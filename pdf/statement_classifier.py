"""Statement Type Classifier — corpus-grounded, two-path (digital + scanned).

Digital path: 39 regex signal patterns matched against page heading text.
Scanned path: Claude vision classification (one call per page).

Ported from: financial-spreadx/lib/pdf/statement-classifier.ts
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from config import AWS_REGION, BEDROCK_DEFAULT_MODEL_ID, PAGE_TEXT_WINDOW
from models.page import (
    ClassifiedStatement,
    ScannedPageClassification,
    StatementSignal,
    StatementType,
)

if TYPE_CHECKING:
    pass

# ── STATEMENT_SIGNALS ────────────────────────────────────────────────────────
# Ordered longest/most-specific first within each type group.
# All patterns use statements? (plural-tolerant).
# Ported verbatim from statement-classifier.ts lines 29-83.

I = re.IGNORECASE
IM = re.IGNORECASE | re.MULTILINE
M = re.MULTILINE

STATEMENT_SIGNALS: list[StatementSignal] = [
    # ── BALANCE SHEET (6 patterns) ──
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+financial\s+condition", I),
                    type="balance_sheet", weight=1.0, template_hints=["T1", "T2"]),
    StatementSignal(pattern=re.compile(r"consolidated\s+and\s+company\s+statements?\s+of\s+financial\s+position", I),
                    type="balance_sheet", weight=1.0),
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+financial\s+position", I),
                    type="balance_sheet", weight=1.0),
    StatementSignal(pattern=re.compile(r"balance\s+sheet\s+as\s+(at|on)\s+", I),
                    type="balance_sheet", weight=1.0, template_hints=["T3", "T4", "T5"]),
    StatementSignal(pattern=re.compile(r"consolidated\s+balance\s+sheets?", I),
                    type="balance_sheet", weight=1.0, template_hints=["T1", "T2"]),
    StatementSignal(pattern=re.compile(r"\bbalance\s+sheets?\b", I),
                    type="balance_sheet", weight=0.9),

    # ── INCOME STATEMENT (13 patterns) ──
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+income\s+and\s+comprehensive\s+income", I),
                    type="income_statement", weight=1.0, template_hints=["T1"]),
    StatementSignal(pattern=re.compile(r"statement\s+of\s+profit\s+or\s+loss\s+and\s+other\s+comprehensive\s+income", I),
                    type="income_statement", weight=1.0, template_hints=["T8"]),
    StatementSignal(pattern=re.compile(r"group\s+statement\s+of\s+profit\s+or\s+loss", I),
                    type="income_statement", weight=1.0, template_hints=["T7"]),
    StatementSignal(pattern=re.compile(r"statement\s+of\s+profit\s+or\s+loss\b", I),
                    type="income_statement", weight=1.0, template_hints=["T8"]),
    StatementSignal(pattern=re.compile(r"profit\s+(and|&)\s+loss\s+account\s+and\s+other\s+comprehensive\s+income", I),
                    type="income_statement", weight=1.0, template_hints=["T6"]),
    StatementSignal(pattern=re.compile(r"profit\s+(and|&)\s+loss\s+account", I),
                    type="income_statement", weight=1.0, template_hints=["T4", "T5"]),
    StatementSignal(pattern=re.compile(r"statement\s+of\s+profit\s+and\s+loss", I),
                    type="income_statement", weight=1.0, template_hints=["T3", "T4"]),
    StatementSignal(pattern=re.compile(r"comprehensive\s+income\s+statement", I),
                    type="income_statement", weight=1.0, template_hints=["T8"]),
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+operations", I),
                    type="income_statement", weight=1.0, template_hints=["T1", "T2"]),
    StatementSignal(pattern=re.compile(r"consolidated\s+income\s+statement", I),
                    type="income_statement", weight=1.0, template_hints=["T5"]),
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+comprehensive\s+income", I),
                    type="income_statement", weight=1.0),
    # CRITICAL FIX: s? catches "STATEMENTS OF INCOME" (Cash America, all T1 US GAAP)
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+(profit|income|operations|comprehensive\s+income)", I),
                    type="income_statement", weight=1.0),
    StatementSignal(pattern=re.compile(r"statement\s+of\s+(comprehensive\s+)?income", I),
                    type="income_statement", weight=0.9),
    StatementSignal(pattern=re.compile(r"\bincome\s+statements?\b", I),
                    type="income_statement", weight=0.9),

    # ── CASH FLOW (5 patterns) ──
    StatementSignal(pattern=re.compile(r"(group|company)\s+statement\s+of\s+cash\s+flows", I),
                    type="cash_flow", weight=1.0, template_hints=["T7"]),
    # CRITICAL FIX: s? catches "STATEMENTS OF CASH FLOWS"
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+cash\s+flows?\b", I),
                    type="cash_flow", weight=1.0),
    StatementSignal(pattern=re.compile(r"consolidated\s+cash\s+flow\s+statement", I),
                    type="cash_flow", weight=1.0, template_hints=["T8"]),
    StatementSignal(pattern=re.compile(r"cash\s+flow\s+statement", I),
                    type="cash_flow", weight=1.0, template_hints=["T4"]),
    StatementSignal(pattern=re.compile(r"cash\s+flows?\s+(from|used\s+in)\s+(operating|investing|financing)\s+activities", I),
                    type="cash_flow", weight=0.9),

    # ── EQUITY STATEMENT (10 patterns) ──
    StatementSignal(pattern=re.compile(r"reconciliation\s+of\s+members['\u2019]?\s+interests", I),
                    type="equity_statement", weight=1.0, template_hints=["T6"]),
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+changes\s+in\s+members['\u2019]?\s+(equity|capital)", I),
                    type="equity_statement", weight=1.0, template_hints=["T6"]),
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+changes\s+in\s+partners['\u2019]?\s+capital", I),
                    type="equity_statement", weight=1.0, template_hints=["T2"]),
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+changes\s+in\s+members['\u2019]?\s+capital", I),
                    type="equity_statement", weight=1.0, template_hints=["T2"]),
    StatementSignal(pattern=re.compile(r"stockholders['\u2019]?\s+equity\s+and\s+comprehensive\s+loss", I),
                    type="equity_statement", weight=1.0, template_hints=["T1"]),
    # CRITICAL FIX: (changes\s+in\s+)? optional — catches "STATEMENTS OF STOCKHOLDERS EQUITY"
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+(changes\s+in\s+)?stockholders['\u2019]?\s+equity", I),
                    type="equity_statement", weight=1.0, template_hints=["T1"]),
    StatementSignal(pattern=re.compile(r"consolidated\s+statements?\s+of\s+equity\b", I),
                    type="equity_statement", weight=1.0, template_hints=["T1"]),
    StatementSignal(pattern=re.compile(r"consolidated\s+and\s+company\s+statements?\s+of\s+changes\s+in\s+equity", I),
                    type="equity_statement", weight=1.0),
    StatementSignal(pattern=re.compile(r"changes\s+in\s+(shareholders|stockholders)['\u2019]?\s+equity", I),
                    type="equity_statement", weight=1.0),
    StatementSignal(pattern=re.compile(r"statements?\s+of\s+changes\s+in\s+equity", I),
                    type="equity_statement", weight=1.0),

    # ── NOTES (3 patterns) ──
    StatementSignal(pattern=re.compile(r"^notes?\s+to\s+the\s+(consolidated\s+)?(financial\s+statements?|accounts)", IM),
                    type="notes", weight=1.0),
    StatementSignal(pattern=re.compile(r"^note\s+\d+\b", IM),
                    type="notes", weight=0.9),
    StatementSignal(pattern=re.compile(r"^\d+\.\s+[A-Z][A-Z\s]{4,}", M),
                    type="notes", weight=0.7),
]


# ── Heading normalization ────────────────────────────────────────────────────

def normalize_heading_text(text: str) -> str:
    """Replace smart quotes with ASCII equivalents for reliable regex matching.

    Ported from statement-classifier.ts normalizeHeadingText() lines 97-101.
    """
    # Smart single quotes -> ASCII apostrophe
    text = re.sub(r"[\u0091\u0092\u2018\u2019\u201a\u201b]", "'", text)
    # Smart double quotes -> ASCII double quote
    text = re.sub(r"[\u0093\u0094\u201c\u201d\u201e\u201f]", '"', text)
    return text


# ── Digital path ─────────────────────────────────────────────────────────────

def classify_statement_type(text_content: str) -> list[ClassifiedStatement]:
    """Classify statement type(s) for a digital/hybrid page.

    Scans first 600 chars (after normalizing smart quotes), matches against
    STATEMENT_SIGNALS in order. Returns ALL matching types — dual-statement
    pages return length 2. Ordered by first match position.

    Ported from statement-classifier.ts classifyStatementType() lines 109-129.
    """
    window = normalize_heading_text(text_content[:PAGE_TEXT_WINDOW])
    results: list[ClassifiedStatement] = []
    seen_types: set[StatementType] = set()

    for signal in STATEMENT_SIGNALS:
        match = signal.pattern.search(window)
        if match and signal.type not in seen_types:
            results.append(
                ClassifiedStatement(
                    statement_type=signal.type,
                    confidence=signal.weight,
                    matched_pattern=match.group(0),
                )
            )
            seen_types.add(signal.type)

    if results:
        return results

    return [ClassifiedStatement(statement_type="other", confidence=1.0, matched_pattern="")]


# ── Scanned path (Claude vision) ────────────────────────────────────────────

_SCANNED_PROMPT = """Identify the financial statement type(s) on this page.
Return ONLY valid JSON, no markdown fences:
{
  "pages": [{
    "statement_types": ["balance_sheet"|"income_statement"|"cash_flow"|"equity_statement"|"notes"|"other"],
    "confidence": 0.0-1.0,
    "visible_years": [2024, 2023],
    "heading_verbatim": "exact heading printed on page — empty string if none",
    "scope": "consolidated"|"standalone"|"group"|"company"|"unknown",
    "is_continuation": false
  }]
}
Rules:
- statement_types may have 1-2 values (some pages show two statements side by side).
- heading_verbatim is the literal heading; empty string for continuation pages.
- is_continuation: true when no statement heading is visible (page continues previous statement).
- confidence: 0.95+ clear heading visible; 0.70-0.94 inferred from table structure only.
- If confidence < 0.70, set statement_types: ["other"] and is_continuation: false."""


def classify_scanned_pages(
    image_buffers: dict[int, bytes],
) -> dict[int, ScannedPageClassification]:
    """Vision-based classification for scanned pages (no extractable text).

    One Claude call per page, max_tokens 512 (classification only).

    Ported from statement-classifier.ts classifyScannedPages() lines 159-216.
    """
    import boto3

    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    results: dict[int, ScannedPageClassification] = {}

    fallback = ScannedPageClassification(
        statement_types=["other"],
        confidence=0.0,
        visible_years=[],
        heading_verbatim="",
        scope="unknown",
        is_continuation=False,
    )

    for page_num, buf in image_buffers.items():
        try:
            response = client.converse(
                modelId=BEDROCK_DEFAULT_MODEL_ID,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "image": {
                                    "format": "png",
                                    "source": {"bytes": buf}
                                }
                            },
                            {"text": _SCANNED_PROMPT}
                        ]
                    }
                ],
                inferenceConfig={"maxTokens": 512},
            )
            raw = response["output"]["message"]["content"][0]["text"]
        except Exception:
            raw = '{"pages": []}'

        clean = re.sub(r"```json|```", "", raw).strip()

        try:
            parsed = json.loads(clean)
            page_data = parsed.get("pages", [{}])[0]
            results[page_num] = ScannedPageClassification(
                statement_types=page_data.get("statement_types", ["other"]),
                confidence=page_data.get("confidence", 0.0),
                visible_years=page_data.get("visible_years", []),
                heading_verbatim=page_data.get("heading_verbatim", ""),
                scope=page_data.get("scope", "unknown"),
                is_continuation=page_data.get("is_continuation", False),
            )
        except (json.JSONDecodeError, IndexError, KeyError):
            results[page_num] = fallback.model_copy()

    return results
