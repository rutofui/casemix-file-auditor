from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    BILLING_KEYWORDS,
    LIP_KEYWORDS,
    PDFCheckConfig,
    SEP_KEYWORDS,
    contains_keyword,
    extract_sep_values,
    normalize_text,
)


@dataclass
class PDFCheckResult:
    source_id: str
    local_path: str
    readable: bool = False
    text_char_count: int = 0
    page_count: int = 0
    scan_page_count: int = 0
    sep_values: list[str] = field(default_factory=list)
    sep_keyword_detected: bool = False
    lip_detected: bool = False
    billing_detected: bool = False
    scan_detected: bool = False
    needs_manual_review: bool = False
    error: str = ""
    notes: list[str] = field(default_factory=list)


def is_tesseract_available() -> bool:
    return False


def detect_pdf_components(text: str) -> dict[str, object]:
    normalized = normalize_text(text)
    return {
        "sep_values": extract_sep_values(text),
        "sep_keyword_detected": contains_keyword(normalized, SEP_KEYWORDS),
        "lip_detected": contains_keyword(normalized, LIP_KEYWORDS),
        "billing_detected": contains_keyword(normalized, BILLING_KEYWORDS),
    }


def check_pdf(
    source_id: str,
    local_path: str,
    config: PDFCheckConfig | None = None,
) -> PDFCheckResult:
    config = config or PDFCheckConfig()
    result = PDFCheckResult(source_id=source_id, local_path=local_path)

    path = Path(local_path)
    if not local_path or not path.exists():
        result.error = "File PDF tidak dapat diakses."
        result.needs_manual_review = True
        return result

    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        result.error = f"PyMuPDF belum tersedia: {exc}"
        result.needs_manual_review = True
        return result

    try:
        document = fitz.open(str(path))
    except Exception as exc:
        result.error = f"PDF gagal dibuka: {exc}"
        result.needs_manual_review = True
        return result

    page_texts: list[str] = []
    try:
        result.page_count = document.page_count
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_text = page.get_text("text") or ""
            page_texts.append(page_text)
            if _page_has_scan(page, page_text, config):
                result.scan_page_count += 1

        combined_text = "\n".join(page_texts)
        components = detect_pdf_components(combined_text)
        result.readable = True
        result.text_char_count = len(normalize_text(combined_text))
        result.sep_values = list(components["sep_values"])
        result.sep_keyword_detected = bool(components["sep_keyword_detected"])
        result.lip_detected = bool(components["lip_detected"])
        result.billing_detected = bool(components["billing_detected"])
        result.scan_detected = result.scan_page_count > 0

        if result.text_char_count < config.min_pdf_text_chars:
            result.notes.append("Teks digital PDF terlalu sedikit; pastikan SEP/LIP/Rincian Tagihan terbaca.")
    finally:
        document.close()

    return result


def _page_has_scan(page: object, page_text: str, config: PDFCheckConfig) -> bool:
    image_area = 0.0
    page_area = max(float(page.rect.width * page.rect.height), 1.0)

    try:
        image_infos = page.get_image_info(xrefs=True)
    except Exception:
        image_infos = []

    for image_info in image_infos:
        bbox = image_info.get("bbox")
        if not bbox:
            continue
        width = max(float(bbox[2] - bbox[0]), 0.0)
        height = max(float(bbox[3] - bbox[1]), 0.0)
        image_area += width * height

    image_ratio = image_area / page_area
    if image_ratio >= config.min_scan_image_area_ratio:
        return True

    has_images = bool(image_infos)
    has_minimal_text = len((page_text or "").strip()) < config.min_page_text_chars
    return has_images and has_minimal_text
