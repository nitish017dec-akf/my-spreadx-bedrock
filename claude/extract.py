"""S5 — Row Extractor (digital text path).

Extracts structured financial rows from page text using Claude.

Ported from: financial-spreadx/lib/claude/extract.ts
"""

from __future__ import annotations

import json
import re

import boto3

from config import BEDROCK_DEFAULT_MODEL_ID, MAX_PAGE_TEXT_FOR_EXTRACT, TEXT_EXTRACT_MAX_TOKENS, get_bedrock_client
from pdf.statement_classifier import STATEMENT_SIGNALS, normalize_heading_text


def extract_four_digit_year(key: str) -> str:
    """Normalize a year string to a 4-digit year.

    Examples:
        "2019"          -> "2019"
        "2018-19"       -> "2019"
        "FY 2018-19"    -> "2019"
        "Year ended 2023" -> "2023"
        "no year here"  -> "no year here"

    Ported from extract.ts extractFourDigitYear() lines 83-94.
    """
    # Fiscal year format: "2018-19" -> "2019"
    fiscal_match = re.search(r"(\d{4})-(\d{2})$", key.strip())
    if fiscal_match:
        century = (int(fiscal_match.group(1)) // 100) * 100
        return str(century + int(fiscal_match.group(2)))

    # Extract last 4-digit year found in the string
    all_years = re.findall(r"\d{4}", key)
    if all_years:
        return all_years[-1]

    return key


_MIN_SEGMENT_CHARS = 200  # Segments smaller than this are likely false matches


def segment_page_text(page_text: str, target_statement_type: str) -> str:
    """Isolate the relevant statement section from a multi-statement page.

    Scans the full page text for all statement heading matches using
    STATEMENT_SIGNALS, then returns only the segment that belongs to
    the target_statement_type.

    Headings must appear at the start of a line to avoid matching
    inline references or table-of-contents entries.  Segments shorter
    than _MIN_SEGMENT_CHARS are treated as false matches and the full
    text is returned instead.

    If no heading boundary for the target type is found, returns the
    full text unchanged (safe fallback).
    """
    normalized = normalize_heading_text(page_text)

    # Find all statement heading positions across the full text.
    # Only consider matches at the start of a line (after \n or at pos 0)
    # to avoid inline mentions and TOC references.
    matches: list[tuple[int, str]] = []  # (position, statement_type)
    seen_positions: set[int] = set()

    for signal in STATEMENT_SIGNALS:
        if signal.type in ("notes", "other"):
            continue
        for m in signal.pattern.finditer(normalized):
            pos = m.start()
            # Find the start of the line containing this match
            line_start = normalized.rfind("\n", 0, pos) + 1  # 0 if no newline found
            chars_before_match = pos - line_start
            # Heading must be near the start of a line (allow short prefixes
            # like "Consolidated " before the matched pattern, but reject
            # matches embedded deep in paragraph text)
            if chars_before_match > 50:
                continue
            # Use line_start as the position so the segment includes the
            # full heading line (e.g., "Consolidated" prefix)
            seg_pos = line_start
            if seg_pos not in seen_positions:
                matches.append((seg_pos, signal.type))
                seen_positions.add(seg_pos)

    if not matches:
        return page_text

    # Sort by position in text
    matches.sort(key=lambda x: x[0])

    # Find the target statement's segment
    for i, (pos, stype) in enumerate(matches):
        if stype == target_statement_type:
            start = pos
            # End is the next match of a DIFFERENT type (skip same-type duplicates
            # from overlapping regex patterns matching nearby positions)
            end = len(page_text)
            for j in range(i + 1, len(matches)):
                if matches[j][1] != target_statement_type:
                    end = matches[j][0]
                    break
            segment = page_text[start:end]
            # Guard against tiny segments from TOC/footer false matches
            if len(segment) >= _MIN_SEGMENT_CHARS:
                return segment
            # Segment too small — likely a false match; return full text
            return page_text

    # Target type not found in headings — return full text
    return page_text


_EXTRACT_PROMPT_TEMPLATE = """You are a financial data extraction engine. Extract ALL financial line items from this {statement_type_display} page.

Template type: {template_type}
Statement type: {statement_type}

Rules:
1. raw_label must be the EXACT text from the document — do not paraphrase or normalize
2. Extract ALL year columns present. For each row, add one year_values entry per column. Use exactly 4 digits for the year field (e.g. "2019", "2018"). For fiscal years like "2018-19" use the ending year "2019".
3. Negative values should use negative numbers, not parentheses
4. Values in parentheses like (1,234) should be converted to -1234
5. Set is_subtotal=true for total/subtotal rows (e.g., "Total Revenue", "Net Income")
6. Set note_ref to the note reference if present (e.g., "Note 12", "Note 3.1")
7. section_path should reflect the hierarchy (e.g., ["Revenue", "Interest Income"])
8. indentation_level: 0 for main items, 1 for sub-items, 2+ for deeper nesting
9. Account codes before line items (e.g., "401000 Brokerage fee income") — use the descriptive text as raw_label, not the account code
10. Values with spaces inside parentheses like ( 5,748) are negative: -5748
11. Percentage columns may appear alongside value columns — extract monetary values only
12. Note references may appear in unusual formats like "(Note 6 -32 )" — extract "Note 6" as note_ref

Return ONLY valid JSON matching this schema:
{{
  "rows": [
    {{
      "raw_label": "string",
      "year_values": [{{"year": "2024", "value": 1234.56}}, {{"year": "2023", "value": null}}],
      "section_path": ["string"],
      "indentation_level": 0,
      "is_subtotal": false,
      "note_ref": null
    }}
  ]
}}

Page text:
{page_text}"""


def extract_statement(
    page_text: str,
    statement_type: str,
    template_type: str,
    max_text_length: int | None = None,
) -> list[dict]:
    """Extract financial rows from a page of text via Claude.

    Args:
        page_text:       Full text content of the page(s).
        statement_type:  income_statement | balance_sheet | cash_flow | equity_statement.
        template_type:   T1-T8 template classification.
        max_text_length: Override for text truncation limit (default: MAX_PAGE_TEXT_FOR_EXTRACT).
                         Pass a larger value for multi-page concatenated text.

    Returns:
        List of dicts with keys: raw_label, raw_values, section_path,
        indentation_level, is_subtotal, note_ref.
    """
    limit = max_text_length or MAX_PAGE_TEXT_FOR_EXTRACT
    prompt = _EXTRACT_PROMPT_TEMPLATE.format(
        statement_type_display=statement_type.replace("_", " "),
        statement_type=statement_type,
        template_type=template_type,
        page_text=page_text[:limit],
    )

    client = get_bedrock_client()
    response = client.converse(
        modelId=BEDROCK_DEFAULT_MODEL_ID,
        system=[{"text": "You are a financial data extraction engine. You MUST return ONLY valid JSON with a top-level 'rows' array. No other keys at the top level. No markdown fences. No commentary."}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": TEXT_EXTRACT_MAX_TOKENS},
    )

    raw = response["output"]["message"]["content"][0]["text"]

    clean = re.sub(r"```json|```", "", raw).strip()
    
    # Robustly find the JSON block in case the model is chatty
    start_idx = clean.find('{')
    end_idx = clean.rfind('}')
    if start_idx != -1 and end_idx != -1:
        clean = clean[start_idx:end_idx + 1]

    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e} | Raw text snippet: {raw[:200]}")
        return []

    rows = parsed.get("rows", [])
    result: list[dict] = []

    for row in rows:
        raw_label = row.get("raw_label", "").strip()
        if not raw_label:
            continue

        # Convert year_values array to raw_values dict
        year_values = row.get("year_values", [])
        raw_values: dict[str, float | None] = {}
        for yv in year_values:
            year_key = extract_four_digit_year(str(yv.get("year", "")))
            raw_values[year_key] = yv.get("value")

        result.append(
            {
                "raw_label": raw_label,
                "raw_values": raw_values,
                "section_path": row.get("section_path", []),
                "indentation_level": row.get("indentation_level", 0),
                "is_subtotal": row.get("is_subtotal", False),
                "note_ref": row.get("note_ref"),
            }
        )

    return result
