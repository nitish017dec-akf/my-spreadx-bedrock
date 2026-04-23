"""Pipeline Orchestrator — wires S2 -> S2b -> S3 -> (S4b) -> S5 -> S6.

Stateless: PDF bytes in, PipelineResult out. No database.

Ported from: financial-spreadx/app/api/documents/route.ts lines 75-293
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from config import logger
from claude.extract import extract_statement, segment_page_text
from claude.extract_notes import extract_note
from claude.extract_vision import extract_statement_from_image
from models.extraction import NoteExtraction, parse_note_number
from models.page import ClassifiedPage, FilterResult
from pdf.column_classifier import classify_column_headers
from pdf.page_classifier import classify_pdf_pages, summarize_classifications
from pdf.page_filter import filter_financial_pages
from pdf.page_rasterizer import detect_and_correct_rotation, rasterize_page, rasterize_pages, rotate_image, rotate_image_90
from pdf.scope_detector import detect_scope
from pdf.statement_classifier import (
    classify_scanned_pages,
    classify_statement_type,
)

STATEMENT_TYPES = [
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "equity_statement",
]

ProgressCallback = Callable[[str, str, float], None]


@dataclass
class PipelineResult:
    """Result of running the full extraction pipeline."""

    classified_pages: list[ClassifiedPage] = field(default_factory=list)
    filter_result: FilterResult = field(default_factory=FilterResult)
    extracted_rows: list[dict] = field(default_factory=list)
    extracted_notes: list[NoteExtraction] = field(default_factory=list)
    failed_pages: list[dict] = field(default_factory=list)
    template_type: str = "T0_unknown"
    summary: dict = field(default_factory=dict)


def _notify(cb: ProgressCallback | None, stage: str, detail: str, pct: float) -> None:
    logger.info(f"[{stage}] {detail} ({pct:.0%})")
    if cb:
        cb(stage, detail, pct)


def run_pipeline(
    pdf_bytes: bytes,
    template_type: str = "T0_unknown",
    dpi_scale: float = 2.0,
    progress_callback: ProgressCallback | None = None,
) -> PipelineResult:
    """Run the full S2 -> S2b -> S3 -> (S4b) -> S5 -> S6 pipeline.

    Args:
        pdf_bytes:         Raw PDF file bytes.
        template_type:     Template hint (T1-T8 or T0_unknown).
        dpi_scale:         Render scale for scanned page rasterization.
        progress_callback: Optional (stage, detail, pct) callback.

    Returns:
        PipelineResult with all extracted data.
    """
    result = PipelineResult(template_type=template_type)

    # ── S2: Page classification ──────────────────────────────────────────
    _notify(progress_callback, "S2", "Classifying pages...", 0.05)
    pages = classify_pdf_pages(pdf_bytes)
    result.classified_pages = pages
    summary = summarize_classifications(pages)
    _notify(
        progress_callback,
        "S2",
        f"{summary['total']} pages ({summary['digital']} digital, "
        f"{summary['scanned']} scanned, {summary['hybrid']} hybrid)",
        0.15,
    )

    page_map: dict[int, ClassifiedPage] = {p.page_number: p for p in pages}

    # ── S2b: Statement type classification (digital path) ────────────────
    _notify(progress_callback, "S2b", "Detecting statement types...", 0.18)
    for page in pages:
        if page.classification == "scanned":
            continue
        hits = classify_statement_type(page.text_content)
        page.section_type = hits[0].statement_type
        page.secondary_section_type = hits[1].statement_type if len(hits) > 1 else None
    _notify(progress_callback, "S2b", "Statement types assigned", 0.25)

    # ── S2c: Hybrid page detection ──────────────────────────────────────
    # Detect pages classified as "digital" but with suspiciously incomplete
    # text (high drawing count vs low word count). These are hybrid pages
    # where labels are vector-drawn and invisible to text extraction.
    # Reroute them through the scanned/vision path for accurate extraction.
    for page in pages:
        if page.classification != "digital":
            continue
        if (page.drawing_count > 100
                and page.drawing_count > 0
                and page.word_count < page.drawing_count * 0.5):
            page.classification = "scanned"
            page.requires_ocr = True
            # Keep text_content intact for potential fallback

    # ── S3: Financial page filtering ─────────────────────────────────────
    _notify(progress_callback, "S3", "Filtering financial pages...", 0.28)
    filter_result = filter_financial_pages(pages)
    result.filter_result = filter_result
    _notify(
        progress_callback,
        "S3",
        f"{filter_result.filtered_page_count} pages selected",
        0.35,
    )

    # ── S4b: Scanned page classification (vision) ────────────────────────
    scanned_pages = [p for p in pages if p.classification == "scanned"]
    if scanned_pages:
        _notify(progress_callback, "S4b", f"Classifying {len(scanned_pages)} scanned pages...", 0.36)
        scanned_nums = [p.page_number for p in scanned_pages]
        image_buffers = rasterize_pages(pdf_bytes, scanned_nums, scale=1.5)

        scanned_classifications = classify_scanned_pages(image_buffers)

        for page_num, cls in scanned_classifications.items():
            page = page_map[page_num]
            primary = cls.statement_types[0] if cls.statement_types else "other"
            secondary = cls.statement_types[1] if len(cls.statement_types) > 1 else None

            page.section_type = primary
            page.secondary_section_type = secondary
            # Store PNG buffer for reuse in S5 (avoid double rasterization)
            page.image_buffer = image_buffers.get(page_num)

            # Add to filter_result.selected_pages
            if primary and primary not in ("other", "notes"):
                arr = filter_result.selected_pages.get(primary, [])
                if page_num not in arr:
                    arr.append(page_num)
                    filter_result.selected_pages[primary] = arr
            if secondary and secondary not in ("other", "notes"):
                arr2 = filter_result.selected_pages.get(secondary, [])
                if page_num not in arr2:
                    arr2.append(page_num)
                    filter_result.selected_pages[secondary] = arr2

        # Clear S4b classification buffers so S5 re-rasterizes at full DPI.
        # The 1.5x classification images are too low-res for data extraction
        # on dense or multi-column pages.
        for page in scanned_pages:
            page.image_buffer = None

    # ── S5: Row extraction ───────────────────────────────────────────────
    _notify(progress_callback, "S5", "Extracting rows...", 0.38)
    all_rows: list[dict] = []
    ocr_page_nums: set[int] = set()

    total_pages_to_extract = sum(
        len(filter_result.selected_pages.get(st, [])) for st in STATEMENT_TYPES
    )
    pages_extracted = 0

    from config import MAX_CONCAT_TEXT_FOR_EXTRACT

    for stmt_type in STATEMENT_TYPES:
        page_nums = filter_result.selected_pages.get(stmt_type, [])
        if not page_nums:
            continue

        # Detect scope from the first page of this statement type
        first_page = page_map.get(page_nums[0])
        scope = detect_scope(first_page.text_content) if first_page else "unknown"

        # Split pages into digital and scanned groups
        digital_pages = [
            page_map[pn] for pn in page_nums
            if page_map.get(pn) and page_map[pn].classification == "digital"
        ]
        scanned_page_nums = [
            pn for pn in page_nums
            if page_map.get(pn) and page_map[pn].classification != "digital"
        ]

        # ── Digital path: segment, concatenate, extract once ────────────
        if digital_pages:
            pages_extracted += len(digital_pages)
            pct = 0.38 + (pages_extracted / max(total_pages_to_extract, 1)) * 0.42
            dp_nums = [p.page_number for p in digital_pages]
            _notify(
                progress_callback,
                "S5",
                f"Extracting {stmt_type} digital pages {dp_nums} ({pages_extracted}/{total_pages_to_extract})...",
                pct,
            )

            # Segment each page to isolate target statement, then concatenate
            segments = [
                segment_page_text(p.text_content, stmt_type)
                for p in digital_pages
            ]
            combined_text = "\n\n--- PAGE BREAK ---\n\n".join(segments)
            combined_text = combined_text[:MAX_CONCAT_TEXT_FOR_EXTRACT]

            rows = extract_statement(
                combined_text, stmt_type, template_type,
                max_text_length=MAX_CONCAT_TEXT_FOR_EXTRACT,
            )

            # Fallback 1: if concatenated extraction returned 0 rows,
            # retry with per-page extraction (some PDFs work better
            # when pages are extracted individually)
            if not rows and len(digital_pages) > 1:
                for dp in digital_pages:
                    seg = segment_page_text(dp.text_content, stmt_type)
                    page_rows = extract_statement(seg, stmt_type, template_type)
                    rows.extend(page_rows)

            # Fallback 2: if text extraction still returned 0 rows,
            # retry each page through the vision path (rasterize + OCR)
            if not rows:
                for dp in digital_pages:
                    try:
                        png = rasterize_page(pdf_bytes, dp.page_number, dpi_scale)
                        png = detect_and_correct_rotation(
                            png, dp.page_width, dp.page_height,
                        )
                        vision_rows = extract_statement_from_image(
                            png, stmt_type, template_type, dp.page_number,
                        )
                        rows.extend(vision_rows)
                        ocr_page_nums.add(dp.page_number)
                    except Exception as e:
                        logger.warning(f"Vision fallback failed for digital page {dp.page_number}: {e}")
                        result.failed_pages.append({"page": dp.page_number, "stage": "digital_vision_fallback", "error": str(e)})

            # Enrich rows with metadata (use first digital page for page number)
            first_dp = digital_pages[0].page_number
            year_keys: list[str] = []
            for r in rows:
                year_keys.extend(r.get("raw_values", {}).keys())
            unique_years = list(set(year_keys))
            col_meta_list = classify_column_headers(unique_years)
            col_meta = {
                str(m.year or m.label): {"type": m.type, "label": m.label}
                for m in col_meta_list
            }
            for r in rows:
                if not r.get("raw_label", "").strip():
                    continue
                r["statement_type"] = stmt_type
                r["statement_scope"] = scope
                r["page"] = first_dp
                r["column_metadata"] = col_meta
                all_rows.append(r)

        # ── Scanned path: extract each page individually via vision ─────
        for page_num in scanned_page_nums:
            page_data = page_map.get(page_num)
            if not page_data:
                continue

            pages_extracted += 1
            pct = 0.38 + (pages_extracted / max(total_pages_to_extract, 1)) * 0.42
            _notify(
                progress_callback,
                "S5",
                f"Extracting {stmt_type} page {page_num} ({pages_extracted}/{total_pages_to_extract})...",
                pct,
            )

            rows = []
            try:
                # Adaptive DPI: use higher resolution for dense vector-drawn pages
                effective_dpi = dpi_scale
                if page_data.drawing_count > 2000:
                    effective_dpi = max(dpi_scale, 3.0)

                png = page_data.image_buffer or rasterize_page(pdf_bytes, page_num, effective_dpi)
                png = detect_and_correct_rotation(
                    png, page_data.page_width, page_data.page_height,
                )
                rows = extract_statement_from_image(png, stmt_type, template_type, page_num)

                # Retry on 0 rows or garbled micro-extractions: sweep angles at higher DPI
                if not rows or len(rows) < 3:
                    retry_dpi = max(effective_dpi, 3.0)
                    retry_png = rasterize_page(pdf_bytes, page_num, retry_dpi)
                    for _angle in (0, 90, 180, 270):
                        rotated = rotate_image(retry_png, _angle) if _angle else retry_png
                        rows = extract_statement_from_image(rotated, stmt_type, template_type, page_num)
                        if rows and len(rows) >= 3:
                            break

                ocr_page_nums.add(page_num)
            except Exception as e:
                logger.warning(f"All extraction paths failed for scanned page {page_num}: {e}")
                result.failed_pages.append({"page": page_num, "stage": "scanned_all_paths", "error": str(e)})
                # Fallback: try text extraction if vision fails
                if page_data.text_content:
                    rows = extract_statement(page_data.text_content, stmt_type, template_type)

            # Enrich rows with metadata
            year_keys_s: list[str] = []
            for r in rows:
                year_keys_s.extend(r.get("raw_values", {}).keys())
            unique_years_s = list(set(year_keys_s))
            col_meta_list_s = classify_column_headers(unique_years_s)
            col_meta_s = {
                str(m.year or m.label): {"type": m.type, "label": m.label}
                for m in col_meta_list_s
            }
            for r in rows:
                if not r.get("raw_label", "").strip():
                    continue
                r["statement_type"] = stmt_type
                r["statement_scope"] = scope
                r["page"] = page_num
                r["column_metadata"] = col_meta_s
                all_rows.append(r)

    # Remove exact duplicates produced by dual-type scanned pages being extracted twice.
    # section_path and indentation_level are included so legitimately repeated labels
    # (e.g., "Net income" appearing both at the P&L bottom and in the attribution section)
    # are NOT removed — they occupy structurally distinct positions.
    seen_keys: set[tuple] = set()
    deduped_rows: list[dict] = []
    for r in all_rows:
        key = (
            r.get("raw_label", "").strip(),
            str(sorted(r.get("raw_values", {}).items())),
            r.get("statement_type", ""),
            r.get("page", 0),
            str(r.get("section_path", [])),
            r.get("indentation_level", 0),
        )
        if key not in seen_keys:
            seen_keys.add(key)
            deduped_rows.append(r)
    all_rows = deduped_rows

    result.extracted_rows = all_rows
    _notify(progress_callback, "S5", f"{len(all_rows)} rows extracted", 0.80)

    # ── S6: Note extraction ──────────────────────────────────────────────
    _notify(progress_callback, "S6", "Extracting footnotes...", 0.82)
    referenced_note_nums: set[int] = set()
    for row in all_rows:
        n = parse_note_number(row.get("note_ref"))
        if n is not None:
            referenced_note_nums.add(n)

    notes: list[NoteExtraction] = []
    for note_num in sorted(referenced_note_nums):
        note_page_nums = filter_result.note_page_map.get(note_num, [])
        if not note_page_nums:
            continue

        note_text = "\n\n".join(
            page_map[pn].text_content
            for pn in note_page_nums
            if pn in page_map and page_map[pn].text_content
        )
        if not note_text.strip():
            continue

        _notify(progress_callback, "S6", f"Extracting Note {note_num}...", 0.82 + 0.10 * (len(notes) / max(len(referenced_note_nums), 1)))
        note = extract_note(note_text, note_num, template_type)
        notes.append(note)

    result.extracted_notes = notes
    _notify(progress_callback, "S6", f"{len(notes)} notes extracted", 0.95)

    # ── Build summary ────────────────────────────────────────────────────
    result.summary = {
        "total_pages": summary["total"],
        "digital_pages": summary["digital"],
        "scanned_pages": summary["scanned"],
        "hybrid_pages": summary["hybrid"],
        "filtered_pages": filter_result.filtered_page_count,
        "total_rows": len(all_rows),
        "rows_by_type": {
            st: sum(1 for r in all_rows if r.get("statement_type") == st)
            for st in STATEMENT_TYPES
        },
        "total_notes": len(notes),
        "ocr_pages": len(ocr_page_nums),
        "template_type": template_type,
        "failed_pages": len(result.failed_pages),
    }

    _notify(progress_callback, "Done", "Pipeline complete", 1.0)
    return result
