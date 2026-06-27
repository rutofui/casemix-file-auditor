from __future__ import annotations

import time

import streamlit as st

from src.config import PDFCheckConfig
from src.version_check import format_version_datetime as _format_version_datetime


def format_version_datetime(value: str) -> str:
    return _format_version_datetime(value)


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total} detik"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} menit {secs} detik"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} jam {minutes} menit {secs} detik"


def refresh_duration_status(duration_status, started_at: float) -> None:
    if duration_status is not None:
        duration_status.info(
            f"Durasi berjalan: {format_elapsed(time.perf_counter() - started_at)}"
        )


def inject_layout_styles() -> None:
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
        .txt-panel {
            background: #1e40af;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_panel_header(title: str, subtitle: str, class_name: str) -> None:
    st.markdown(
        f"""
        <div class="casemix-panel-header {class_name}">
            <h2>{title}</h2>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def automatic_pdf_check_config(*, use_ocr: bool = False) -> PDFCheckConfig:
    return PDFCheckConfig(
        min_page_text_chars=40,
        min_pdf_text_chars=80,
        use_ocr=use_ocr,
    )
