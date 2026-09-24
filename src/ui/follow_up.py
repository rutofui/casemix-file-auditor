from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import is_valid_sep, normalize_sep
from src.exporter import export_review_to_excel
from src.ui.results import input_signature, review_is_current


def build_follow_up(frames: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    rows: dict[str, dict[str, str]] = {}
    for frame_index, (source, frame) in enumerate(frames):
        if frame is None or frame.empty:
            continue
        for index, claim in frame.iterrows():
            if claim.get("Status Akhir") == "Lengkap":
                continue
            sep = normalize_sep(claim.get("No SEP", claim.get("SEP", "")))
            key = sep if is_valid_sep(sep) else f"SEP perlu koreksi ({source}, tabel {frame_index + 1}, baris {index + 1}): {sep}"
            row = rows.setdefault(key, {
                "No SEP": key, "Temuan": "", "Petugas": "",
                "Catatan koreksi": "", "Status tindak lanjut": "Belum ditinjau",
            })
            detail = str(claim.get("Catatan", "") or claim.get("Temuan", "") or claim.get("Status Akhir", ""))
            if "Masalah" in claim:
                detail = f"{claim.get('Field', '')}: {claim['Masalah']}"
            finding = f"{source}: {detail}"
            if finding not in row["Temuan"].split("\n"):
                row["Temuan"] = "\n".join(filter(None, [row["Temuan"], finding]))
    return pd.DataFrame(rows.values(), columns=["No SEP", "Temuan", "Petugas", "Catatan koreksi", "Status tindak lanjut"])


def render_follow_up_tab() -> None:
    st.subheader("Tindak lanjut per SEP")
    st.caption("Gabungan temuan dari hasil terbaru di sesi ini. Status petugas tidak mengubah hasil pemeriksaan otomatis.")
    frames = []
    contexts = []
    sources = [("eklaim", "Analisis TXT"), ("file", "Jumlah berkas"), ("content", "Isi berkas")]
    for prefix, label in sources:
        if not review_is_current(prefix):
            st.caption(f"{label}: belum tersedia atau perlu dijalankan ulang.")
            continue
        context = st.session_state[f"{prefix}_result_context"]
        contexts.append(context)
        st.caption(f"{label}: {context['source']} | {context['time']}")
        if prefix == "eklaim":
            analysis = st.session_state["eklaim_analysis"]
            for field in (
                "invalid_ptd_df", "invalid_numeric_df", "completeness_df",
                "severity_high_los_low_df", "severity_low_los_high_df",
                "intensive_care_df", "grouper_gt_rs_df", "selisih_gt_30pct_df",
            ):
                frames.append((label, getattr(analysis, field, pd.DataFrame())))
        else:
            frames.append((label, st.session_state.get(f"{prefix}_review_df")))
            if prefix == "file":
                frames.append(("PDF di luar acuan", st.session_state.get("file_orphan_df")))
    findings = build_follow_up(frames)
    if findings.empty:
        st.info("Belum ada temuan untuk ditindaklanjuti dari hasil yang tersedia.")
        return

    revision = input_signature(contexts, findings.to_dict("records"))
    editor_key = f"follow_up_editor_{revision}"
    if st.session_state.get("follow_up_revision") != revision or editor_key not in st.session_state:
        saved = st.session_state.get("follow_up_saved", pd.DataFrame())
        if not saved.empty:
            saved = saved.set_index("No SEP")
            for index, row in findings.iterrows():
                sep = row["No SEP"]
                if sep in saved.index and saved.loc[sep, "Temuan"] == row["Temuan"]:
                    for column in ["Petugas", "Catatan koreksi", "Status tindak lanjut"]:
                        findings.at[index, column] = saved.loc[sep, column]
        st.session_state["follow_up_base"] = findings
        st.session_state["follow_up_revision"] = revision

    # ponytail: catatan bertahan per sesi; tambah penyimpanan lokal saat perlu dilanjutkan lintas sesi.
    st.caption("Catatan tersimpan selama sesi ini. Unduh Excel sebelum menutup aplikasi. Temuan baru perlu ditinjau ulang.")
    edited = st.data_editor(
        st.session_state["follow_up_base"],
        key=editor_key,
        hide_index=True,
        disabled=["No SEP", "Temuan"],
        column_config={
            "Status tindak lanjut": st.column_config.SelectboxColumn(
                options=["Belum ditinjau", "Dalam perbaikan", "Selesai"], required=True,
            ),
        },
    )
    saved = st.session_state.get("follow_up_saved", pd.DataFrame())
    st.session_state["follow_up_saved"] = pd.concat(
        [saved.loc[~saved["No SEP"].isin(edited["No SEP"])] if not saved.empty else saved, edited],
        ignore_index=True,
    )
    st.download_button(
        "Unduh tindak lanjut Excel",
        export_review_to_excel(
            edited, None,
            {"SEP dengan temuan": len(edited), "Selesai": int((edited["Status tindak lanjut"] == "Selesai").sum())},
            review_sheet_name="tindak_lanjut",
        ),
        file_name="tindak_lanjut_casemix.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
