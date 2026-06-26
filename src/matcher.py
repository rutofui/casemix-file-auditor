from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import pandas as pd

from .config import (
    CONTENT_REVIEW_COLUMNS,
    FILE_REVIEW_COLUMNS,
    NO,
    REQUIRED_COMPONENTS,
    REVIEW_COLUMNS,
    STATUS_DUPLIKAT,
    STATUS_FILE_ADA,
    STATUS_FILE_BELUM_ADA,
    STATUS_FOLDER_SALAH,
    STATUS_FOLDER_SESUAI,
    STATUS_FOLDER_TIDAK_ADA_FILE,
    STATUS_FOLDER_TIDAK_TERDETEKSI,
    STATUS_KURANG_KOMPONEN,
    STATUS_KURANG_PDF,
    STATUS_LENGKAP,
    STATUS_REVIEW_MANUAL,
    STATUS_SALAH_FOLDER,
    YES,
    bool_to_ya_tidak,
)


def build_review(
    claims_df: pd.DataFrame,
    file_entries_df: pd.DataFrame,
    pdf_results_by_source_id: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    pdf_results_by_source_id = pdf_results_by_source_id or {}
    file_entries = file_entries_df.copy() if file_entries_df is not None else pd.DataFrame()
    if file_entries.empty:
        index_entries = file_entries
        content_entries = file_entries
    else:
        index_entries = file_entries[file_entries["is_index_source"].astype(bool)].copy()
        content_entries = file_entries[file_entries["is_content_source"].astype(bool)].copy()

    valid_claim_seps = set(
        claims_df.loc[claims_df["_sep_valid"].astype(bool), "_no_sep_normalized"].dropna().astype(str)
    )
    review_rows: list[dict[str, object]] = []

    for _, claim in claims_df.iterrows():
        review_rows.append(
            _review_one_claim(
                claim=claim,
                index_entries=index_entries,
                content_entries=content_entries,
                pdf_results_by_source_id=pdf_results_by_source_id,
            )
        )

    review_df = pd.DataFrame(review_rows, columns=REVIEW_COLUMNS)
    orphan_df = build_orphan_pdf_table(index_entries, valid_claim_seps)
    summary = build_summary(review_df, claims_df)
    return review_df, orphan_df, summary


def build_file_review(
    claims_df: pd.DataFrame,
    file_entries_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    file_entries = file_entries_df.copy() if file_entries_df is not None else pd.DataFrame()
    index_entries = (
        file_entries[file_entries["is_index_source"].astype(bool)].copy()
        if not file_entries.empty
        else file_entries
    )
    valid_claim_seps = set(
        claims_df.loc[claims_df["_sep_valid"].astype(bool), "_no_sep_normalized"].dropna().astype(str)
    )
    rows = [
        _review_one_file_count(claim=claim, index_entries=index_entries)
        for _, claim in claims_df.iterrows()
    ]
    review_df = pd.DataFrame(rows, columns=FILE_REVIEW_COLUMNS)
    orphan_df = build_orphan_pdf_table(index_entries, valid_claim_seps)
    summary = build_file_summary(review_df, claims_df, orphan_df)
    return review_df, orphan_df, summary


def build_pdf_content_review(
    file_entries_df: pd.DataFrame,
    pdf_results_by_source_id: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    pdf_results_by_source_id = pdf_results_by_source_id or {}
    file_entries = file_entries_df.copy() if file_entries_df is not None else pd.DataFrame()
    content_entries = (
        file_entries[file_entries["is_content_source"].astype(bool)].copy()
        if not file_entries.empty
        else file_entries
    )
    rows = [
        _review_one_pdf_content(
            entry=entry,
            pdf_results_by_source_id=pdf_results_by_source_id,
        )
        for _, entry in content_entries.iterrows()
    ]
    review_df = pd.DataFrame(rows, columns=CONTENT_REVIEW_COLUMNS)
    orphan_df = pd.DataFrame(columns=["No SEP", "Path File", "Tanggal Folder", "Sumber", "Catatan"])
    summary = build_content_summary(review_df, pd.DataFrame())
    return review_df, orphan_df, summary


def build_orphan_pdf_table(index_entries: pd.DataFrame, valid_claim_seps: set[str]) -> pd.DataFrame:
    columns = ["No SEP", "Path File", "Tanggal Folder", "Sumber", "Catatan"]
    if index_entries is None or index_entries.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    for _, entry in index_entries.iterrows():
        sep = str(entry.get("no_sep", "") or "")
        if sep and sep in valid_claim_seps:
            continue
        note = "SEP tidak ada di Excel."
        if not sep:
            note = "SEP tidak terdeteksi dari nama/path PDF."
        rows.append(
            {
                "No SEP": sep,
                "Path File": entry.get("display_path", ""),
                "Tanggal Folder": entry.get("tanggal_folder", ""),
                "Sumber": entry.get("source", ""),
                "Catatan": note,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_summary(review_df: pd.DataFrame, claims_df: pd.DataFrame) -> dict[str, int]:
    if review_df.empty:
        return {
            "Total klaim": 0,
            "Total SEP valid": 0,
            "Total PDF ditemukan": 0,
            "Total klaim belum ada PDF": 0,
            "Total salah folder": 0,
            "Total duplikat": 0,
            "Total kurang komponen": 0,
            "Total lengkap": 0,
        }

    return {
        "Total klaim": int(len(review_df)),
        "Total SEP valid": int(claims_df["_sep_valid"].astype(bool).sum()),
        "Total PDF ditemukan": int((review_df["Status File"] == STATUS_FILE_ADA).sum()),
        "Total klaim belum ada PDF": int((review_df["Status File"] == STATUS_FILE_BELUM_ADA).sum()),
        "Total salah folder": int((review_df["Status Folder"] == STATUS_FOLDER_SALAH).sum()),
        "Total duplikat": int((review_df["Duplikat"] == YES).sum()),
        "Total kurang komponen": int((review_df["Status Akhir"] == STATUS_KURANG_KOMPONEN).sum()),
        "Total lengkap": int((review_df["Status Akhir"] == STATUS_LENGKAP).sum()),
    }


def build_file_summary(
    review_df: pd.DataFrame,
    claims_df: pd.DataFrame,
    orphan_df: pd.DataFrame,
) -> dict[str, int]:
    if review_df.empty:
        return {
            "Total klaim": 0,
            "Total SEP valid": 0,
            "PDF ditemukan": 0,
            "Belum ada PDF": 0,
            "Salah folder": 0,
            "Duplikat": 0,
            "PDF tanpa Excel": 0,
            "Jumlah lengkap": 0,
        }
    return {
        "Total klaim": int(len(review_df)),
        "Total SEP valid": int(claims_df["_sep_valid"].astype(bool).sum()),
        "PDF ditemukan": int((review_df["Status File"] == STATUS_FILE_ADA).sum()),
        "Belum ada PDF": int((review_df["Status File"] == STATUS_FILE_BELUM_ADA).sum()),
        "Salah folder": int((review_df["Status Folder"] == STATUS_FOLDER_SALAH).sum()),
        "Duplikat": int((review_df["Duplikat"] == YES).sum()),
        "PDF tanpa Excel": int(len(orphan_df)),
        "Jumlah lengkap": int((review_df["Status Akhir"] == STATUS_LENGKAP).sum()),
    }


def build_content_summary(review_df: pd.DataFrame, claims_df: pd.DataFrame) -> dict[str, int]:
    if review_df.empty:
        return {
            "Total PDF": 0,
            "PDF dibaca": 0,
            "SEP cocok di PDF": 0,
            "LIP": 0,
            "Rincian tagihan": 0,
            "Hasil scan": 0,
            "Kurang komponen": 0,
            "Perlu review manual": 0,
            "Isi lengkap": 0,
        }
    return {
        "Total PDF": int(len(review_df)),
        "PDF dibaca": int((review_df["PDF Dapat Dibaca"] == YES).sum()),
        "SEP cocok di PDF": int((review_df["SEP Terdeteksi Dalam PDF"] == YES).sum()),
        "LIP": int((review_df["LIP Terdeteksi"] == YES).sum()),
        "Rincian tagihan": int((review_df["Rincian Tagihan Terdeteksi"] == YES).sum()),
        "Hasil scan": int((review_df["Hasil Scan Terdeteksi"] == YES).sum()),
        "Kurang komponen": int((review_df["Status Akhir"] == STATUS_KURANG_KOMPONEN).sum()),
        "Perlu review manual": int((review_df["Status Akhir"] == STATUS_REVIEW_MANUAL).sum()),
        "Isi lengkap": int((review_df["Status Akhir"] == STATUS_LENGKAP).sum()),
    }


def _review_one_file_count(*, claim: pd.Series, index_entries: pd.DataFrame) -> dict[str, object]:
    sep = str(claim.get("_no_sep_normalized", "") or "")
    sep_valid = bool(claim.get("_sep_valid", False))
    notes: list[str] = []
    row = _base_file_row(claim, sep)

    if not sep_valid:
        row["Status Akhir"] = STATUS_REVIEW_MANUAL
        row["Catatan"] = "No SEP kosong atau format SEP tidak valid."
        return row

    matched_index = index_entries[index_entries["no_sep"] == sep] if not index_entries.empty else index_entries
    if matched_index.empty:
        row["Status Akhir"] = STATUS_KURANG_PDF
        row["Catatan"] = "File PDF untuk SEP ini belum ditemukan."
        return row

    _apply_file_match(row, claim, matched_index, notes)

    if row["Duplikat"] == YES:
        final_status = STATUS_DUPLIKAT
    elif row["Status Folder"] == STATUS_FOLDER_SALAH:
        final_status = STATUS_SALAH_FOLDER
    elif row["Status Folder"] == STATUS_FOLDER_TIDAK_TERDETEKSI:
        final_status = STATUS_REVIEW_MANUAL
    else:
        final_status = STATUS_LENGKAP

    row["Status Akhir"] = final_status
    row["Catatan"] = " ".join(_unique_non_empty(notes))
    return row


def _review_one_pdf_content(
    *,
    entry: pd.Series,
    pdf_results_by_source_id: dict[str, Any],
) -> dict[str, object]:
    source_id = str(entry.get("source_id", ""))
    filename_sep = str(entry.get("no_sep", "") or "")
    pdf_result = pdf_results_by_source_id.get(source_id)
    notes: list[str] = []
    row = {
        "No SEP": filename_sep,
        "Nama File": entry.get("file_name", ""),
        "Path File": entry.get("display_path", ""),
        "PDF Dapat Dibaca": NO,
        "SEP Terdeteksi Dalam PDF": NO,
        "LIP Terdeteksi": NO,
        "Rincian Tagihan Terdeteksi": NO,
        "Hasil Scan Terdeteksi": NO,
        "Status Akhir": STATUS_REVIEW_MANUAL,
        "Catatan": "",
    }

    if pdf_result is None:
        row["Catatan"] = "PDF belum diperiksa."
        return row

    pdf_sep_values = list(_result_value(pdf_result, "sep_values", []) or [])
    if not row["No SEP"] and pdf_sep_values:
        row["No SEP"] = pdf_sep_values[0]
    row["PDF Dapat Dibaca"] = bool_to_ya_tidak(bool(_result_value(pdf_result, "readable", False)))
    row["SEP Terdeteksi Dalam PDF"] = bool_to_ya_tidak(bool(pdf_sep_values))
    row["LIP Terdeteksi"] = bool_to_ya_tidak(bool(_result_value(pdf_result, "lip_detected", False)))
    row["Rincian Tagihan Terdeteksi"] = bool_to_ya_tidak(
        bool(_result_value(pdf_result, "billing_detected", False))
    )
    row["Hasil Scan Terdeteksi"] = bool_to_ya_tidak(
        bool(_result_value(pdf_result, "scan_detected", False))
    )

    if filename_sep and pdf_sep_values and filename_sep not in set(pdf_sep_values):
        notes.append("Nomor SEP pada nama file berbeda dengan SEP yang terdeteksi di isi PDF.")

    error = _result_value(pdf_result, "error", "")
    if error:
        notes.append(str(error))
    for note in _result_value(pdf_result, "notes", []) or []:
        if note:
            notes.append(str(note))

    missing_components = [col for col in REQUIRED_COMPONENTS if row.get(col, NO) != YES]
    if _result_value(pdf_result, "needs_manual_review", False):
        final_status = STATUS_REVIEW_MANUAL
    elif missing_components:
        final_status = STATUS_KURANG_KOMPONEN
        notes.append("Komponen belum terdeteksi: " + ", ".join(missing_components))
    else:
        final_status = STATUS_LENGKAP

    row["Status Akhir"] = final_status
    row["Catatan"] = " ".join(_unique_non_empty(notes))
    return row


def _base_file_row(claim: pd.Series, sep: str) -> dict[str, object]:
    return {
        "No SEP": sep or str(claim.get("No SEP", "") or ""),
        "Tanggal Pulang": claim.get("Tanggal Pulang", ""),
        "No RM": claim.get("No RM", ""),
        "Nama Pasien": claim.get("Nama Pasien", ""),
        "Diagnosa": claim.get("Diagnosa", ""),
        "Status File": STATUS_FILE_BELUM_ADA,
        "Path File": "",
        "Tanggal Folder": "",
        "Status Folder": STATUS_FOLDER_TIDAK_ADA_FILE,
        "Duplikat": NO,
        "Status Akhir": STATUS_KURANG_PDF,
        "Catatan": "",
    }


def _apply_file_match(
    row: dict[str, object],
    claim: pd.Series,
    matched_index: pd.DataFrame,
    notes: list[str],
) -> None:
    row["Status File"] = STATUS_FILE_ADA
    paths = _unique_non_empty(matched_index["display_path"].tolist())
    row["Path File"] = " | ".join(paths)
    unique_pdf_paths = set(paths)
    row["Duplikat"] = YES if len(unique_pdf_paths) > 1 else NO
    if row["Duplikat"] == YES:
        notes.append(f"Ditemukan {len(unique_pdf_paths)} file PDF untuk SEP ini.")

    folder_dates = _unique_non_empty(matched_index["tanggal_folder"].tolist())
    row["Tanggal Folder"] = ", ".join(folder_dates)
    folder_status, folder_note = _folder_status(
        tanggal_pulang=claim.get("Tanggal Pulang", ""),
        matched_index=matched_index,
    )
    row["Status Folder"] = folder_status
    if folder_note:
        notes.append(folder_note)


def _review_one_claim(
    *,
    claim: pd.Series,
    index_entries: pd.DataFrame,
    content_entries: pd.DataFrame,
    pdf_results_by_source_id: dict[str, Any],
) -> dict[str, object]:
    sep = str(claim.get("_no_sep_normalized", "") or "")
    sep_valid = bool(claim.get("_sep_valid", False))
    notes: list[str] = []

    base = {
        "No SEP": sep or str(claim.get("No SEP", "") or ""),
        "Tanggal Pulang": claim.get("Tanggal Pulang", ""),
        "No RM": claim.get("No RM", ""),
        "Nama Pasien": claim.get("Nama Pasien", ""),
        "Diagnosa": claim.get("Diagnosa", ""),
        "Status File": STATUS_FILE_BELUM_ADA,
        "Path File": "",
        "Tanggal Folder": "",
        "Status Folder": STATUS_FOLDER_TIDAK_ADA_FILE,
        "Duplikat": NO,
        "SEP Terdeteksi Dalam PDF": NO,
        "LIP Terdeteksi": NO,
        "Rincian Tagihan Terdeteksi": NO,
        "Hasil Scan Terdeteksi": NO,
        "Status Akhir": STATUS_KURANG_PDF,
        "Catatan": "",
    }

    if not sep_valid:
        base["Status Akhir"] = STATUS_REVIEW_MANUAL
        base["Catatan"] = "No SEP kosong atau format SEP tidak valid."
        return base

    matched_index = index_entries[index_entries["no_sep"] == sep] if not index_entries.empty else index_entries
    if matched_index.empty:
        base["Status Akhir"] = STATUS_KURANG_PDF
        base["Catatan"] = "File PDF untuk SEP ini belum ditemukan."
        return base

    base["Status File"] = STATUS_FILE_ADA
    paths = _unique_non_empty(matched_index["display_path"].tolist())
    base["Path File"] = " | ".join(paths)
    unique_pdf_paths = set(paths)
    duplicate = len(unique_pdf_paths) > 1
    base["Duplikat"] = YES if duplicate else NO
    if duplicate:
        notes.append(f"Ditemukan {len(unique_pdf_paths)} file PDF untuk SEP ini.")

    folder_dates = _unique_non_empty(matched_index["tanggal_folder"].tolist())
    base["Tanggal Folder"] = ", ".join(folder_dates)
    folder_status, folder_note = _folder_status(
        tanggal_pulang=claim.get("Tanggal Pulang", ""),
        matched_index=matched_index,
    )
    base["Status Folder"] = folder_status
    if folder_note:
        notes.append(folder_note)

    matched_content = (
        content_entries[content_entries["no_sep"] == sep] if not content_entries.empty else content_entries
    )
    pdf_result = _pick_pdf_result(matched_content, pdf_results_by_source_id)
    if pdf_result is None:
        notes.append(
            "Isi PDF belum dapat diperiksa. Upload PDF atau pilih folder lokal yang berisi PDF."
        )
    else:
        _apply_pdf_result(base, sep, pdf_result, notes)

    missing_components = [
        col for col in REQUIRED_COMPONENTS if base.get(col, NO) != YES
    ]

    if duplicate:
        final_status = STATUS_DUPLIKAT
    elif folder_status == STATUS_FOLDER_SALAH:
        final_status = STATUS_SALAH_FOLDER
    elif pdf_result is None or _result_value(pdf_result, "needs_manual_review", False):
        final_status = STATUS_REVIEW_MANUAL
    elif folder_status == STATUS_FOLDER_TIDAK_TERDETEKSI:
        final_status = STATUS_REVIEW_MANUAL
    elif missing_components:
        final_status = STATUS_KURANG_KOMPONEN
        notes.append("Komponen belum terdeteksi: " + ", ".join(missing_components))
    else:
        final_status = STATUS_LENGKAP

    base["Status Akhir"] = final_status
    base["Catatan"] = " ".join(_unique_non_empty(notes))
    return base


def _apply_pdf_result(
    row: dict[str, object],
    expected_sep: str,
    pdf_result: Any,
    notes: list[str],
) -> None:
    sep_values = set(_result_value(pdf_result, "sep_values", []) or [])
    sep_detected = expected_sep in sep_values
    row["SEP Terdeteksi Dalam PDF"] = bool_to_ya_tidak(sep_detected)
    row["LIP Terdeteksi"] = bool_to_ya_tidak(bool(_result_value(pdf_result, "lip_detected", False)))
    row["Rincian Tagihan Terdeteksi"] = bool_to_ya_tidak(
        bool(_result_value(pdf_result, "billing_detected", False))
    )
    row["Hasil Scan Terdeteksi"] = bool_to_ya_tidak(
        bool(_result_value(pdf_result, "scan_detected", False))
    )

    if sep_values and expected_sep not in sep_values:
        notes.append("Nomor SEP di PDF berbeda/tidak cocok dengan Excel.")
    error = _result_value(pdf_result, "error", "")
    if error:
        notes.append(str(error))
    for note in _result_value(pdf_result, "notes", []) or []:
        if note:
            notes.append(str(note))


def _folder_status(tanggal_pulang: object, matched_index: pd.DataFrame) -> tuple[str, str]:
    expected_day = _day_from_date_value(tanggal_pulang)
    if not expected_day:
        return STATUS_FOLDER_TIDAK_TERDETEKSI, "Tanggal Pulang tidak valid/tidak terbaca."

    detected_dates = [str(value) for value in matched_index["tanggal_folder"].tolist() if str(value)]
    if not detected_dates:
        return STATUS_FOLDER_TIDAK_TERDETEKSI, "Folder tanggal tidak bisa dibaca dari path PDF."
    if any(day != expected_day for day in detected_dates):
        return STATUS_FOLDER_SALAH, f"Seharusnya folder tanggal {expected_day}."
    if len(detected_dates) == len(matched_index):
        return STATUS_FOLDER_SESUAI, ""
    return STATUS_FOLDER_TIDAK_TERDETEKSI, "Sebagian path PDF tidak memiliki folder tanggal."


def _day_from_date_value(value: object) -> str:
    if value is None or str(value).strip() == "":
        return ""
    text = str(value).strip()
    if isinstance(value, (pd.Timestamp,)):
        parsed = value
    elif len(text) >= 10 and text[4] in "-/" and text[7] in "-/":
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=False)
    else:
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            parsed = pd.to_datetime(value, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        return ""
    return f"{int(parsed.day):02d}"


def _pick_pdf_result(content_entries: pd.DataFrame, pdf_results_by_source_id: dict[str, Any]) -> Any | None:
    if content_entries is None or content_entries.empty:
        return None

    for _, entry in content_entries.iterrows():
        source_id = str(entry.get("source_id", ""))
        result = pdf_results_by_source_id.get(source_id)
        if result is not None and not _result_value(result, "error", ""):
            return result

    for _, entry in content_entries.iterrows():
        source_id = str(entry.get("source_id", ""))
        result = pdf_results_by_source_id.get(source_id)
        if result is not None:
            return result
    return None


def _result_value(result: Any, key: str, default: Any = None) -> Any:
    if result is None:
        return default
    if isinstance(result, dict):
        return result.get(key, default)
    if is_dataclass(result):
        return asdict(result).get(key, default)
    return getattr(result, key, default)


def _unique_non_empty(values: list[object]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = "" if value is None else str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
