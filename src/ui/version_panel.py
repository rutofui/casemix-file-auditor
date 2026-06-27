from __future__ import annotations

import streamlit as st

from src.ui.layout import format_version_datetime
from src.version_check import (
    UpdateCheckResult,
    check_for_updates,
    run_update_script,
)


def render_version_panel() -> None:
    _ensure_auto_update_check()
    result: UpdateCheckResult | None = st.session_state.get("update_check_result")

    with st.container(border=True):
        left, right = st.columns([3, 1])
        with left:
            _render_version_text(result)
            if result and result.update_available and result.remote is not None:
                st.warning(
                    "Versi baru tersedia di GitHub: "
                    f"**{format_version_datetime(result.remote.built_at)}**"
                )
            elif result and result.error:
                st.caption(result.error)

        with right:
            update_available = bool(result and result.update_available)
            button_label = "Update" if update_available else "Check for Updates"
            button_type = "primary" if update_available else "secondary"
            if st.button(button_label, type=button_type, key="version_action_button", width="stretch"):
                if update_available:
                    _run_update_flow()
                else:
                    st.session_state["update_check_result"] = check_for_updates(force=True)
                    st.rerun()

    if st.session_state.get("update_run_output"):
        with st.expander("Log pembaruan terakhir", expanded=not st.session_state.get("update_run_success", False)):
            st.code(st.session_state["update_run_output"])


def _ensure_auto_update_check() -> None:
    if st.session_state.get("update_check_done"):
        return
    st.session_state["update_check_done"] = True
    st.session_state["update_check_result"] = check_for_updates(force=True)
    st.session_state["update_check_timestamp"] = st.session_state.get("_streamlit_time", 0)


def _render_version_text(result: UpdateCheckResult | None) -> None:
    if result is None or result.local is None:
        st.caption("Versi terpasang: tidak terdeteksi")
        return
    st.caption(
        f"Versi terpasang: **{format_version_datetime(result.local.built_at)}** "
        f"(`{result.local.commit_sha}`)"
    )


def _run_update_flow() -> None:
    with st.spinner("Memperbarui aplikasi..."):
        run_result = run_update_script()
    st.session_state["update_run_output"] = run_result.output or run_result.error
    st.session_state["update_run_success"] = run_result.success
    if run_result.success:
        st.session_state["update_check_result"] = check_for_updates(force=True)
        st.success("Pembaruan selesai. Tutup aplikasi ini, lalu jalankan ulang `run_app.bat`.")
        st.rerun()
    else:
        st.error(run_result.error or "Pembaruan gagal. Lihat log di bawah.")
