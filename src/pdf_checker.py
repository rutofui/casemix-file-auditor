from __future__ import annotations

from dataclasses import dataclass, field
import os

# Must be set before Paddle/PaddleOCR import to avoid oneDNN+PIR crashes on Windows CPU.
os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")

from pathlib import Path
import tempfile
from typing import Any

from .config import (
    BILLING_KEYWORDS,
    DOCUMENT_TITLE_KEYWORDS,
    LIP_KEYWORDS,
    PDFCheckConfig,
    SEP_KEYWORDS,
    contains_keyword,
    detect_document_titles,
    detect_document_titles_from_pages,
    detect_document_titles_on_page,
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
    ocr_enabled: bool = False
    ocr_available: bool = False
    ocr_page_count: int = 0
    ocr_text_char_count: int = 0
    document_titles: list[str] = field(default_factory=list)
    needs_manual_review: bool = False
    error: str = ""
    notes: list[str] = field(default_factory=list)


def is_paddleocr_available() -> bool:
    try:
        import paddleocr  # noqa: F401
    except Exception:
        return False
    return True


def detect_pdf_components(
    text: str,
    *,
    page_texts: list[str] | None = None,
    header_only_ocr_pages: list[bool] | None = None,
) -> dict[str, object]:
    normalized = normalize_text(text)
    if page_texts is not None:
        document_titles = detect_document_titles_from_pages(
            page_texts,
            header_only_ocr_pages=header_only_ocr_pages,
        )
    else:
        document_titles = detect_document_titles_from_pages([text])
    return {
        "sep_values": extract_sep_values(text),
        "sep_keyword_detected": contains_keyword(normalized, SEP_KEYWORDS),
        "lip_detected": contains_keyword(normalized, LIP_KEYWORDS),
        "billing_detected": contains_keyword(normalized, BILLING_KEYWORDS),
        "document_titles": document_titles,
    }


def check_pdf(
    source_id: str,
    local_path: str,
    config: PDFCheckConfig | None = None,
) -> PDFCheckResult:
    config = config or PDFCheckConfig()
    result = PDFCheckResult(source_id=source_id, local_path=local_path)
    result.ocr_enabled = bool(config.use_ocr)

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

    page_contents: list[str] = []
    header_only_ocr_pages: list[bool] = []
    ocr_page_texts: list[str] = []
    all_title_categories: frozenset[str] = frozenset(DOCUMENT_TITLE_KEYWORDS.keys())
    titles_found: set[str] = set()
    try:
        result.page_count = document.page_count
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_text = page.get_text("text") or ""
            page_combined = page_text
            header_only_ocr = False
            page_has_scan = _page_has_scan(page, page_text, config)
            if page_has_scan:
                result.scan_page_count += 1
            all_titles_found = titles_found >= all_title_categories
            if config.use_ocr and not all_titles_found and _page_needs_ocr(page, page_text, config, page_has_scan):
                try:
                    ocr_engine = _get_paddleocr_engine(config)
                    result.ocr_available = True
                except Exception as exc:
                    result.notes.append(
                        "PaddleOCR belum siap, halaman scan tidak diproses OCR: "
                        f"{exc}"
                    )
                    page_contents.append(page_combined)
                    header_only_ocr_pages.append(False)
                    titles_found.update(detect_document_titles_on_page(page_combined))
                    continue
                ocr_text = _ocr_page(page, ocr_engine, config)
                if ocr_text.strip():
                    ocr_page_texts.append(ocr_text)
                    header_only_ocr = True
                    if page_combined.strip():
                        page_combined = f"{page_combined}\n{ocr_text}"
                    else:
                        page_combined = ocr_text
                    result.ocr_page_count += 1
            page_contents.append(page_combined)
            header_only_ocr_pages.append(header_only_ocr)
            titles_found.update(
                detect_document_titles_on_page(page_combined, header_only_ocr=header_only_ocr)
            )

        combined_text = "\n".join(page_contents)
        components = detect_pdf_components(
            combined_text,
            page_texts=page_contents,
            header_only_ocr_pages=header_only_ocr_pages,
        )
        result.readable = True
        result.text_char_count = len(normalize_text(combined_text))
        result.ocr_text_char_count = len(normalize_text("\n".join(ocr_page_texts)))
        result.sep_values = list(components["sep_values"])
        result.sep_keyword_detected = bool(components["sep_keyword_detected"])
        result.lip_detected = bool(components["lip_detected"])
        result.billing_detected = bool(components["billing_detected"])
        result.scan_detected = result.scan_page_count > 0
        result.document_titles = list(components["document_titles"])

        if result.text_char_count < config.min_pdf_text_chars:
            result.notes.append("Teks digital PDF terlalu sedikit; pastikan SEP/LIP/Rincian Tagihan terbaca.")
        if config.use_ocr and result.scan_page_count and result.ocr_page_count:
            skipped = result.scan_page_count - result.ocr_page_count
            note = f"OCR dipakai pada {result.ocr_page_count} halaman scan."
            if skipped > 0:
                note += f" {skipped} halaman scan dilewati (semua komponen sudah terdeteksi)."
            result.notes.append(note)
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


def _page_needs_ocr(
    page: object,
    page_text: str,
    config: PDFCheckConfig,
    page_has_scan: bool,
) -> bool:
    text_is_minimal = len(normalize_text(page_text)) < config.min_page_text_chars
    if text_is_minimal:
        return True
    return page_has_scan and text_is_minimal


_process_ocr_engine: object | None = None
_process_ocr_engine_config_key: tuple[str, str] | None = None


def _ocr_engine_config_key(config: PDFCheckConfig) -> tuple[str, str]:
    return (config.ocr_detection_model_name, config.ocr_recognition_model_name)


def _get_paddleocr_engine(config: PDFCheckConfig) -> object:
    global _process_ocr_engine, _process_ocr_engine_config_key
    config_key = _ocr_engine_config_key(config)
    if _process_ocr_engine is None or _process_ocr_engine_config_key != config_key:
        _process_ocr_engine = _create_paddleocr_engine(config)
        _process_ocr_engine_config_key = config_key
    return _process_ocr_engine


def _create_paddleocr_engine(config: PDFCheckConfig) -> object:
    from paddleocr import PaddleOCR

    return PaddleOCR(
        text_detection_model_name=config.ocr_detection_model_name,
        text_recognition_model_name=config.ocr_recognition_model_name,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="cpu",
        enable_mkldnn=False,
    )


def _run_ocr(ocr_engine: object, image_path: str) -> object:
    if hasattr(ocr_engine, "predict"):
        return ocr_engine.predict(image_path)
    if hasattr(ocr_engine, "ocr"):
        try:
            return ocr_engine.ocr(image_path, cls=True)
        except TypeError:
            return ocr_engine.ocr(image_path)
    raise RuntimeError("PaddleOCR engine tidak memiliki method predict/ocr.")


def _ocr_page(page: object, ocr_engine: object, config: PDFCheckConfig) -> str:
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError(f"PyMuPDF tidak tersedia untuk render OCR: {exc}") from exc

    page_rect = page.rect
    crop_ratio = max(min(float(config.ocr_crop_top_ratio), 1.0), 0.1)
    clip = fitz.Rect(
        page_rect.x0,
        page_rect.y0,
        page_rect.x1,
        page_rect.y0 + page_rect.height * crop_ratio,
    )
    matrix = fitz.Matrix(config.ocr_render_zoom, config.ocr_render_zoom)
    pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
    with tempfile.TemporaryDirectory(prefix="casemix_ocr_") as temp_dir:
        image_path = str(Path(temp_dir) / "page.png")
        pixmap.save(image_path)
        ocr_output = _run_ocr(ocr_engine, image_path)
    return "\n".join(_extract_ocr_texts(ocr_output))


def _extract_ocr_texts(value: object) -> list[str]:
    texts: list[str] = []
    _collect_ocr_texts(value, texts)
    return [text for text in texts if len(text.strip()) >= 2]


def _ocr_result_to_mapping(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    for attr in ("json", "res"):
        payload = getattr(value, attr, None)
        if isinstance(payload, dict):
            return payload
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return payload
    return None


def _collect_ocr_texts(value: object, texts: list[str]) -> None:
    if value is None:
        return
    mapping = _ocr_result_to_mapping(value)
    if mapping is not None:
        value = mapping
    if isinstance(value, dict):
        for key in ("rec_texts", "texts"):
            dict_value = value.get(key)
            if isinstance(dict_value, list):
                for item in dict_value:
                    if isinstance(item, str):
                        texts.append(item)
        for dict_value in value.values():
            _collect_ocr_texts(dict_value, texts)
        return
    if isinstance(value, tuple) and value and isinstance(value[0], str):
        texts.append(value[0])
        return
    if isinstance(value, list):
        for item in value:
            _collect_ocr_texts(item, texts)
