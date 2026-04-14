"""Streamlit demo UI for the SpreadX Raw Extraction pipeline.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Project setup (MUST be before any project imports) ───────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json

import pandas as pd
import streamlit as st

# Bedrock uses standard boto3 credential resolution (e.g. AWS_ACCESS_KEY_ID via env, or ~/.aws)

from export.xlsx_export import build_raw_extraction_xlsx
from pipeline.orchestrator import run_pipeline

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SpreadX Extractor",
    page_icon=":bar_chart:",
    layout="wide",
)

st.title("Financial SpreadX - Raw Extraction Demo")

# ── Sidebar settings ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    template = st.selectbox(
        "Template type",
        ["T0_unknown", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"],
        help="T0_unknown = auto / no hint. T1-T8 = specific accounting standard.",
    )
    dpi = st.slider("Render DPI scale", 1.0, 3.0, 2.0, 0.5,
                     help="Higher = better OCR quality for scanned pages, slower.")

    st.divider()
    st.caption("SpreadX Extractor v0.1")
    st.caption("Stages: S2 (classify) > S3 (filter) > S5 (extract) > S6 (notes)")

# ── Upload section ───────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Upload a PDF financial statement",
    type=["pdf"],
    help="One PDF at a time. Max ~50 MB.",
)

if uploaded is not None:
    # Save uploaded file bytes (Streamlit UploadedFile is file-like)
    pdf_bytes = uploaded.read()

    # Check if we already processed this exact file
    file_key = f"{uploaded.name}_{len(pdf_bytes)}"
    if st.session_state.get("_last_file_key") == file_key and "pipeline_result" in st.session_state:
        # Reuse cached result
        result = st.session_state["pipeline_result"]
    else:
        # ── Run pipeline with live progress ──────────────────────────────
        progress_bar = st.progress(0, text="Starting pipeline...")
        status_panel = st.status("Processing...", expanded=True)

        def _progress(stage: str, detail: str, pct: float) -> None:
            progress_bar.progress(pct, text=f"{stage}: {detail}")
            status_panel.write(f"**{stage}:** {detail}")

        result = run_pipeline(
            pdf_bytes,
            template_type=template,
            dpi_scale=dpi,
            progress_callback=_progress,
        )

        # Build XLSX once
        xlsx_bytes = build_raw_extraction_xlsx(result)

        # Cache in session state
        st.session_state["pipeline_result"] = result
        st.session_state["xlsx_bytes"] = xlsx_bytes
        st.session_state["_last_file_key"] = file_key

        progress_bar.progress(1.0, text="Complete!")
        status_panel.update(label="Pipeline complete!", state="complete")

    # ── Summary metrics ──────────────────────────────────────────────────
    st.divider()
    s = result.summary
    cols = st.columns(5)
    cols[0].metric("Total Pages", s.get("total_pages", 0))
    cols[1].metric("Digital", s.get("digital_pages", 0))
    cols[2].metric("Scanned", s.get("scanned_pages", 0))
    cols[3].metric("Rows Extracted", s.get("total_rows", 0))
    cols[4].metric("Notes Parsed", s.get("total_notes", 0))

    # ── Data preview ─────────────────────────────────────────────────────
    st.subheader("Extracted Rows")

    if result.extracted_rows:
        df = pd.DataFrame(result.extracted_rows)
        # Select and order display columns
        display_cols = [
            "page", "statement_type", "raw_label", "indentation_level",
            "is_subtotal", "note_ref", "statement_scope", "raw_values",
        ]
        available = [c for c in display_cols if c in df.columns]
        df_display = df[available].copy()

        # Convert raw_values dict to string for display
        if "raw_values" in df_display.columns:
            df_display["raw_values"] = df_display["raw_values"].apply(
                lambda v: json.dumps(v) if isinstance(v, dict) else str(v)
            )

        st.dataframe(df_display, use_container_width=True, height=420)

        # ── Per-statement-type expanders ─────────────────────────────────
        stmt_types = df["statement_type"].unique().tolist() if "statement_type" in df.columns else []
        for stype in sorted(stmt_types):
            count = int((df["statement_type"] == stype).sum())
            with st.expander(f"{stype.replace('_', ' ').title()} ({count} rows)"):
                filtered = df_display[df["statement_type"] == stype]
                st.dataframe(filtered, use_container_width=True, height=250)
    else:
        st.info("No rows extracted. Check that the PDF contains financial statements.")

    # ── Notes preview ────────────────────────────────────────────────────
    if result.extracted_notes:
        st.subheader(f"Extracted Notes ({len(result.extracted_notes)})")
        for note in result.extracted_notes:
            with st.expander(f"Note {note.note_number}: {note.note_title}"):
                st.write(note.summary)
                if note.sub_tables:
                    for st_tbl in note.sub_tables:
                        if st_tbl.table_title:
                            st.caption(st_tbl.table_title)
                        if st_tbl.rows:
                            note_df = pd.DataFrame(
                                [{"Label": r.label, **r.values} for r in st_tbl.rows]
                            )
                            st.dataframe(note_df, use_container_width=True)

    # ── Download button ──────────────────────────────────────────────────
    st.divider()
    xlsx_bytes = st.session_state.get("xlsx_bytes", b"")
    if xlsx_bytes:
        st.download_button(
            label="Download Raw Extraction XLSX",
            data=xlsx_bytes,
            file_name=f"{uploaded.name.replace('.pdf', '')}_extracted.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

else:
    # Empty state
    st.info("Upload a PDF financial statement to begin extraction.")

    st.markdown("""
    **How it works:**
    1. **S2 — Page Classification:** Each page is classified as digital, scanned, or hybrid
    2. **S3 — Page Filtering:** Financial pages are grouped by statement type
    3. **S5 — Row Extraction:** Claude AI extracts financial line items from each page
    4. **S6 — Note Extraction:** Referenced footnotes are parsed and structured
    5. **Export:** Results are written to an Excel file with a Raw Extraction tab
    """)
