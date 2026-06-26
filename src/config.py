from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


APP_NAME = "Casemix File Auditor"

SEP_REGEX = r"\d{4}R\d{3}\d{4}V\d{6}"
SEP_PATTERN = re.compile(SEP_REGEX, re.IGNORECASE)

STATUS_FILE_ADA = "Ada"
STATUS_FILE_BELUM_ADA = "Belum Ada"

STATUS_FOLDER_SESUAI = "Sesuai"
STATUS_FOLDER_SALAH = "Salah Folder"
STATUS_FOLDER_TIDAK_TERDETEKSI = "Tanggal Folder Tidak Terdeteksi"
STATUS_FOLDER_TIDAK_ADA_FILE = "Tidak Ada File"

STATUS_LENGKAP = "Lengkap"
STATUS_KURANG_PDF = "Kurang PDF"
STATUS_KURANG_KOMPONEN = "Kurang Komponen"
STATUS_SALAH_FOLDER = "Salah Folder"
STATUS_DUPLIKAT = "Duplikat"
STATUS_REVIEW_MANUAL = "Perlu Review Manual"

YES = "Ya"
NO = "Tidak"

REQUIRED_COMPONENTS = [
    "SEP Terdeteksi Dalam PDF",
    "LIP Terdeteksi",
    "Rincian Tagihan Terdeteksi",
    "Hasil Scan Terdeteksi",
]

REVIEW_COLUMNS = [
    "No SEP",
    "Tanggal Pulang",
    "No RM",
    "Nama Pasien",
    "Diagnosa",
    "Status File",
    "Path File",
    "Tanggal Folder",
    "Status Folder",
    "Duplikat",
    "SEP Terdeteksi Dalam PDF",
    "LIP Terdeteksi",
    "Rincian Tagihan Terdeteksi",
    "Hasil Scan Terdeteksi",
    "Status Akhir",
    "Catatan",
]

FILE_REVIEW_COLUMNS = [
    "No SEP",
    "Tanggal Pulang",
    "No RM",
    "Nama Pasien",
    "Diagnosa",
    "Status File",
    "Path File",
    "Tanggal Folder",
    "Status Folder",
    "Duplikat",
    "Status Akhir",
    "Catatan",
]

CONTENT_REVIEW_COLUMNS = [
    "No SEP",
    "Nama File",
    "Path File",
    "PDF Dapat Dibaca",
    "SEP Terdeteksi Dalam PDF",
    "LIP Terdeteksi",
    "Rincian Tagihan Terdeteksi",
    "Hasil Scan Terdeteksi",
    "Status Akhir",
    "Catatan",
]

CLAIM_COLUMNS = [
    "No SEP",
    "Tanggal Registrasi",
    "Tanggal Pulang",
    "No RM",
    "Nama Pasien",
    "Instalasi",
    "Diagnosa",
    "Tindakan",
]

SEP_KEYWORDS = [
    "SEP",
    "Nomor SEP",
    "No SEP",
    "Surat Eligibilitas Peserta",
]

LIP_KEYWORDS = [
    "Berkas Klaim Individual Pasien",
    "Lembar Individual Pasien",
    "Individual Pasien",
    "LIP",
]

BILLING_KEYWORDS = [
    "Billing",
    "Rincian Biaya",
    "Rincian Tagihan",
    "Total Biaya",
    "Total Tarif",
    "Tarif Rumah Sakit",
    "Administrasi",
    "Hasil Grouping",
    "INA-CBG",
    "Barang",
    "Jasa",
    "Fasilitas",
]

@dataclass(frozen=True)
class PDFCheckConfig:
    min_page_text_chars: int = 40
    min_pdf_text_chars: int = 80
    min_scan_image_area_ratio: float = 0.18


def normalize_sep(value: object) -> str:
    """Normalize a SEP value without inventing separators or changing digits."""
    if value is None:
        return ""
    text = str(value).strip().upper()
    if text in {"", "NAN", "NONE", "NAT"}:
        return ""
    return re.sub(r"\s+", "", text)


def is_valid_sep(value: object) -> bool:
    return bool(SEP_PATTERN.fullmatch(normalize_sep(value)))


def extract_sep_values(text: object) -> list[str]:
    if text is None:
        return []
    upper = str(text).upper()
    values = {match.upper() for match in SEP_PATTERN.findall(upper)}
    compact = re.sub(r"\s+", "", upper)
    values.update(match.upper() for match in SEP_PATTERN.findall(compact))
    return sorted(values)


def normalize_text(text: object) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text).upper()).strip()


def contains_keyword(text: str, keywords: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(keyword) in normalized for keyword in keywords)


def bool_to_ya_tidak(value: bool) -> str:
    return YES if value else NO
