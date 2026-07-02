from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


APP_NAME = "Casemix File Auditor"

GITHUB_REPO = "rutofui/casemix-file-auditor"
GITHUB_DEFAULT_BRANCH = "master"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_DEFAULT_BRANCH}"
GITHUB_BUILD_INFO_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_DEFAULT_BRANCH}/BUILD_INFO.json"
)

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
STATUS_ICD_TIDAK_SESUAI = "Kode ICD Tidak Sesuai"
STATUS_DATA_LIP_TIDAK_SESUAI = "Data LIP Tidak Sesuai"

YES = "Ya"
NO = "Tidak"

REQUIRED_COMPONENTS = [
    "SEP Terdeteksi Dalam PDF",
    "LIP Terdeteksi",
    "Rincian Tagihan Terdeteksi",
    "Hasil Scan Terdeteksi",
]

OCR_REQUIRED_COMPONENTS = [
    "SEP Terdeteksi Dalam PDF",
    "LIP Terdeteksi",
    "Rincian Tagihan Terdeteksi",
    "Resume Medis",
    "Triage",
    "Surat Perintah Rawat Inap",
    "Hasil Pemeriksaan",
    "Pemeriksaan Radiologi",
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

FILE_REVIEW_ICD_COLUMNS = FILE_REVIEW_COLUMNS[:-1] + [
    "ICD-10 Sesuai",
    "ICD-9-CM Sesuai",
    "Kode Tidak Ditemukan di PDF",
] + FILE_REVIEW_COLUMNS[-1:]

FILE_REVIEW_TXT_COLUMNS = FILE_REVIEW_COLUMNS[:2] + [
    "Tanggal Masuk",
    "Kelas Perawatan",
] + FILE_REVIEW_COLUMNS[2:-1] + [
    "Tanggal Masuk LIP",
    "Tanggal Keluar LIP",
    "Kelas Perawatan LIP",
    "Tanggal Masuk Sesuai",
    "Tanggal Keluar Sesuai",
    "Kelas Perawatan Sesuai",
    "ICD-10 Sesuai",
    "ICD-9-CM Sesuai",
    "Kode Tidak Ditemukan di PDF",
] + FILE_REVIEW_COLUMNS[-1:]

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

OCR_CONTENT_REVIEW_COLUMNS = [
    "No SEP",
    "Nama File",
    "Path File",
    "PDF Dapat Dibaca",
    "SEP Terdeteksi Dalam PDF",
    "LIP Terdeteksi",
    "Rincian Tagihan Terdeteksi",
    "Resume Medis",
    "Triage",
    "Surat Perintah Rawat Inap",
    "Hasil Pemeriksaan",
    "Pemeriksaan Radiologi",
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

DOCUMENT_TITLE_KEYWORDS = {
    "Resume Medis": [
        "Resume Medis",
        "Ringkasan Pulang",
        "Discharge Summary",
    ],
    "Triage": [
        "Triage",
        "Triase",
        "Form Triage",
        "Form Triase",
    ],
    "Surat Perintah Rawat Inap": [
        "Surat Perintah Rawat Inap",
        "Surat Perintah Masuk Rawat Inap",
        "Formulir SPRI",
        "Form SPRI",
    ],
    "Hasil Pemeriksaan": [
        "Hasil Pemeriksaan",
        "Pemeriksaan Laboratorium",
        "Laboratorium",
        "Patologi Klinik",
    ],
    "Pemeriksaan Radiologi": [
        "Pemeriksaan Radiologi",
        "Radiologi",
        "Hasil Radiologi",
        "Rontgen",
        "USG",
        "CT Scan",
        "MRI",
    ],
}

SPRI_TITLE_PHRASES = list(DOCUMENT_TITLE_KEYWORDS["Surat Perintah Rawat Inap"])

SPRI_CONTEXT_PHRASES = [
    "Nomor Surat",
    "Mohon perawatan",
    "Tanggal Masuk",
    "Jenis Ruang",
    "DPJP Rawat Inap",
    "Alasan Rawat Inap",
]

SPRI_HEADER_CHAR_LIMIT = 700


@dataclass(frozen=True)
class PDFCheckConfig:
    min_page_text_chars: int = 40
    min_pdf_text_chars: int = 80
    min_scan_image_area_ratio: float = 0.18
    min_scan_fallback_image_area_ratio: float = 0.04
    use_ocr: bool = False
    ocr_render_zoom: float = 1.5
    ocr_crop_top_ratio: float = 1 / 3
    ocr_detection_model_name: str = "PP-OCRv6_small_det"
    ocr_recognition_model_name: str = "PP-OCRv6_small_rec"


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


def contains_whole_word(text: str, word: str) -> bool:
    token = normalize_text(word)
    if not token:
        return False
    pattern = rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])"
    return re.search(pattern, normalize_text(text)) is not None


def code_present_in_text(text: str, code: str) -> bool:
    """Boundary-safe presence check for ICD-10/ICD-9-CM codes.

    Unlike contains_whole_word, this also treats "." as a non-boundary
    character so decimal-style ICD-9-CM codes (e.g. "90.59") don't
    partial-match inside a longer numeric token (e.g. "190.591").
    """
    token = normalize_text(code)
    if not token:
        return False
    pattern = rf"(?<![A-Z0-9.]){re.escape(token)}(?![A-Z0-9.])"
    return re.search(pattern, normalize_text(text)) is not None


def document_title_keyword_match(normalized: str, keyword: str) -> bool:
    token = normalize_text(keyword)
    if not token:
        return False
    if " " in token or len(token) > 4:
        return token in normalized
    return contains_whole_word(normalized, token)


def spri_title_in_header(normalized: str) -> bool:
    header = normalized[:SPRI_HEADER_CHAR_LIMIT]
    if any(document_title_keyword_match(header, phrase) for phrase in SPRI_TITLE_PHRASES):
        return True
    return contains_whole_word(header, "SPRI") and (
        "FORMULIR SPRI" in header or "FORM SPRI" in header
    )


def spri_detected_on_page(page_text: str, *, header_only_ocr: bool = False) -> bool:
    normalized = normalize_text(page_text)
    if not spri_title_in_header(normalized):
        return False
    if header_only_ocr:
        return True
    return any(normalize_text(phrase) in normalized for phrase in SPRI_CONTEXT_PHRASES)


def detect_document_titles_on_page(page_text: str, *, header_only_ocr: bool = False) -> list[str]:
    normalized = normalize_text(page_text)
    titles: list[str] = []
    for title, keywords in DOCUMENT_TITLE_KEYWORDS.items():
        if title == "Surat Perintah Rawat Inap":
            if spri_detected_on_page(page_text, header_only_ocr=header_only_ocr):
                titles.append(title)
            continue
        if any(document_title_keyword_match(normalized, keyword) for keyword in keywords):
            titles.append(title)
    return titles


def detect_document_titles_from_pages(
    page_texts: Iterable[str],
    *,
    header_only_ocr_pages: Iterable[bool] | None = None,
) -> list[str]:
    pages = list(page_texts)
    flags = list(header_only_ocr_pages) if header_only_ocr_pages is not None else [False] * len(pages)
    if len(flags) != len(pages):
        flags = [False] * len(pages)
    detected: set[str] = set()
    for page_text, header_only_ocr in zip(pages, flags):
        detected.update(
            detect_document_titles_on_page(page_text, header_only_ocr=header_only_ocr)
        )
    return [title for title in DOCUMENT_TITLE_KEYWORDS if title in detected]


def detect_document_titles(text: str) -> list[str]:
    return detect_document_titles_on_page(text)


def bool_to_ya_tidak(value: bool) -> str:
    return YES if value else NO
