from __future__ import annotations

from pathlib import Path
import tempfile
import time
import traceback

import pandas as pd
import streamlit as st

from src.config import APP_NAME, CONTENT_REVIEW_COLUMNS, FILE_REVIEW_COLUMNS, PDFCheckConfig
from src.config import OCR_CONTENT_REVIEW_COLUMNS
from src.exporter import export_review_to_excel
from src.matcher import build_file_review, build_pdf_content_review
from src.parser_excel import read_claims_excel
from src.parser_file_list import (
    build_file_entry,
    combine_file_entries,
    empty_file_entries,
    parse_file_list_text,
    scan_pdf_folder,
)
from src.pdf_checker import check_pdf
from src.pdf_parallel import resolve_pdf_worker_count, check_pdfs_parallel


st.set_page_config(page_title=APP_NAME, layout="wide")


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total} detik"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} menit {secs} detik"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} jam {minutes} menit {secs} detik"


def _refresh_duration_status(duration_status, started_at: float) -> None:
    if duration_status is not None:
        duration_status.info(
            f"Durasi berjalan: {_format_elapsed(time.perf_counter() - started_at)}"
        )


def main() -> None:
    st.title(APP_NAME)
    st.caption("Review lokal berkas klaim JKN sebelum pengajuan.")

    _inject_layout_styles()
    left, right = st.columns(2, gap="large")

    with left:
        _render_panel_header(
            "Review Jumlah Berkas",
            "Cocokkan daftar klaim Excel dengan indeks file PDF dari TXT atau folder lokal.",
            "file-panel",
        )
        file_excel = st.file_uploader(
            "Excel daftar klaim",
            type=["xlsx", "xls"],
            key="file_review_excel",
        )
        file_source_mode = st.radio(
            "Sumber data PDF",
            ["list_berkas_klaim.txt", "Folder Berkas Lokal"],
            horizontal=True,
            key="file_review_source_mode",
        )
        file_list = None
        file_folder_path = ""
        if file_source_mode == "list_berkas_klaim.txt":
            st.caption("Command Prompt untuk membuat list berkas klaim:")
            st.code("dir /s /b > list_berkas_klaim.txt", language="bat")
            file_list = st.file_uploader(
                "list_berkas_klaim.txt",
                type=["txt"],
                key="file_review_list",
            )
        else:
            file_folder_path = st.text_input(
                "Folder Berkas Lokal",
                key="file_review_folder",
                placeholder=r"Contoh: D:\Casemix\Pending\2026",
            )
        if st.button(
            "Jalankan Review Jumlah Berkas",
            type="primary",
            width="stretch",
            key="run_file_review",
        ):
            _run_file_review(
                excel_file=file_excel,
                source_mode=file_source_mode,
                file_list=file_list,
                folder_path=file_folder_path,
            )
        _render_file_panel()

    with right:
        _render_panel_header(
            "Review Isi Berkas",
            "Periksa kelengkapan komponen di dalam PDF klaim.",
            "content-panel",
        )
        content_uploaded_pdfs = st.file_uploader(
            "PDF berkas klaim",
            type=["pdf"],
            accept_multiple_files=True,
            key="content_review_pdfs",
        )
        content_folder_path = st.text_input(
            "Folder PDF lokal (opsional)",
            key="content_review_folder",
        )
        content_scan_mode = st.radio(
            "Mode scan isi PDF",
            ["Tanpa OCR", "Dengan OCR"],
            horizontal=True,
            key="content_review_scan_mode",
        )
        if st.button(
            "Jalankan Review Isi Berkas",
            width="stretch",
            key="run_content_review",
        ):
            _run_content_review(
                uploaded_pdfs=content_uploaded_pdfs,
                folder_path=content_folder_path,
                config=_automatic_pdf_check_config(
                    use_ocr=content_scan_mode == "Dengan OCR",
                ),
            )
        _render_content_panel()


def _inject_layout_styles() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px;
        }
        .casemix-panel-header {
            border-radius: 8px;
            color: white;
            margin: 0 0 1rem 0;
            padding: 1rem 1.1rem;
        }
        .casemix-panel-header h2 {
            color: white;
            font-size: 1.45rem;
            line-height: 1.2;
            margin: 0 0 .35rem 0;
            padding: 0;
        }
        .casemix-panel-header p {
            color: rgba(255, 255, 255, .9);
            font-size: .92rem;
            margin: 0;
        }
        .file-panel {
            background: #0f766e;
        }
        .content-panel {
            background: #b45309;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_panel_header(title: str, subtitle: str, class_name: str) -> None:
    st.markdown(
        f"""
        <div class="casemix-panel-header {class_name}">
            <h2>{title}</h2>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _automatic_pdf_check_config(*, use_ocr: bool = False) -> PDFCheckConfig:
    return PDFCheckConfig(
        min_page_text_chars=40,
        min_pdf_text_chars=80,
        use_ocr=use_ocr,
    )


def _run_file_review(
    *,
    excel_file,
    source_mode: str,
    file_list,
    folder_path: str,
) -> None:
    if excel_file is None:
        st.error("Upload Excel daftar klaim terlebih dahulu.")
        return
    if source_mode == "list_berkas_klaim.txt" and file_list is None:
        st.error("Upload list_berkas_klaim.txt terlebih dahulu.")
        return
    if source_mode == "Folder Berkas Lokal" and not folder_path.strip():
        st.error("Isi path Folder Berkas Lokal terlebih dahulu.")
        return

    try:
        started_at = time.perf_counter()
        duration_status = st.empty()
        duration_status.info(f"Durasi berjalan: {_format_elapsed(0)}")
        with st.spinner("Mengecek jumlah berkas..."):
            excel_result = read_claims_excel(excel_file)
            file_entries = _build_file_review_entries(
                source_mode=source_mode,
                file_list=file_list,
                folder_path=folder_path,
            )
            _show_file_input_warnings(
                excel_result.warnings,
                source_mode=source_mode,
                file_list=file_list,
                folder_path=folder_path,
                file_entries=file_entries,
            )
            duration_status.info(
                f"Durasi berjalan: {_format_elapsed(time.perf_counter() - started_at)}"
            )
            review_df, orphan_df, summary = build_file_review(excel_result.df, file_entries)
            export_bytes = export_review_to_excel(
                review_df,
                orphan_df,
                summary,
                review_sheet_name="review_jumlah_berkas",
            )

        elapsed = time.perf_counter() - started_at
        duration_status.empty()
        st.session_state["file_review_df"] = review_df
        st.session_state["file_orphan_df"] = orphan_df
        st.session_state["file_summary"] = summary
        st.session_state["file_export_bytes"] = export_bytes
        st.session_state["file_review_duration_sec"] = elapsed
        st.session_state["last_review_kind"] = "file"
        st.success(f"Review jumlah berkas selesai ({_format_elapsed(elapsed)}).")
    except Exception as exc:
        st.error(f"Review jumlah berkas gagal: {exc}")
        with st.expander("Detail teknis"):
            st.code(traceback.format_exc())


def _run_content_review(
    *,
    uploaded_pdfs,
    folder_path: str,
    config: PDFCheckConfig,
) -> None:
    if not uploaded_pdfs and not folder_path.strip():
        st.error("Upload PDF atau isi folder PDF lokal terlebih dahulu.")
        return

    try:
        started_at = time.perf_counter()
        duration_status = st.empty()
        duration_status.info(f"Durasi berjalan: {_format_elapsed(0)}")
        with st.spinner("Mengecek isi berkas PDF..."):
            with tempfile.TemporaryDirectory(prefix="casemix_claim_pdf_") as temp_dir:
                upload_entries = _save_uploaded_pdfs(
                    uploaded_pdfs or [],
                    temp_dir=temp_dir,
                    is_index_source=False,
                )
                folder_entries = _scan_folder_entries(
                    folder_path=folder_path,
                    is_index_source=False,
                )
                file_entries = combine_file_entries([upload_entries, folder_entries])
                if file_entries.empty:
                    duration_status.empty()
                    st.error("Tidak ada PDF yang bisa diperiksa dari input review isi berkas.")
                    return
                _refresh_duration_status(duration_status, started_at)
                pdf_results, _ = _check_all_content_pdfs(
                    file_entries=file_entries,
                    config=config,
                    started_at=started_at,
                    duration_status=duration_status,
                )
                _refresh_duration_status(duration_status, started_at)
                review_df, orphan_df, summary = build_pdf_content_review(
                    file_entries,
                    pdf_results,
                    use_ocr=config.use_ocr,
                )
                export_bytes = export_review_to_excel(
                    review_df,
                    orphan_df,
                    summary,
                    review_sheet_name="review_isi_berkas",
                )

        elapsed = time.perf_counter() - started_at
        duration_status.empty()
        st.session_state["content_review_df"] = review_df
        st.session_state["content_orphan_df"] = orphan_df
        st.session_state["content_summary"] = summary
        st.session_state["content_export_bytes"] = export_bytes
        st.session_state["content_use_ocr"] = config.use_ocr
        st.session_state["content_review_duration_sec"] = elapsed
        st.session_state["last_review_kind"] = "content"
        st.success(f"Review isi berkas selesai ({_format_elapsed(elapsed)}).")
    except Exception as exc:
        st.error(f"Review isi berkas gagal: {exc}")
        with st.expander("Detail teknis"):
            st.code(traceback.format_exc())


def _show_file_input_warnings(
    excel_warnings: list[str],
    *,
    source_mode: str,
    file_list,
    folder_path: str,
    file_entries: pd.DataFrame,
) -> None:
    for warning in excel_warnings:
        st.warning(warning)
    if source_mode == "list_berkas_klaim.txt" and file_list is not None and file_entries.empty:
        st.warning("list_berkas_klaim.txt tidak menghasilkan data PDF.")
    if source_mode == "Folder Berkas Lokal" and folder_path.strip() and file_entries.empty:
        st.warning("Folder Berkas Lokal tidak menghasilkan data PDF.")


def _build_file_review_entries(
    *,
    source_mode: str,
    file_list,
    folder_path: str,
) -> pd.DataFrame:
    if source_mode == "Folder Berkas Lokal":
        return _scan_folder_entries(
            folder_path=folder_path,
            is_index_source=True,
        )
    return _parse_uploaded_file_list(file_list)


def _parse_uploaded_file_list(file_list) -> pd.DataFrame:
    if file_list is None:
        return empty_file_entries()
    raw_text = file_list.getvalue().decode("utf-8", errors="ignore")
    result = parse_file_list_text(raw_text, source_name=file_list.name)
    for warning in result.warnings:
        st.warning(warning)
    return result.df


def _save_uploaded_pdfs(uploaded_pdfs, *, temp_dir: str, is_index_source: bool) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    temp_root = Path(temp_dir)
    for index, uploaded_pdf in enumerate(uploaded_pdfs):
        display_path = uploaded_pdf.name
        safe_name = Path(display_path.replace("\\", "/")).name or f"uploaded_{index}.pdf"
        local_path = temp_root / f"{index:04d}_{safe_name}"
        local_path.write_bytes(uploaded_pdf.getvalue())
        rows.append(
            build_file_entry(
                display_path,
                local_path=str(local_path),
                source="upload",
                is_index_source=is_index_source,
                is_content_source=True,
                note="PDF upload.",
            )
        )
    if not rows:
        return empty_file_entries()
    return pd.DataFrame(rows)


def _scan_folder_entries(folder_path: str, *, is_index_source: bool) -> pd.DataFrame:
    result = scan_pdf_folder(
        folder_path.strip(),
        source_name="folder",
        is_index_source=is_index_source,
    )
    for warning in result.warnings:
        st.warning(warning)
    return result.df


def _check_relevant_pdfs(
    *,
    claims_df: pd.DataFrame,
    file_entries: pd.DataFrame,
    config: PDFCheckConfig,
) -> dict[str, object]:
    if file_entries.empty:
        return {}

    valid_claim_seps = set(
        claims_df.loc[claims_df["_sep_valid"].astype(bool), "_no_sep_normalized"].astype(str)
    )
    index_entries = file_entries[file_entries["is_index_source"].astype(bool)]
    matched_seps = set(index_entries[index_entries["no_sep"].isin(valid_claim_seps)]["no_sep"])
    content_entries = file_entries[
        file_entries["is_content_source"].astype(bool)
        & file_entries["no_sep"].isin(matched_seps)
        & (file_entries["local_path"].astype(str) != "")
    ].copy()

    if content_entries.empty:
        return {}

    content_entries = _one_content_source_per_sep(content_entries)
    pdf_results: dict[str, object] = {}
    progress = st.progress(0)
    status = st.empty()
    total = len(content_entries)

    for idx, (_, entry) in enumerate(content_entries.iterrows(), start=1):
        status.text(f"Memeriksa PDF {idx}/{total}: {entry['file_name']}")
        result = check_pdf(
            source_id=str(entry["source_id"]),
            local_path=str(entry["local_path"]),
            config=config,
        )
        pdf_results[str(entry["source_id"])] = result
        progress.progress(idx / total)

    status.empty()
    progress.empty()
    return pdf_results


def _check_all_content_pdfs(
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
        return _format_elapsed(time.perf_counter() - pdf_started_at)

    def refresh_duration() -> None:
        _refresh_duration_status(duration_status, pdf_started_at)

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


def _one_content_source_per_sep(content_entries: pd.DataFrame) -> pd.DataFrame:
    source_rank = {"folder": 0, "upload": 1}
    ranked = content_entries.copy()
    ranked["_source_rank"] = ranked["source"].map(source_rank).fillna(2)
    ranked = ranked.sort_values(["no_sep", "_source_rank", "display_path"])
    return ranked.drop_duplicates(subset=["no_sep"], keep="first").drop(columns=["_source_rank"])


def _render_results() -> None:
    panels = []
    if st.session_state.get("file_review_df") is not None:
        panels.append(("file", _render_file_panel))
    if st.session_state.get("content_review_df") is not None:
        panels.append(("content", _render_content_panel))
    if not panels:
        return

    if st.session_state.get("last_review_kind") == "content":
        panels = sorted(panels, key=lambda item: 0 if item[0] == "content" else 1)
    elif st.session_state.get("last_review_kind") == "file":
        panels = sorted(panels, key=lambda item: 0 if item[0] == "file" else 1)

    st.header("Hasil Review")
    for index, (_, render_panel) in enumerate(panels):
        if index:
            st.divider()
        render_panel()


def _render_file_panel() -> None:
    if st.session_state.get("file_review_df") is None:
        return
    st.subheader("Hasil Review Jumlah Berkas")
    _render_review_panel(
        review_df=st.session_state.get("file_review_df"),
        summary=st.session_state.get("file_summary"),
        orphan_df=st.session_state.get("file_orphan_df"),
        export_bytes=st.session_state.get("file_export_bytes"),
        empty_columns=FILE_REVIEW_COLUMNS,
        empty_summary=_empty_file_summary(),
        status_options=["Semua", "Lengkap", "Kurang PDF", "Salah Folder", "Duplikat", "Perlu Review Manual"],
        export_file_name="hasil_review_jumlah_berkas.xlsx",
        orphan_title="PDF di folder/list tetapi tidak ada di Excel",
        widget_prefix="file_review",
        duration_sec=st.session_state.get("file_review_duration_sec"),
    )


def _render_content_panel() -> None:
    if st.session_state.get("content_review_df") is None:
        return
    use_ocr = bool(st.session_state.get("content_use_ocr", False))
    st.subheader("Hasil Review Isi Berkas")
    _render_review_panel(
        review_df=st.session_state.get("content_review_df"),
        summary=st.session_state.get("content_summary"),
        orphan_df=st.session_state.get("content_orphan_df"),
        export_bytes=st.session_state.get("content_export_bytes"),
        empty_columns=OCR_CONTENT_REVIEW_COLUMNS if use_ocr else CONTENT_REVIEW_COLUMNS,
        empty_summary=_empty_ocr_content_summary() if use_ocr else _empty_content_summary(),
        status_options=["Semua", "Lengkap", "Kurang Komponen", "Perlu Review Manual"],
        export_file_name="hasil_review_isi_berkas_ocr.xlsx" if use_ocr else "hasil_review_isi_berkas.xlsx",
        orphan_title="PDF di folder/list tetapi tidak ada di Excel",
        widget_prefix="content_review",
        duration_sec=st.session_state.get("content_review_duration_sec"),
    )


def _render_review_panel(
    *,
    review_df,
    summary,
    orphan_df,
    export_bytes,
    empty_columns: list[str],
    empty_summary: dict[str, int],
    status_options: list[str],
    export_file_name: str,
    orphan_title: str,
    widget_prefix: str,
    duration_sec: float | None = None,
) -> None:
    has_results = review_df is not None and summary is not None
    if not has_results:
        review_df = pd.DataFrame(columns=empty_columns)
        orphan_df = pd.DataFrame(columns=["No SEP", "Path File", "Tanggal Folder", "Sumber", "Catatan"])
        summary = empty_summary

    if duration_sec is not None:
        st.caption(f"Durasi review terakhir: **{_format_elapsed(duration_sec)}**")

    summary_items = list(summary.items())
    for start in range(0, len(summary_items), 4):
        metric_cols = st.columns(4)
        for col, (label, value) in zip(metric_cols, summary_items[start : start + 4]):
            col.metric(label, value)

    st.divider()
    left, right = st.columns([3, 1])
    with left:
        selected_status = st.selectbox(
            "Filter Status Akhir",
            status_options,
            key=f"{widget_prefix}_status_filter",
        )
    with right:
        st.download_button(
            "Export Excel",
            data=export_bytes or b"",
            file_name=export_file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            disabled=not has_results,
            key=f"{widget_prefix}_export",
        )

    filtered_df = review_df
    if selected_status != "Semua":
        filtered_df = review_df[review_df["Status Akhir"] == selected_status]

    st.dataframe(filtered_df, width="stretch", hide_index=True)

    with st.expander(f"{orphan_title} ({len(orphan_df)})"):
        st.dataframe(orphan_df, width="stretch", hide_index=True)


def _empty_file_summary() -> dict[str, int]:
    return {
        "Total klaim": 0,
        "Total SEP valid": 0,
        "PDF ditemukan": 0,
        "Belum ada PDF": 0,
        "Salah folder": 0,
        "Duplikat": 0,
        "PDF tanpa Excel": 0,
        "Jumlah lengkap": 0,
    }


def _empty_content_summary() -> dict[str, int]:
    return {
        "Total PDF": 0,
        "PDF dibaca": 0,
        "SEP cocok di PDF": 0,
        "LIP": 0,
        "Rincian tagihan": 0,
        "Hasil scan": 0,
        "Kurang komponen": 0,
        "Perlu review manual": 0,
        "Isi lengkap": 0,
    }


def _empty_ocr_content_summary() -> dict[str, int]:
    return {
        "Total PDF": 0,
        "PDF dibaca": 0,
        "SEP cocok di PDF": 0,
        "LIP": 0,
        "Rincian tagihan": 0,
        "Resume Medis": 0,
        "Triage": 0,
        "SPRI": 0,
        "Hasil Pemeriksaan": 0,
        "Radiologi": 0,
        "Kurang komponen": 0,
        "Perlu review manual": 0,
        "Isi lengkap": 0,
    }


if __name__ == "__main__":
    main()
