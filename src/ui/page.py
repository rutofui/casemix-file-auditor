from __future__ import annotations

import streamlit as st

from src.config import APP_NAME
from src.ui.content_review import render_content_review_tab
from src.ui.file_review import render_file_review_tab
from src.ui.follow_up import render_follow_up_tab
from src.ui.layout import inject_layout_styles
from src.ui.txt_analysis import render_txt_analysis_tab
from src.ui.version_panel import render_version_panel


def render_main_page() -> None:
    st.title(APP_NAME)
    st.caption("Review lokal berkas klaim JKN sebelum pengajuan.")

    inject_layout_styles()
    render_version_panel()

    tab_txt, tab_file, tab_content, tab_follow_up = st.tabs(
        [
            "Analisis TXT E-Klaim",
            "Review Jumlah Berkas",
            "Review Isi Berkas",
            "Tindak lanjut",
        ],
        on_change="rerun",
    )

    with tab_txt:
        render_txt_analysis_tab()

    with tab_file:
        render_file_review_tab()

    with tab_content:
        render_content_review_tab()

    if tab_follow_up.open:
        with tab_follow_up:
            render_follow_up_tab()
