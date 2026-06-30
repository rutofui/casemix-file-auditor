from __future__ import annotations

import pandas as pd
import pytest

from src.config import (
    FILE_REVIEW_COLUMNS,
    FILE_REVIEW_ICD_COLUMNS,
    STATUS_DUPLIKAT,
    STATUS_FOLDER_SALAH,
    STATUS_FOLDER_SESUAI,
    STATUS_FOLDER_TIDAK_TERDETEKSI,
    STATUS_ICD_TIDAK_SESUAI,
    STATUS_LENGKAP,
    STATUS_SALAH_FOLDER,
)
from src.matcher import (
    _day_from_date_value,
    _folder_status,
    build_file_review,
    build_orphan_pdf_table,
)
from src.pdf_checker import FirstPageCodeCheckResult
from src.parser_file_list import build_file_entry


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


# ---------------------------------------------------------------------------
# build_file_review with icd_check_results (TXT + Folder ICD check)
# ---------------------------------------------------------------------------


def _make_claim(sep: str, *, tanggal_pulang: str = "2026-06-05") -> dict:
    return {
        "No SEP": sep,
        "Tanggal Pulang": tanggal_pulang,
        "No RM": "RM001",
        "Nama Pasien": "Pasien A",
        "Diagnosa": "A09.9;E86",
        "_no_sep_normalized": sep,
        "_sep_valid": True,
    }


def _make_folder_entry(sep: str, *, day: str = "05") -> dict:
    return build_file_entry(
        f"folder/{day}/{sep}.pdf",
        local_path=f"/abs/folder/{day}/{sep}.pdf",
        source="folder",
        is_index_source=True,
        is_content_source=True,
    )


class TestBuildFileReviewWithIcdCheck:
    def test_all_codes_present_is_lengkap(self):
        sep = "0132R0770626V000060"
        claims = pd.DataFrame([_make_claim(sep)])
        files = pd.DataFrame([_make_folder_entry(sep)])
        icd_results = {sep: FirstPageCodeCheckResult(readable=True, icd10_missing=[], icd9_missing=[])}

        review_df, _, _ = build_file_review(claims, files, icd_check_results=icd_results)

        assert review_df.loc[0, "Status Akhir"] == STATUS_LENGKAP
        assert review_df.loc[0, "ICD-10 Sesuai"] == "Ya"
        assert review_df.loc[0, "ICD-9-CM Sesuai"] == "Ya"
        assert list(review_df.columns) == FILE_REVIEW_ICD_COLUMNS

    def test_missing_icd10_code_downgrades_status(self):
        sep = "0132R0770626V000061"
        claims = pd.DataFrame([_make_claim(sep)])
        files = pd.DataFrame([_make_folder_entry(sep)])
        icd_results = {sep: FirstPageCodeCheckResult(readable=True, icd10_missing=["E86"], icd9_missing=[])}

        review_df, _, summary = build_file_review(claims, files, icd_check_results=icd_results)

        assert review_df.loc[0, "Status Akhir"] == STATUS_ICD_TIDAK_SESUAI
        assert review_df.loc[0, "ICD-10 Sesuai"] == "Tidak"
        assert "E86" in review_df.loc[0, "Kode Tidak Ditemukan di PDF"]
        assert "E86" in review_df.loc[0, "Catatan"]
        assert summary["Kode ICD tidak sesuai"] == 1

    def test_unreadable_pdf_downgrades_with_note(self):
        sep = "0132R0770626V000062"
        claims = pd.DataFrame([_make_claim(sep)])
        files = pd.DataFrame([_make_folder_entry(sep)])
        icd_results = {
            sep: FirstPageCodeCheckResult(
                readable=False,
                icd10_missing=["A09.9", "E86"],
                icd9_missing=["90.59"],
                error="PDF gagal dibuka.",
            )
        }

        review_df, _, _ = build_file_review(claims, files, icd_check_results=icd_results)

        assert review_df.loc[0, "Status Akhir"] == STATUS_ICD_TIDAK_SESUAI
        assert review_df.loc[0, "ICD-10 Sesuai"] == "Tidak"
        assert review_df.loc[0, "ICD-9-CM Sesuai"] == "Tidak"
        assert "tidak dapat dibaca" in review_df.loc[0, "Catatan"].lower()

    def test_duplikat_status_wins_over_icd_check(self):
        sep = "0132R0770626V000063"
        claims = pd.DataFrame([_make_claim(sep)])
        files = pd.DataFrame(
            [
                build_file_entry(
                    f"folder/05/{sep}_a.pdf",
                    local_path=f"/abs/folder/05/{sep}_a.pdf",
                    source="folder",
                    is_index_source=True,
                    is_content_source=True,
                ),
                build_file_entry(
                    f"folder/05/{sep}_b.pdf",
                    local_path=f"/abs/folder/05/{sep}_b.pdf",
                    source="folder",
                    is_index_source=True,
                    is_content_source=True,
                ),
            ]
        )
        icd_results = {sep: FirstPageCodeCheckResult(readable=True, icd10_missing=["E86"], icd9_missing=[])}

        review_df, _, _ = build_file_review(claims, files, icd_check_results=icd_results)

        assert review_df.loc[0, "Status Akhir"] == STATUS_DUPLIKAT

    def test_salah_folder_status_wins_over_icd_check(self):
        sep = "0132R0770626V000064"
        claims = pd.DataFrame([_make_claim(sep, tanggal_pulang="2026-06-06")])
        files = pd.DataFrame([_make_folder_entry(sep, day="05")])
        icd_results = {sep: FirstPageCodeCheckResult(readable=True, icd10_missing=["E86"], icd9_missing=[])}

        review_df, _, _ = build_file_review(claims, files, icd_check_results=icd_results)

        assert review_df.loc[0, "Status Akhir"] == STATUS_SALAH_FOLDER

    def test_sep_missing_from_icd_results_is_not_penalized(self):
        sep = "0132R0770626V000065"
        claims = pd.DataFrame([_make_claim(sep)])
        files = pd.DataFrame([_make_folder_entry(sep)])

        review_df, _, _ = build_file_review(claims, files, icd_check_results={})

        assert review_df.loc[0, "Status Akhir"] == STATUS_LENGKAP

    def test_no_icd_check_keeps_original_columns(self):
        sep = "0132R0770626V000066"
        claims = pd.DataFrame([_make_claim(sep)])
        files = pd.DataFrame([_make_folder_entry(sep)])

        review_df, _, summary = build_file_review(claims, files)

        assert list(review_df.columns) == FILE_REVIEW_COLUMNS
        assert "Kode ICD tidak sesuai" not in summary
