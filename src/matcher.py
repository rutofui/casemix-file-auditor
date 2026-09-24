from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import pandas as pd

from .config import (
    CONTENT_COMPONENTS,
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
    required_components: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    if required_components is not None:
        unknown = set(required_components) - set(CONTENT_COMPONENTS)
        if not required_components or unknown:
            raise ValueError(f"Checklist komponen tidak valid: {', '.join(sorted(unknown)) or 'kosong'}")
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
            required_components=required_components,
        )
        for _, entry in content_entries.iterrows()
    ]
    columns = OCR_CONTENT_REVIEW_COLUMNS if use_ocr else CONTENT_REVIEW_COLUMNS
    if required_components is not None:
        columns = ["No SEP", "Nama File", "Path File", "PDF Dapat Dibaca", *CONTENT_COMPONENTS,
                   "SEP Dalam PDF", "Bukti Halaman", "Status Akhir", "Catatan"]
    review_df = pd.DataFrame(rows, columns=columns)
    orphan_df = pd.DataFrame(columns=["No SEP", "Path File", "Tanggal Folder", "Sumber", "Catatan"])
    summary = build_content_summary(
        review_df, pd.DataFrame(), use_ocr=use_ocr, required_components=required_components
    )
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
        note = "SEP tidak ada di daftar acuan."
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
            "PDF di luar daftar acuan": 0,
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
        "PDF di luar daftar acuan": int(len(orphan_df)),
        "Jumlah lengkap": int((review_df["Status Akhir"] == STATUS_LENGKAP).sum()),
    }
    if icd_check_active:
        summary["Kode ICD tidak sesuai"] = int(
            review_df["Temuan"].fillna("").str.split("; ").map(lambda items: STATUS_ICD_TIDAK_SESUAI in items).sum()
        )
    if lip_check_active:
        summary["Data LIP tidak sesuai"] = int(
            review_df["Temuan"].fillna("").str.split("; ").map(lambda items: STATUS_DATA_LIP_TIDAK_SESUAI in items).sum()
        )
    return summary


def build_content_summary(
    review_df: pd.DataFrame,
    claims_df: pd.DataFrame,
    *,
    use_ocr: bool = False,
    required_components: list[str] | None = None,
) -> dict[str, int]:
    if required_components is not None:
        return {
            "Total PDF": int(len(review_df)),
            "PDF dibaca": int((review_df["PDF Dapat Dibaca"] == YES).sum()) if not review_df.empty else 0,
            **{
                component: int((review_df[component] == YES).sum()) if not review_df.empty else 0
                for component in required_components
            },
            "Kurang komponen": int((review_df["Status Akhir"] == STATUS_KURANG_KOMPONEN).sum()) if not review_df.empty else 0,
            "Perlu review manual": int((review_df["Status Akhir"] == STATUS_REVIEW_MANUAL).sum()) if not review_df.empty else 0,
            "Isi lengkap": int((review_df["Status Akhir"] == STATUS_LENGKAP).sum()) if not review_df.empty else 0,
        }
    if use_ocr:
        return build_ocr_content_summary(review_df)
    if review_df.empty:
        return {
            "Total PDF": 0,
            "PDF dibaca": 0,
            "SEP terdeteksi di PDF": 0,
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
        "SEP terdeteksi di PDF": int((review_df["SEP Terdeteksi Dalam PDF"] == YES).sum()),
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
            "SEP terdeteksi di PDF": 0,
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
        "SEP terdeteksi di PDF": int((review_df["SEP Terdeteksi Dalam PDF"] == YES).sum()),
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
    findings: list[str] = []
    row = _base_file_row(claim, sep)

    if not sep_valid:
        row["Status Akhir"] = STATUS_REVIEW_MANUAL
        row["Temuan"] = STATUS_REVIEW_MANUAL
        row["Catatan"] = "No SEP kosong atau format SEP tidak valid."
        return row

    matched_index = index_entries[index_entries["no_sep"] == sep] if not index_entries.empty else index_entries
    if matched_index.empty:
        row["Status Akhir"] = STATUS_KURANG_PDF
        row["Temuan"] = STATUS_KURANG_PDF
        row["Catatan"] = "File PDF untuk SEP ini belum ditemukan."
        return row

    _apply_file_match(row, claim, matched_index, notes)

    if row["Duplikat"] == YES:
        findings.append(STATUS_DUPLIKAT)
    if row["Status Folder"] == STATUS_FOLDER_SALAH:
        findings.append(STATUS_SALAH_FOLDER)
    elif row["Status Folder"] == STATUS_FOLDER_TIDAK_TERDETEKSI:
        findings.append(STATUS_REVIEW_MANUAL)

    lip_status = STATUS_LENGKAP
    if lip_metadata_results is not None:
        lip_status = _apply_lip_metadata_check(row, sep, lip_metadata_results, notes)
        if lip_status != STATUS_LENGKAP:
            findings.append(lip_status)
        if any(row.get(column) == NO for column in (
            "Tanggal Masuk Sesuai", "Tanggal Keluar Sesuai", "Kelas Perawatan Sesuai"
        )):
            findings.append(STATUS_DATA_LIP_TIDAK_SESUAI)
    icd_status = STATUS_LENGKAP
    if icd_check_results is not None:
        icd_status = _apply_icd_check(row, sep, icd_check_results, notes)
        if icd_status != STATUS_LENGKAP:
            findings.append(icd_status)

    row["Temuan"] = "; ".join(_unique_non_empty(findings))
    priority = [STATUS_DUPLIKAT, STATUS_SALAH_FOLDER, STATUS_REVIEW_MANUAL,
                STATUS_DATA_LIP_TIDAK_SESUAI, STATUS_ICD_TIDAK_SESUAI]
    row["Status Akhir"] = next((status for status in priority if status in findings), STATUS_LENGKAP)
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
    missing_data = False
    for result_key, column, label in [
        ("tanggal_masuk_match", "Tanggal Masuk Sesuai", "Tanggal masuk"),
        ("tanggal_keluar_match", "Tanggal Keluar Sesuai", "Tanggal keluar"),
        ("kelas_perawatan_match", "Kelas Perawatan Sesuai", "Kelas perawatan"),
    ]:
        match_value = _result_value(result, result_key, None)
        if match_value is None:
            row[column] = "-"
            missing_data = True
            notes.append(f"{label} tidak tersedia sebagai data pembanding.")
            continue
        row[column] = bool_to_ya_tidak(bool(match_value))
        if not match_value:
            detected_key = {
                "tanggal_masuk_match": "tanggal_masuk_lip",
                "tanggal_keluar_match": "tanggal_keluar_lip",
                "kelas_perawatan_match": "kelas_perawatan_lip",
            }[result_key]
            if not _result_value(result, detected_key, ""):
                row[column] = "-"
                missing_data = True
                notes.append(f"{label} tidak ditemukan di LIP.")
            else:
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
    if missing_data or not _result_value(result, "lip_page_number", None):
        if not _result_value(result, "lip_page_number", None):
            notes.append("Halaman LIP tidak terdeteksi di PDF.")
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
        notes.append("Verifikasi kode ICD tidak menghasilkan data untuk SEP ini.")
        return STATUS_REVIEW_MANUAL

    icd10_missing = list(_result_value(result, "icd10_missing", []) or [])
    icd9_missing = list(_result_value(result, "icd9_missing", []) or [])
    readable = bool(_result_value(result, "readable", False))

    missing_codes = _unique_non_empty(icd10_missing + icd9_missing)

    if not readable:
        row["ICD-10 Sesuai"] = "-"
        row["ICD-9-CM Sesuai"] = "-"
        row["Kode Tidak Ditemukan di PDF"] = ""
        notes.append("Halaman pertama PDF tidak dapat dibaca untuk verifikasi kode ICD.")
        return STATUS_REVIEW_MANUAL

    row["ICD-10 Sesuai"] = bool_to_ya_tidak(not icd10_missing)
    row["ICD-9-CM Sesuai"] = bool_to_ya_tidak(not icd9_missing)
    row["Kode Tidak Ditemukan di PDF"] = ", ".join(missing_codes)

    if missing_codes:
        notes.append(f"Kode tidak ditemukan di halaman pertama PDF: {', '.join(missing_codes)}.")
        return STATUS_ICD_TIDAK_SESUAI

    return STATUS_LENGKAP


def _review_one_pdf_content(
    *,
    entry: pd.Series,
    pdf_results_by_source_id: dict[str, Any],
    use_ocr: bool,
    required_components: list[str] | None = None,
) -> dict[str, object]:
    source_id = str(entry.get("source_id", ""))
    filename_sep = str(entry.get("no_sep", "") or "")
    pdf_result = pdf_results_by_source_id.get(source_id)
    notes: list[str] = []
    required_components = required_components if required_components is not None else (
        OCR_REQUIRED_COMPONENTS if use_ocr else REQUIRED_COMPONENTS
    )
    known_components = [
        "SEP Terdeteksi Dalam PDF", "LIP Terdeteksi", "Rincian Tagihan Terdeteksi",
        "Hasil Scan Terdeteksi", "Resume Medis", "Triage", "Surat Perintah Rawat Inap",
        "Hasil Pemeriksaan", "Pemeriksaan Radiologi",
    ]
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
        "SEP Dalam PDF": "",
        "Bukti Halaman": "",
    }
    for component in known_components:
        if component not in required_components:
            row[component] = "Tidak berlaku"

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
    for component in CONTENT_COMPONENTS:
        if component in detected_titles and component in row:
            row[component] = YES

    error = _result_value(pdf_result, "error", "")
    if error:
        notes.append(str(error))
    for note in _result_value(pdf_result, "notes", []) or []:
        if note:
            notes.append(str(note))

    missing_components = [col for col in required_components if row.get(col, NO) != YES]
    sep_mismatch = bool(filename_sep and pdf_sep_values and filename_sep not in set(pdf_sep_values))
    multiple_pdf_seps = len(set(pdf_sep_values)) > 1
    if sep_mismatch:
        notes.append("Nomor SEP pada nama file berbeda dengan SEP yang terdeteksi di isi PDF.")
    if multiple_pdf_seps:
        notes.append("Lebih dari satu nomor SEP terdeteksi di isi PDF.")
    for component in CONTENT_COMPONENTS:
        if component not in required_components:
            row[component] = "Tidak berlaku"
    if missing_components:
        notes.append("Komponen belum terdeteksi: " + ", ".join(missing_components))
    row["SEP Dalam PDF"] = ", ".join(_unique_non_empty(pdf_sep_values))
    component_pages = _result_value(pdf_result, "component_pages", {}) or {}
    row["Bukti Halaman"] = "; ".join(
        f"{name}: {', '.join(map(str, pages))}"
        for name, pages in component_pages.items() if pages
    )
    identity_unreadable = not bool(_result_value(pdf_result, "readable", False))
    identity_missing = not pdf_sep_values
    if (
        sep_mismatch or multiple_pdf_seps or identity_unreadable or identity_missing
        or _result_value(pdf_result, "needs_manual_review", False)
    ):
        final_status = STATUS_REVIEW_MANUAL
    elif missing_components:
        final_status = STATUS_KURANG_KOMPONEN
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
