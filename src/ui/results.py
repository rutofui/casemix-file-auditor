from __future__ import annotations

from datetime import datetime
import hashlib
import json

import pandas as pd
import streamlit as st

from src.ui.layout import format_elapsed


def input_signature(*values) -> str:
    # ponytail: tracks selected inputs, not folder contents; rerun after disk changes.
    def identity(value):
        if isinstance(value, (list, tuple)):
            return [identity(item) for item in value]
        if hasattr(value, "getvalue"):
            file_id = getattr(value, "file_id", None)
            return [getattr(value, "name", ""), file_id or hashlib.sha256(value.getvalue()).hexdigest()]
        return value

    return hashlib.sha256(json.dumps(identity(values), ensure_ascii=True).encode()).hexdigest()


def set_current_input(prefix: str, signature: str) -> None:
    st.session_state[f"{prefix}_current_input"] = signature


def begin_review(prefix: str) -> None:
    st.session_state.pop(f"{prefix}_result_context", None)


def finish_review(prefix: str, signature: str, source_label: str) -> None:
    st.session_state[f"{prefix}_result_context"] = {
        "signature": signature,
        "source": source_label,
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    set_current_input(prefix, signature)


def review_is_current(prefix: str) -> bool:
    context = st.session_state.get(f"{prefix}_result_context")
    return bool(context and context["signature"] == st.session_state.get(f"{prefix}_current_input"))


def render_result_context(prefix: str) -> bool:
    if not review_is_current(prefix):
        st.warning("Input berubah atau proses terakhir gagal. Hasil sebelumnya kedaluwarsa; jalankan ulang sebelum melihat atau mengekspor hasil.")
        return False
    context = st.session_state[f"{prefix}_result_context"]
    st.caption(f"Sumber: {context['source']} | Diproses: {context['time']}")
    return True


def empty_file_summary() -> dict[str, int]:
    return {
        "Total klaim": 0,
        "Total SEP valid": 0,
        "PDF ditemukan": 0,
        "Belum ada PDF": 0,
        "Salah folder": 0,
        "Duplikat": 0,
        "PDF di luar daftar acuan": 0,
        "Jumlah lengkap": 0,
    }


def empty_file_icd_summary() -> dict[str, int]:
    summary = empty_file_summary()
    summary["Kode ICD tidak sesuai"] = 0
    return summary


def empty_file_txt_summary() -> dict[str, int]:
    summary = empty_file_icd_summary()
    summary["Data LIP tidak sesuai"] = 0
    return summary


def empty_content_summary() -> dict[str, int]:
    return {
        "Total PDF": 0,
        "PDF dibaca": 0,
        "SEP terdeteksi di PDF": 0,
        "LIP": 0,
        "Rincian tagihan": 0,
        "Hasil scan": 0,
        "Kurang komponen": 0,
        "Perlu review manual": 0,
        "Isi lengkap": 0,
    }


def empty_ocr_content_summary() -> dict[str, int]:
    return {
        "Total PDF": 0,
        "PDF dibaca": 0,
        "SEP terdeteksi di PDF": 0,
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


def render_review_panel(
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
    section_title: str = "Hasil Review",
    duration_sec: float | None = None,
) -> None:
    has_results = review_df is not None and summary is not None
    if not has_results:
        review_df = pd.DataFrame(columns=empty_columns)
        orphan_df = pd.DataFrame(columns=["No SEP", "Path File", "Tanggal Folder", "Sumber", "Catatan"])
        summary = empty_summary

    if duration_sec is not None:
        st.caption(f"Durasi review terakhir: **{format_elapsed(duration_sec)}**")

    summary_items = list(summary.items())
    for start in range(0, len(summary_items), 4):
        metric_cols = st.columns(4)
        for col, (label, value) in zip(metric_cols, summary_items[start : start + 4]):
            col.metric(label, value)

    st.divider()

    st.subheader(section_title)

    left, right = st.columns([3, 1])
    with left:
        selected_status = st.selectbox(
            "Filter temuan" if "Temuan" in review_df.columns else "Filter Status Akhir",
            status_options,
            key=f"{widget_prefix}_status_filter",
            disabled=not has_results,
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
    if has_results and selected_status != "Semua":
        matches = review_df["Status Akhir"] == selected_status
        if "Temuan" in review_df.columns:
            matches |= review_df["Temuan"].fillna("").str.split("; ").map(lambda items: selected_status in items)
        filtered_df = review_df[matches]

    st.dataframe(filtered_df, width="stretch", hide_index=True)

    if orphan_df is not None and not orphan_df.empty:
        with st.expander(f"{orphan_title} ({len(orphan_df)})"):
            st.dataframe(orphan_df, width="stretch", hide_index=True)
