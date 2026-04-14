"""Pydantic models for extracted financial rows and notes."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field


class ExtractedRow(BaseModel):
    """A single financial line item extracted from a PDF page."""

    raw_label: str
    raw_values: dict[str, float | None] = Field(default_factory=dict)
    section_path: list[str] = Field(default_factory=list)
    indentation_level: int = 0
    is_subtotal: bool = False
    note_ref: str | None = None
    statement_type: str = ""
    statement_scope: str = "unknown"
    page: int = 0
    column_metadata: dict[str, dict] | None = None


class NoteSubTableRow(BaseModel):
    """A row within a note sub-table."""

    label: str
    values: dict = Field(default_factory=dict)


class NoteSubTable(BaseModel):
    """A sub-table within a financial note."""

    table_title: str | None = None
    rows: list[NoteSubTableRow] = Field(default_factory=list)


class NoteExtraction(BaseModel):
    """Structured data extracted from a financial statement note."""

    note_number: int
    note_title: str
    summary: str = ""
    sub_tables: list[NoteSubTable] = Field(default_factory=list)


def parse_note_number(note_ref: str | None) -> int | None:
    """Extract the first integer from a note reference string.

    Examples:
        "Note 12"       -> 12
        "(Note 3.1)"    -> 3
        "See Note 5"    -> 5
        None            -> None
        "See accompanying notes" -> None
    """
    if not note_ref:
        return None
    match = re.search(r"\d+", str(note_ref))
    return int(match.group(0)) if match else None
