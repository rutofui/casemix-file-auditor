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
        /* ── Panel header ── */
        .casemix-panel-header {
            border-radius: 10px;
            color: white;
            margin: 0 0 1.25rem 0;
            padding: 1rem 1.25rem;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.13);
        }
        .casemix-panel-header h2 {
            color: white;
            font-size: 1.35rem;
            font-weight: 700;
            line-height: 1.25;
            margin: 0 0 0.25rem 0;
            padding: 0;
        }
        .casemix-panel-header p {
            color: rgba(255, 255, 255, 0.88);
            font-size: 0.88rem;
            margin: 0;
        }
        .file-panel    { background: linear-gradient(130deg, #0f766e 0%, #0d9488 100%); }
        .content-panel { background: linear-gradient(130deg, #9a3412 0%, #c2410c 100%); }
        .txt-panel     { background: linear-gradient(130deg, #1e3a8a 0%, #2563eb 100%); }
        .merge-panel   { background: linear-gradient(130deg, #365314 0%, #65a30d 100%); }

        /* ── Metric cards ── */
        div[data-testid="metric-container"] {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 0.65rem 0.9rem;
        }
        div[data-testid="stMetricLabel"] p {
            font-size: 0.78rem;
            color: #64748b;
            font-weight: 500;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.45rem;
            font-weight: 700;
        }

        /* ── Bordered container (version panel) ── */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px;
            border-color: #e2e8f0 !important;
        }

        /* ── Active tab ── */
        button[data-baseweb="tab"] {
            font-size: 0.9rem;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            font-weight: 700;
        }

        /* ── Expanders ── */
        div[data-testid="stExpander"] {
            border: 1px solid #e2e8f0 !important;
            border-radius: 8px !important;
        }
        div[data-testid="stExpander"] summary p {
            font-weight: 600;
            font-size: 0.9rem;
        }

        /* ── Dividers ── */
        hr[data-testid="stDivider"] {
            margin: 0.5rem 0;
            border-color: #e2e8f0;
        }

        /* ── Success / Error / Warning boxes ── */
        div[data-testid="stAlert"] {
            border-radius: 8px;
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
