from __future__ import annotations

import pandas as pd
import pytest

from src.config import (
    STATUS_FOLDER_SALAH,
    STATUS_FOLDER_SESUAI,
    STATUS_FOLDER_TIDAK_TERDETEKSI,
)
from src.matcher import (
    _day_from_date_value,
    _folder_status,
    build_orphan_pdf_table,
)


# ---------------------------------------------------------------------------
# _day_from_date_value
# ---------------------------------------------------------------------------


class TestDayFromDateValue:
    def test_iso_date_string(self):
        assert _day_from_date_value("2024-03-05") == "05"

    def test_iso_date_with_time(self):
        assert _day_from_date_value("2024-11-01T08:30:00") == "01"

    def test_slash_iso_format(self):
        assert _day_from_date_value("2024/07/15") == "15"

    def test_indonesian_date_format_dd_mm_yyyy(self):
        assert _day_from_date_value("05/03/2024") == "05"

    def test_day_31(self):
        assert _day_from_date_value("2024-01-31") == "31"

    def test_single_digit_day_is_zero_padded(self):
        assert _day_from_date_value("2024-03-07") == "07"

    def test_pandas_timestamp(self):
        ts = pd.Timestamp("2024-06-20")
        assert _day_from_date_value(ts) == "20"

    def test_none_returns_empty(self):
        assert _day_from_date_value(None) == ""

    def test_empty_string_returns_empty(self):
        assert _day_from_date_value("") == ""

    def test_whitespace_returns_empty(self):
        assert _day_from_date_value("   ") == ""

    def test_invalid_string_returns_empty(self):
        assert _day_from_date_value("bukan-tanggal") == ""

    def test_nat_returns_empty(self):
        assert _day_from_date_value(pd.NaT) == ""


# ---------------------------------------------------------------------------
# _folder_status
# ---------------------------------------------------------------------------


def _make_index(tanggal_folder_values: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"tanggal_folder": tanggal_folder_values})


class TestFolderStatus:
    def test_folder_sesuai_when_day_matches(self):
        matched = _make_index(["05", "05"])
        status, note = _folder_status("2024-03-05", matched)
        assert status == STATUS_FOLDER_SESUAI
        assert note == ""

    def test_folder_salah_when_day_differs(self):
        matched = _make_index(["10"])
        status, note = _folder_status("2024-03-05", matched)
        assert status == STATUS_FOLDER_SALAH
        assert "05" in note

    def test_tidak_terdeteksi_when_tanggal_pulang_invalid(self):
        matched = _make_index(["05"])
        status, note = _folder_status("bukan-tanggal", matched)
        assert status == STATUS_FOLDER_TIDAK_TERDETEKSI
        assert note

    def test_tidak_terdeteksi_when_tanggal_pulang_none(self):
        matched = _make_index(["05"])
        status, note = _folder_status(None, matched)
        assert status == STATUS_FOLDER_TIDAK_TERDETEKSI

    def test_tidak_terdeteksi_when_no_folder_dates(self):
        matched = _make_index([""])
        status, note = _folder_status("2024-03-05", matched)
        assert status == STATUS_FOLDER_TIDAK_TERDETEKSI
        assert note

    def test_tidak_terdeteksi_when_some_rows_have_empty_folder(self):
        matched = _make_index(["05", ""])
        status, note = _folder_status("2024-03-05", matched)
        assert status == STATUS_FOLDER_TIDAK_TERDETEKSI

    def test_salah_when_mixed_days_and_one_wrong(self):
        matched = _make_index(["05", "06"])
        status, note = _folder_status("2024-03-05", matched)
        assert status == STATUS_FOLDER_SALAH

    def test_sesuai_with_single_pdf(self):
        matched = _make_index(["31"])
        status, note = _folder_status("2024-01-31", matched)
        assert status == STATUS_FOLDER_SESUAI
        assert note == ""


# ---------------------------------------------------------------------------
# build_orphan_pdf_table
# ---------------------------------------------------------------------------


def _make_entries(rows: list[dict]) -> pd.DataFrame:
    cols = ["no_sep", "display_path", "tanggal_folder", "source"]
    return pd.DataFrame(rows, columns=cols)


class TestBuildOrphanPdfTable:
    def test_pdf_not_in_excel_is_orphan(self):
        entries = _make_entries([
            {"no_sep": "0132R0010101V000001", "display_path": "/path/01/sep1.pdf", "tanggal_folder": "01", "source": "folder"},
        ])
        valid_seps = set()
        orphan = build_orphan_pdf_table(entries, valid_seps)
        assert len(orphan) == 1
        assert orphan.iloc[0]["No SEP"] == "0132R0010101V000001"

    def test_pdf_in_excel_is_not_orphan(self):
        entries = _make_entries([
            {"no_sep": "0132R0010101V000001", "display_path": "/path/sep1.pdf", "tanggal_folder": "01", "source": "folder"},
        ])
        valid_seps = {"0132R0010101V000001"}
        orphan = build_orphan_pdf_table(entries, valid_seps)
        assert orphan.empty

    def test_pdf_without_sep_is_orphan_with_note(self):
        entries = _make_entries([
            {"no_sep": "", "display_path": "/path/unknown.pdf", "tanggal_folder": "05", "source": "folder"},
        ])
        orphan = build_orphan_pdf_table(entries, set())
        assert len(orphan) == 1
        assert "tidak terdeteksi" in orphan.iloc[0]["Catatan"].lower()

    def test_empty_entries_returns_empty_table(self):
        orphan = build_orphan_pdf_table(pd.DataFrame(), set())
        assert orphan.empty

    def test_mixed_pdfs_only_orphans_returned(self):
        entries = _make_entries([
            {"no_sep": "0132R0010101V000001", "display_path": "/p/a.pdf", "tanggal_folder": "01", "source": "folder"},
            {"no_sep": "0132R0010101V000002", "display_path": "/p/b.pdf", "tanggal_folder": "02", "source": "folder"},
            {"no_sep": "0132R0010101V000003", "display_path": "/p/c.pdf", "tanggal_folder": "03", "source": "folder"},
        ])
        valid_seps = {"0132R0010101V000001", "0132R0010101V000003"}
        orphan = build_orphan_pdf_table(entries, valid_seps)
        assert len(orphan) == 1
        assert orphan.iloc[0]["No SEP"] == "0132R0010101V000002"
