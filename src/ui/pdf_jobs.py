from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from src.config import PDFCheckConfig
from src.pdf_parallel import check_pdfs_parallel, resolve_pdf_worker_count
from src.ui.layout import format_elapsed, refresh_duration_status


def check_all_content_pdfs(
    *,
    file_entries: pd.DataFrame,
    config: PDFCheckConfig,
    started_at: float | None = None,
    duration_status=None,
) -> tuple[dict[str, object], float]:
    pdf_started_at = started_at if started_at is not None else time.perf_counter()
    if file_entries.empty:
        return {}, 0.0

    content_entries = file_entries[
        file_entries["is_content_source"].astype(bool)
        & (file_entries["local_path"].astype(str) != "")
    ].copy()
    if content_entries.empty:
        return {}, time.perf_counter() - pdf_started_at

    progress = st.progress(0)
    status = st.empty()
    total = len(content_entries)
    worker_count = resolve_pdf_worker_count(total, use_ocr=config.use_ocr)
    file_names_by_source_id = {
        str(entry["source_id"]): str(entry["file_name"])
        for _, entry in content_entries.iterrows()
    }

    mode_label = "OCR" if config.use_ocr else "tanpa OCR"

    def elapsed_label() -> str:
        return format_elapsed(time.perf_counter() - pdf_started_at)

    def refresh_duration() -> None:
        refresh_duration_status(duration_status, pdf_started_at)

    refresh_duration()
    status.text(
        f"Memeriksa {total} PDF {mode_label} dengan {worker_count} worker... "
        f"· Durasi: {elapsed_label()}"
    )

    def update_progress(completed: int, total_items: int, source_id: str) -> None:
        file_name = file_names_by_source_id.get(source_id, source_id)
        status.text(
            f"Memeriksa PDF {completed}/{total_items}: {file_name} "
            f"· Durasi: {elapsed_label()}"
        )
        progress.progress(completed / total_items)
        refresh_duration()

    jobs = [
        (str(entry["source_id"]), str(entry["local_path"]))
        for _, entry in content_entries.iterrows()
    ]
    pdf_results = check_pdfs_parallel(
        jobs,
        config,
        progress_callback=update_progress,
        tick_callback=refresh_duration if duration_status is not None else None,
    )

    elapsed = time.perf_counter() - pdf_started_at
    refresh_duration()
    status.text(f"Pemeriksaan PDF selesai · Durasi: {elapsed_label()}")
    progress.progress(1.0)
    status.empty()
    progress.empty()
    return pdf_results, elapsed
