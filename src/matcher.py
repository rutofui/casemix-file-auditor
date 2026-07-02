from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import pandas as pd

from .config import (
    CONTENT_REVIEW_COLUMNS,
    FILE_REVIEW_COLUMNS,
    FILE_REVIEW_ICD_COLUMNS,
    FILE_REVIEW_TXT_COLUMNS,
    NO,
    OCR_CONTENT_REVIEW_COLUMNS,
    OCR_REQUIRED_COMPONENTS,
    REQUIRED_COMPONENTS,
    STATUS_DUPLIKAT,
    STATUS_FILE_ADA,
    STATUS_FILE_BELUM_ADA,
    STATUS_FOLDER_SALAH,
    STATUS_FOLDER_SESUAI,
    STATUS_FOLDER_TIDAK_ADA_FILE,
    STATUS_FOLDER_TIDAK_TERDETEKSI,
    STATUS_ICD_TIDAK_SESUAI,
    STATUS_DATA_LIP_TIDAK_SESUAI,
    STATUS_KURANG_KOMPONEN,
    STATUS_KURANG_PDF,
    STATUS_LENGKAP,
    STATUS_REVIEW_MANUAL,
    STATUS_SALAH_FOLDER,
    YES,
    bool_to_ya_tidak,
)


def build_file_review(
    claims_df: pd.DataFrame,
    file_entries_df: pd.DataFrame,
    icd_check_results: dict[str, Any] | None = None,
    lip_metadata_results: dict[str, Any] | None = None,
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
        _review_one_file_count(
            claim=claim,
            index_entries=index_entries,
            icd_check_results=icd_check_results,
            lip_metadata_results=lip_metadata_results,
        )
        for _, claim in claims_df.iterrows()
    ]
    columns = FILE_REVIEW_TXT_COLUMNS if lip_metadata_results is not None else (
        FILE_REVIEW_ICD_COLUMNS if icd_check_results is not None else FILE_REVIEW_COLUMNS
    )
    review_df = pd.DataFrame(rows, columns=columns)
    orphan_df = build_orphan_pdf_table(index_entries, valid_claim_seps)
    summary = build_file_summary(
        review_df,
        claims_df,
        orphan_df,
        icd_check_active=icd_check_results is not None,
        lip_check_active=lip_metadata_results is not None,
    )
    return review_df, orphan_df, summary


def build_pdf_content_review(
    file_entries_df: pd.DataFrame,
    pdf_results_by_source_id: dict[str, Any] | None = None,
    *,
    use_ocr: bool = False,
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
            use_ocr=use_ocr,
        )
        for _, entry in content_entries.iterrows()
    ]
    columns = OCR_CONTENT_REVIEW_COLUMNS if use_ocr else CONTENT_REVIEW_COLUMNS
    review_df = pd.DataFrame(rows, columns=columns)
    orphan_df = pd.DataFrame(columns=["No SEP", "Path File", "Tanggal Folder", "Sumber", "Catatan"])
    summary = build_content_summary(review_df, pd.DataFrame(), use_ocr=use_ocr)
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


def build_file_summary(
    review_df: pd.DataFrame,
    claims_df: pd.DataFrame,
    orphan_df: pd.DataFrame,
    *,
    icd_check_active: bool = False,
    lip_check_active: bool = False,
) -> dict[str, int]:
    if review_df.empty:
        summary = {
            "Total klaim": 0,
            "Total SEP valid": 0,
            "PDF ditemukan": 0,
            "Belum ada PDF": 0,
            "Salah folder": 0,
            "Duplikat": 0,
            "PDF tanpa Excel": 0,
            "Jumlah lengkap": 0,
        }
        if icd_check_active:
            summary["Kode ICD tidak sesuai"] = 0
        if lip_check_active:
            summary["Data LIP tidak sesuai"] = 0
        return summary
    summary = {
        "Total klaim": int(len(review_df)),
        "Total SEP valid": int(claims_df["_sep_valid"].astype(bool).sum()),
        "PDF ditemukan": int((review_df["Status File"] == STATUS_FILE_ADA).sum()),
        "Belum ada PDF": int((review_df["Status File"] == STATUS_FILE_BELUM_ADA).sum()),
        "Salah folder": int((review_df["Status Folder"] == STATUS_FOLDER_SALAH).sum()),
        "Duplikat": int((review_df["Duplikat"] == YES).sum()),
        "PDF tanpa Excel": int(len(orphan_df)),
        "Jumlah lengkap": int((review_df["Status Akhir"] == STATUS_LENGKAP).sum()),
    }
    if icd_check_active:
        summary["Kode ICD tidak sesuai"] = int((review_df["Status Akhir"] == STATUS_ICD_TIDAK_SESUAI).sum())
    if lip_check_active:
        summary["Data LIP tidak sesuai"] = int((review_df["Status Akhir"] == STATUS_DATA_LIP_TIDAK_SESUAI).sum())
    return summary


def build_content_summary(
    review_df: pd.DataFrame,
    claims_df: pd.DataFrame,
    *,
    use_ocr: bool = False,
) -> dict[str, int]:
    if use_ocr:
        return build_ocr_content_summary(review_df)
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


def build_ocr_content_summary(review_df: pd.DataFrame) -> dict[str, int]:
    if review_df.empty:
        return {
            "Total PDF": 0,
            "PDF dibaca": 0,
            "SEP cocok di PDF": 0,
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
    return {
        "Total PDF": int(len(review_df)),
        "PDF dibaca": int((review_df["PDF Dapat Dibaca"] == YES).sum()),
        "SEP cocok di PDF": int((review_df["SEP Terdeteksi Dalam PDF"] == YES).sum()),
        "LIP": int((review_df["LIP Terdeteksi"] == YES).sum()),
        "Rincian tagihan": int((review_df["Rincian Tagihan Terdeteksi"] == YES).sum()),
        "Resume Medis": int((review_df["Resume Medis"] == YES).sum()),
        "Triage": int((review_df["Triage"] == YES).sum()),
        "SPRI": int((review_df["Surat Perintah Rawat Inap"] == YES).sum()),
        "Hasil Pemeriksaan": int((review_df["Hasil Pemeriksaan"] == YES).sum()),
        "Radiologi": int((review_df["Pemeriksaan Radiologi"] == YES).sum()),
        "Kurang komponen": int((review_df["Status Akhir"] == STATUS_KURANG_KOMPONEN).sum()),
        "Perlu review manual": int((review_df["Status Akhir"] == STATUS_REVIEW_MANUAL).sum()),
        "Isi lengkap": int((review_df["Status Akhir"] == STATUS_LENGKAP).sum()),
    }


def _review_one_file_count(
    *,
    claim: pd.Series,
    index_entries: pd.DataFrame,
    icd_check_results: dict[str, Any] | None = None,
    lip_metadata_results: dict[str, Any] | None = None,
) -> dict[str, object]:
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
    elif lip_metadata_results is not None:
        final_status = _apply_lip_metadata_check(row, sep, lip_metadata_results, notes)
        if final_status == STATUS_LENGKAP and icd_check_results is not None:
            final_status = _apply_icd_check(row, sep, icd_check_results, notes)
        elif icd_check_results is not None:
            icd_status = _apply_icd_check(row, sep, icd_check_results, notes)
            if icd_status == STATUS_ICD_TIDAK_SESUAI:
                final_status = icd_status
    elif icd_check_results is not None:
        final_status = _apply_icd_check(row, sep, icd_check_results, notes)
    else:
        final_status = STATUS_LENGKAP

    row["Status Akhir"] = final_status
    row["Catatan"] = " ".join(_unique_non_empty(notes))
    return row


def _apply_lip_metadata_check(
    row: dict[str, object],
    sep: str,
    lip_metadata_results: dict[str, Any],
    notes: list[str],
) -> str:
    result = lip_metadata_results.get(sep)
    if result is None:
        notes.append("Data LIP tidak diperiksa karena path PDF lokal tidak tersedia.")
        return STATUS_REVIEW_MANUAL

    readable = bool(_result_value(result, "readable", False))
    row["Tanggal Masuk LIP"] = _result_value(result, "tanggal_masuk_lip", "") or ""
    row["Tanggal Keluar LIP"] = _result_value(result, "tanggal_keluar_lip", "") or ""
    row["Kelas Perawatan LIP"] = _result_value(result, "kelas_perawatan_lip", "") or ""

    mismatch = False
    for result_key, column, label in [
        ("tanggal_masuk_match", "Tanggal Masuk Sesuai", "Tanggal masuk"),
        ("tanggal_keluar_match", "Tanggal Keluar Sesuai", "Tanggal keluar"),
        ("kelas_perawatan_match", "Kelas Perawatan Sesuai", "Kelas perawatan"),
    ]:
        match_value = _result_value(result, result_key, None)
        if match_value is None:
            row[column] = "-"
            continue
        row[column] = bool_to_ya_tidak(bool(match_value))
        if not match_value:
            mismatch = True
            notes.append(f"{label} di LIP tidak sesuai dengan TXT E-Klaim.")

    error = _result_value(result, "error", "")
    if error:
        notes.append(str(error))
    for note in _result_value(result, "notes", []) or []:
        if note:
            notes.append(str(note))

    if not readable:
        return STATUS_REVIEW_MANUAL
    if mismatch:
        return STATUS_DATA_LIP_TIDAK_SESUAI
    return STATUS_LENGKAP


def _apply_icd_check(
    row: dict[str, object],
    sep: str,
    icd_check_results: dict[str, Any],
    notes: list[str],
) -> str:
    result = icd_check_results.get(sep)
    if result is None:
        # SEP intentionally skipped by the orchestrator (e.g. no matched local
        # PDF) — don't penalize a row the check never attempted.
        return STATUS_LENGKAP

    icd10_missing = list(_result_value(result, "icd10_missing", []) or [])
    icd9_missing = list(_result_value(result, "icd9_missing", []) or [])
    readable = bool(_result_value(result, "readable", False))

    row["ICD-10 Sesuai"] = bool_to_ya_tidak(not icd10_missing)
    row["ICD-9-CM Sesuai"] = bool_to_ya_tidak(not icd9_missing)
    missing_codes = _unique_non_empty(icd10_missing + icd9_missing)
    row["Kode Tidak Ditemukan di PDF"] = ", ".join(missing_codes)

    if not readable:
        row["ICD-10 Sesuai"] = NO
        row["ICD-9-CM Sesuai"] = NO
        notes.append("Halaman pertama PDF tidak dapat dibaca untuk verifikasi kode ICD.")
        return STATUS_ICD_TIDAK_SESUAI

    if missing_codes:
        notes.append(f"Kode tidak ditemukan di halaman pertama PDF: {', '.join(missing_codes)}.")
        return STATUS_ICD_TIDAK_SESUAI

    return STATUS_LENGKAP


def _review_one_pdf_content(
    *,
    entry: pd.Series,
    pdf_results_by_source_id: dict[str, Any],
    use_ocr: bool,
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
        "Judul Berkas Terdeteksi": "",
        "Resume Medis": NO,
        "Triage": NO,
        "Surat Perintah Rawat Inap": NO,
        "Hasil Pemeriksaan": NO,
        "Pemeriksaan Radiologi": NO,
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
    row["Judul Berkas Terdeteksi"] = ", ".join(
        _unique_non_empty(list(_result_value(pdf_result, "document_titles", []) or []))
    )
    detected_titles = set(_result_value(pdf_result, "document_titles", []) or [])
    for title in [
        "Resume Medis",
        "Triage",
        "Surat Perintah Rawat Inap",
        "Hasil Pemeriksaan",
        "Pemeriksaan Radiologi",
    ]:
        row[title] = bool_to_ya_tidak(title in detected_titles)

    if filename_sep and pdf_sep_values and filename_sep not in set(pdf_sep_values):
        notes.append("Nomor SEP pada nama file berbeda dengan SEP yang terdeteksi di isi PDF.")

    error = _result_value(pdf_result, "error", "")
    if error:
        notes.append(str(error))
    for note in _result_value(pdf_result, "notes", []) or []:
        if note:
            notes.append(str(note))

    required_components = OCR_REQUIRED_COMPONENTS if use_ocr else REQUIRED_COMPONENTS
    missing_components = [col for col in required_components if row.get(col, NO) != YES]
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
        "Tanggal Masuk": claim.get("Tanggal Masuk", ""),
        "Tanggal Pulang": claim.get("Tanggal Pulang", ""),
        "Kelas Perawatan": claim.get("Kelas Perawatan", ""),
        "No RM": claim.get("No RM", ""),
        "Nama Pasien": claim.get("Nama Pasien", ""),
        "Diagnosa": claim.get("Diagnosa", ""),
        "Status File": STATUS_FILE_BELUM_ADA,
        "Path File": "",
        "Tanggal Folder": "",
        "Status Folder": STATUS_FOLDER_TIDAK_ADA_FILE,
        "Duplikat": NO,
        "Status Akhir": STATUS_KURANG_PDF,
        "ICD-10 Sesuai": "-",
        "ICD-9-CM Sesuai": "-",
        "Kode Tidak Ditemukan di PDF": "",
        "Tanggal Masuk LIP": "",
        "Tanggal Keluar LIP": "",
        "Kelas Perawatan LIP": "",
        "Tanggal Masuk Sesuai": "-",
        "Tanggal Keluar Sesuai": "-",
        "Kelas Perawatan Sesuai": "-",
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
