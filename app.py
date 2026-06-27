from __future__ import annotations

import streamlit as st

from src.config import APP_NAME
from src.ui.page import render_main_page

st.set_page_config(page_title=APP_NAME, layout="wide")


def main() -> None:
    render_main_page()


if __name__ == "__main__":
    main()
