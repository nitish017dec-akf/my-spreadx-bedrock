"""S3 — Page Filter.

Groups classified pages by their pre-assigned statement type and builds
a note-page map. No regex classification happens here — that was done
in S2b (statement_classifier). This is a pure grouping operation.

Ported from: financial-spreadx/lib/pdf/page-filter.ts
"""

from __future__ import annotations

import re

from config import CONTINUATION_MAX_WINDOW
from models.page import ClassifiedPage, FilterResult


def _page_has_foreign_heading(page: ClassifiedPage, section_type: str) -> bool:
    """Return True if the page text contains a statement heading for a type
    different from section_type (and not notes/other).

    Used to stop continuation expansion before a page that starts a new
    statement even when S2b classified it as 'other' (e.g., because the
    heading appeared after a long preamble that pushed it past PAGE_TEXT_WINDOW).
    """
    if not page.text_content:
        return False
    from pdf.statement_classifier import STATEMENT_SIGNALS, normalize_heading_text
    # Scan full text — heading may appear after the PAGE_TEXT_WINDOW used by S2b,
    # which would leave the page classified as "other" even though it starts a new section.
    window = normalize_heading_text(page.text_content)
    for signal in STATEMENT_SIGNALS:
        if signal.type in ("notes", "other", section_type):
            continue
        if signal.pattern.search(window):
            return True
    return False


def expand_with_continuation_pages(
    detected_pages: list[int],
    all_pages: list[ClassifiedPage],
    max_window: int = CONTINUATION_MAX_WINDOW,
    section_type: str = "",
) -> list[int]:
    """Expand a section's page list with continuation pages.

    Stops early when:
      1. End of PDF (no next page)
      2. Scanned page encountered
      3. Next page has a different, assigned section_type (boundary detection)
      4. Next page text contains a heading for a different statement type
         (catches pages misclassified as 'other' that actually start a new section)

    Ported from page-filter.ts expandWithContinuationPages() lines 77-101.
    """
    if not detected_pages:
        return []

    page_map: dict[int, ClassifiedPage] = {p.page_number: p for p in all_pages}
    result: set[int] = set(detected_pages)

    for start_page in detected_pages:
        for offset in range(1, max_window + 1):
            next_num = start_page + offset
            nxt = page_map.get(next_num)
            if nxt is None:
                break  # End of PDF
            if nxt.classification == "scanned":
                break  # Stop at scanned
            # Boundary detection: stop if next page has a different assigned section type
            next_type = nxt.section_type
            if next_type and next_type not in ("other", "notes"):
                break
            # Defense-in-depth: stop if page text contains a foreign statement heading
            # (catches pages where S2b returned 'other' due to long preamble)
            if section_type and _page_has_foreign_heading(nxt, section_type):
                break
            result.add(next_num)

    return sorted(result)


def filter_financial_pages(
    classified_pages: list[ClassifiedPage],
) -> FilterResult:
    """Group pages by their pre-assigned section_type.

    Scanned pages are NOT processed here — they are added to
    selected_pages in Stage 4b after vision classification.

    Ported from page-filter.ts filterFinancialPages() lines 22-70.
    """
    selected: dict[str, list[int]] = {}
    note_page_map: dict[int, list[int]] = {}

    for page in classified_pages:
        if page.classification == "scanned":
            continue

        # Collect primary and secondary section types for this page
        types_to_process: list[str] = []
        if page.section_type and page.section_type != "other":
            types_to_process.append(page.section_type)
        if page.secondary_section_type and page.secondary_section_type not in ("other", page.section_type):
            types_to_process.append(page.secondary_section_type)

        for s_type in types_to_process:
            if s_type == "notes":
                # Try to extract note number from page text
                match = (
                    re.search(r"^note\s+(\d+)", page.text_content, re.IGNORECASE | re.MULTILINE)
                    or re.search(r"^(\d+)\.\s+[A-Z]", page.text_content, re.MULTILINE)
                )
                if match:
                    num = int(match.group(1))
                    pages = note_page_map.get(num, [])
                    pages.append(page.page_number)
                    note_page_map[num] = pages
                continue

            arr = selected.get(s_type, [])
            if page.page_number not in arr:
                arr.append(page.page_number)
            selected[s_type] = arr

    # Expand each section with boundary-aware continuation
    for section, pages in list(selected.items()):
        selected[section] = expand_with_continuation_pages(
            pages, classified_pages, CONTINUATION_MAX_WINDOW, section_type=section
        )

    all_selected: set[int] = set()
    for pages in selected.values():
        all_selected.update(pages)

    total = len(classified_pages)
    return FilterResult(
        selected_pages=selected,
        note_page_map=note_page_map,
        filtered_page_count=len(all_selected),
        total_page_count=total,
        reduction_ratio=len(all_selected) / total if total > 0 else 0.0,
    )
