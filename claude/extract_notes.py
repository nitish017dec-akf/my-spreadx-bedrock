"""S6 — Note Extractor.

Extracts structured data from financial statement notes using Claude.

Ported from: financial-spreadx/lib/claude/extract-notes.ts
"""

from __future__ import annotations

import json
import re

import boto3

from config import AWS_REGION, BEDROCK_DEFAULT_MODEL_ID, MAX_NOTE_TEXT
from models.extraction import NoteExtraction, NoteSubTable, NoteSubTableRow


# Prompt ported verbatim from extract-notes.ts lines 43-54
_NOTE_PROMPT_TEMPLATE = """Extract structured data from this financial statement note (Note {note_number}).
Template: {template_type}

Rules:
1. note_title should be the heading of the note
2. summary should be a brief (max 500 chars) description of what the note covers
3. If the note contains tables, extract them as sub_tables with their rows
4. Values in parentheses like (1,234) should be converted to -1234
5. For unknown values, use null not strings

Return ONLY valid JSON matching this schema:
{{
  "note_number": {note_number},
  "note_title": "string",
  "summary": "string (max 500 chars)",
  "sub_tables": [
    {{
      "table_title": "string or null",
      "rows": [
        {{"label": "string", "values": {{"2024": 1234.56, "2023": null}}}}
      ]
    }}
  ]
}}

Note text:
{note_text}"""


def extract_note(
    note_text: str,
    note_number: int,
    template_type: str,
) -> NoteExtraction:
    """Extract structured data from a financial statement note.

    Args:
        note_text:      Full text of the note page(s).
        note_number:    The note number (e.g., 12).
        template_type:  T1-T8 template classification.

    Returns:
        NoteExtraction with note_number, note_title, summary, sub_tables.
        Falls back to a basic note if parsing fails.
    """
    prompt = _NOTE_PROMPT_TEMPLATE.format(
        note_number=note_number,
        template_type=template_type,
        note_text=note_text[:MAX_NOTE_TEXT],
    )

    try:
        client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
        response = client.converse(
            modelId=BEDROCK_DEFAULT_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 4096},
        )

        raw = response["output"]["message"]["content"][0]["text"]

        clean = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(clean)

        # Build sub_tables from parsed data
        sub_tables: list[NoteSubTable] = []
        for st in parsed.get("sub_tables", []):
            rows = [
                NoteSubTableRow(label=r.get("label", ""), values=r.get("values", {}))
                for r in st.get("rows", [])
            ]
            sub_tables.append(
                NoteSubTable(table_title=st.get("table_title"), rows=rows)
            )

        return NoteExtraction(
            note_number=parsed.get("note_number", note_number),
            note_title=parsed.get("note_title", f"Note {note_number}"),
            summary=parsed.get("summary", "")[:500],
            sub_tables=sub_tables,
        )

    except Exception:
        # Fallback: basic note with first line as title
        first_line = note_text.split("\n")[0].strip() if note_text else ""
        return NoteExtraction(
            note_number=note_number,
            note_title=first_line or f"Note {note_number}",
            summary=note_text[:500] if note_text else "",
            sub_tables=[],
        )
