from __future__ import annotations

import tempfile
import time
import traceback

import streamlit as st

from src.config import CONTENT_COMPONENTS, CONTENT_REVIEW_PROFILES, OCR_CONTENT_REVIEW_COLUMNS, PDFCheckConfig
from src.exporter import export_review_to_excel
from src.matcher import build_pdf_content_review
from src.parser_file_list import combine_file_entries
from src.ui.file_inputs import save_uploaded_pdfs, scan_folder_entries
from src.ui.layout import automatic_pdf_check_config, format_elapsed, refresh_duration_status, render_panel_header
from src.ui.pdf_jobs import check_all_content_pdfs
from src.ui.results import (
    begin_review, empty_ocr_content_summary, finish_review, input_signature,
    render_result_context, render_review_panel, set_current_input,
)


def run_content_review(
    *,
    uploaded_pdfs,
    folder_path: str,
    config: PDFCheckConfig,
    required_components: list[str],
    profile: str,
) -> None:
    begin_review("content")
    if not uploaded_pdfs and not folder_path.strip():
        st.error("Upload PDF atau isi folder PDF lokal terlebih dahulu.")
        return

    try:
        started_at = time.perf_counter()
        duration_status = st.empty()
        duration_status.info(f"Durasi berjalan: {format_elapsed(0)}")
        with st.spinner("Mengecek isi berkas PDF..."):
            with tempfile.TemporaryDirectory(prefix="casemix_claim_pdf_") as temp_dir:
                upload_entries = save_uploaded_pdfs(
                    uploaded_pdfs or [],
                    temp_dir=temp_dir,
                    is_index_source=False,
                )
                folder_entries = scan_folder_entries(
                    folder_path=folder_path,
                    is_index_source=False,
                )
                file_entries = combine_file_entries([upload_entries, folder_entries])
                if file_entries.empty:
                    duration_status.empty()
                    st.error("Tidak ada PDF yang bisa diperiksa dari input review isi berkas.")
                    return
                refresh_duration_status(duration_status, started_at)
                pdf_results, _ = check_all_content_pdfs(
                    file_entries=file_entries,
                    config=config,
                    started_at=started_at,
                    duration_status=duration_status,
                )
                refresh_duration_status(duration_status, started_at)
                review_df, orphan_df, summary = build_pdf_content_review(
                    file_entries,
                    pdf_results,
                    use_ocr=config.use_ocr,
                    required_components=required_components,
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
        st.session_state["content_required_components"] = required_components
        source_label = ", ".join([pdf.name for pdf in uploaded_pdfs or []] + ([folder_path] if folder_path else []))
        finish_review(
            "content",
            input_signature(uploaded_pdfs or [], folder_path, config.use_ocr, profile, required_components),
            f"{source_label} | {profile} | {'OCR' if config.use_ocr else 'Tanpa OCR'}",
        )
        st.session_state["last_review_kind"] = "content"
        st.success(f"Review isi berkas selesai ({format_elapsed(elapsed)}).")
    except Exception as exc:
        st.error(f"Review isi berkas gagal: {exc}")
        with st.expander("Detail teknis"):
            st.code(traceback.format_exc())


def render_content_review_tab() -> None:
    render_panel_header(
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
    profile = st.selectbox("Jenis pelayanan", list(CONTENT_REVIEW_PROFILES), key="content_profile")
    core_components = CONTENT_COMPONENTS[:3]
    extra_components = st.multiselect(
        "Dokumen tambahan yang wajib untuk batch ini",
        CONTENT_COMPONENTS[3:],
        default=[item for item in CONTENT_REVIEW_PROFILES[profile] if item not in core_components],
        key=f"content_checklist_{profile}",
        help="Sesuaikan SOP dan kasus. Dokumen yang tidak dipilih diberi status Tidak berlaku.",
    )
    required_components = core_components + extra_components
    st.caption("SEP, LIP, dan rincian tagihan selalu diperiksa. Pisahkan batch bila persyaratan antar-kasus berbeda.")
    if content_scan_mode == "Dengan OCR":
        st.caption("OCR membaca bagian atas halaman scan; proses pertama memerlukan model OCR. Hasil deteksi tetap perlu verifikasi petugas.")
    else:
        st.caption("Tanpa OCR hanya membaca teks digital. Pilih Dengan OCR untuk membaca judul pada halaman scan.")
    st.caption("Setelah isi folder berubah, jalankan ulang pemeriksaan agar hasil terbaru.")
    set_current_input(
        "content",
        input_signature(content_uploaded_pdfs or [], content_folder_path, content_scan_mode == "Dengan OCR", profile, required_components),
    )
    if st.button(
        "Jalankan Review Isi Berkas",
        type="primary",
        width="stretch",
        key="run_content_review",
    ):
        run_content_review(
            uploaded_pdfs=content_uploaded_pdfs,
            folder_path=content_folder_path,
            config=automatic_pdf_check_config(
                use_ocr=content_scan_mode == "Dengan OCR",
            ),
            required_components=required_components,
            profile=profile,
        )
    render_content_panel()


def render_content_panel() -> None:
    if st.session_state.get("content_review_df") is None:
        return
    if not render_result_context("content"):
        return
    st.caption("Checklist wajib: " + ", ".join(st.session_state.get("content_required_components", [])))
    use_ocr = bool(st.session_state.get("content_use_ocr", False))
    render_review_panel(
        review_df=st.session_state.get("content_review_df"),
        summary=st.session_state.get("content_summary"),
        orphan_df=st.session_state.get("content_orphan_df"),
        export_bytes=st.session_state.get("content_export_bytes"),
        empty_columns=OCR_CONTENT_REVIEW_COLUMNS,
        empty_summary=empty_ocr_content_summary(),
        status_options=["Semua", "Lengkap", "Kurang Komponen", "Perlu Review Manual"],
        export_file_name="hasil_review_isi_berkas_ocr.xlsx" if use_ocr else "hasil_review_isi_berkas.xlsx",
        orphan_title="PDF yang perlu diperiksa terpisah",
        widget_prefix="content_review",
        section_title="Hasil Review Isi Berkas",
        duration_sec=st.session_state.get("content_review_duration_sec"),
    )
