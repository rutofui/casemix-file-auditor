from __future__ import annotations

from dataclasses import dataclass, field
import os
import re

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
    LIP_EVIDENCE_KEYWORDS,
    PDFCheckConfig,
    SEP_KEYWORDS,
    code_present_in_text,
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
    component_pages: dict[str, list[int]] = field(default_factory=dict)


@dataclass
class FirstPageCodeCheckResult:
    readable: bool = False
    icd10_missing: list[str] = field(default_factory=list)
    icd9_missing: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class LipMetadataCheckResult:
    readable: bool = False
    tanggal_masuk_lip: str = ""
    tanggal_keluar_lip: str = ""
    kelas_perawatan_lip: str = ""
    tanggal_masuk_match: bool | None = None
    tanggal_keluar_match: bool | None = None
    kelas_perawatan_match: bool | None = None
    lip_page_number: int | None = None
    error: str = ""
    notes: list[str] = field(default_factory=list)


def check_lip_metadata(
    local_paths: list[str],
    *,
    expected_tanggal_masuk: str = "",
    expected_tanggal_keluar: str = "",
    expected_kelas_perawatan: str = "",
) -> LipMetadataCheckResult:
    if not local_paths:
        return LipMetadataCheckResult(readable=False, error="Tidak ada path PDF untuk diperiksa.")
    if len(local_paths) > 1:
        results = [
            check_lip_metadata(
                [path],
                expected_tanggal_masuk=expected_tanggal_masuk,
                expected_tanggal_keluar=expected_tanggal_keluar,
                expected_kelas_perawatan=expected_kelas_perawatan,
            )
            for path in local_paths
        ]

        def aggregate_match(key: str, value_key: str) -> bool | None:
            values = [
                getattr(result, key) if getattr(result, value_key) else None
                for result in results
            ]
            return False if False in values else (None if any(value is None for value in values) else True)

        return LipMetadataCheckResult(
            readable=all(
                result.readable
                and (not expected_tanggal_masuk or bool(result.tanggal_masuk_lip))
                and (not expected_tanggal_keluar or bool(result.tanggal_keluar_lip))
                and (not expected_kelas_perawatan or bool(result.kelas_perawatan_lip))
                for result in results
            ),
            tanggal_masuk_lip=" | ".join(_unique_preserve_order([r.tanggal_masuk_lip for r in results])),
            tanggal_keluar_lip=" | ".join(_unique_preserve_order([r.tanggal_keluar_lip for r in results])),
            kelas_perawatan_lip=" | ".join(_unique_preserve_order([r.kelas_perawatan_lip for r in results])),
            tanggal_masuk_match=aggregate_match("tanggal_masuk_match", "tanggal_masuk_lip"),
            tanggal_keluar_match=aggregate_match("tanggal_keluar_match", "tanggal_keluar_lip"),
            kelas_perawatan_match=aggregate_match("kelas_perawatan_match", "kelas_perawatan_lip"),
            lip_page_number=next((r.lip_page_number for r in results if r.lip_page_number), None),
            error="; ".join(_unique_preserve_order([r.error for r in results])),
            notes=_unique_preserve_order([note for r in results for note in r.notes]),
        )

    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        return LipMetadataCheckResult(readable=False, error=f"PyMuPDF belum tersedia: {exc}")

    page_texts: list[str] = []
    page_numbers: list[int] = []
    page_locations: list[str] = []
    errors: list[str] = []
    for local_path in local_paths:
        path = Path(local_path)
        if not local_path or not path.exists():
            errors.append("File PDF tidak dapat diakses.")
            continue
        try:
            document = fitz.open(str(path))
        except Exception as exc:
            errors.append(f"PDF gagal dibuka: {exc}")
            continue
        try:
            for page_index in range(document.page_count):
                page_text = document.load_page(page_index).get_text("text") or ""
                page_texts.append(page_text)
                if _is_lip_page(page_text):
                    page_numbers.append(page_index + 1)
                    page_locations.append(f"LIP: {path.name}, halaman {page_index + 1}")
        except Exception as exc:
            errors.append(f"Halaman PDF gagal dibaca: {exc}")
        finally:
            document.close()

    lip_text = _select_lip_text(page_texts)
    if not lip_text.strip():
        return LipMetadataCheckResult(
            readable=False,
            error="Halaman LIP tidak terbaca dari teks digital PDF.",
            notes=_unique_preserve_order([*errors, *page_locations]),
        )

    detected_tanggal_masuk = _extract_labeled_date(lip_text, ["Tanggal Masuk", "Tgl Masuk", "Tgl. Masuk"])
    detected_tanggal_keluar = _extract_labeled_date(
        lip_text,
        ["Tanggal Keluar", "Tgl Keluar", "Tgl. Keluar", "Tanggal Pulang", "Tgl Pulang", "Tgl. Pulang"],
    )
    detected_kelas = _extract_labeled_care_class(
        lip_text,
        ["Kelas Perawatan", "Kelas Rawat", "Hak Kelas", "Kelas", "Ruang Perawatan"],
    )

    result = LipMetadataCheckResult(
        readable=not errors,
        tanggal_masuk_lip=detected_tanggal_masuk,
        tanggal_keluar_lip=detected_tanggal_keluar,
        kelas_perawatan_lip=detected_kelas,
        tanggal_masuk_match=_compare_dates(expected_tanggal_masuk, detected_tanggal_masuk),
        tanggal_keluar_match=_compare_dates(expected_tanggal_keluar, detected_tanggal_keluar),
        kelas_perawatan_match=_compare_care_class(expected_kelas_perawatan, detected_kelas),
        lip_page_number=page_numbers[0] if page_numbers else None,
        error="; ".join(_unique_preserve_order(errors)),
    )
    if expected_tanggal_masuk and not detected_tanggal_masuk:
        result.notes.append("Tanggal masuk tidak ditemukan di LIP.")
    if expected_tanggal_keluar and not detected_tanggal_keluar:
        result.notes.append("Tanggal keluar tidak ditemukan di LIP.")
    if expected_kelas_perawatan and not detected_kelas:
        result.notes.append("Kelas perawatan tidak ditemukan di LIP.")
    result.notes.extend(page_locations)
    return result


def check_first_page_codes(
    local_paths: list[str],
    icd10_codes: list[str],
    icd9_codes: list[str],
) -> FirstPageCodeCheckResult:
    """Check whether ICD-10/ICD-9-CM codes are present on the first page of
    each matched PDF file (digital text only, no OCR). Missing codes are
    combined across files so a code absent from any duplicate remains visible.
    """
    if not local_paths:
        return FirstPageCodeCheckResult(
            readable=False,
            icd10_missing=list(icd10_codes),
            icd9_missing=list(icd9_codes),
            error="Tidak ada path PDF untuk diperiksa.",
        )
    if len(local_paths) > 1:
        results = [check_first_page_codes([path], icd10_codes, icd9_codes) for path in local_paths]
        return FirstPageCodeCheckResult(
            readable=all(result.readable for result in results),
            icd10_missing=[code for code in icd10_codes if any(code in r.icd10_missing for r in results)],
            icd9_missing=[code for code in icd9_codes if any(code in r.icd9_missing for r in results)],
            error="; ".join(_unique_preserve_order([result.error for result in results])),
        )

    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        return FirstPageCodeCheckResult(
            readable=False,
            icd10_missing=list(icd10_codes),
            icd9_missing=list(icd9_codes),
            error=f"PyMuPDF belum tersedia: {exc}",
        )

    combined_text_parts: list[str] = []
    errors: list[str] = []
    any_readable = False

    for local_path in local_paths:
        path = Path(local_path)
        if not local_path or not path.exists():
            errors.append("File PDF tidak dapat diakses.")
            continue
        try:
            document = fitz.open(str(path))
        except Exception as exc:
            errors.append(f"PDF gagal dibuka: {exc}")
            continue
        try:
            if document.page_count > 0:
                page = document.load_page(0)
                page_text = page.get_text("text") or ""
                combined_text_parts.append(page_text)
                any_readable = any_readable or bool(page_text.strip())
        except Exception as exc:
            errors.append(f"Halaman pertama PDF gagal dibaca: {exc}")
        finally:
            document.close()

    if not any_readable:
        return FirstPageCodeCheckResult(
            readable=False,
            icd10_missing=list(icd10_codes),
            icd9_missing=list(icd9_codes),
            error="; ".join(_unique_preserve_order(errors)) or "Halaman pertama PDF tidak dapat dibaca.",
        )

    combined_text = "\n".join(combined_text_parts)
    icd10_missing = [code for code in icd10_codes if not code_present_in_text(combined_text, code)]
    icd9_missing = [code for code in icd9_codes if not code_present_in_text(combined_text, code)]

    return FirstPageCodeCheckResult(
        readable=not errors,
        icd10_missing=icd10_missing,
        icd9_missing=icd9_missing,
        error="; ".join(_unique_preserve_order(errors)),
    )


def _select_lip_text(page_texts: list[str]) -> str:
    for text in page_texts:
        if _is_lip_page(text):
            return text
    return ""


def _is_lip_page(text: str) -> bool:
    if contains_keyword(text, LIP_EVIDENCE_KEYWORDS):
        return True
    header = "\n".join(text.splitlines()[:12])
    return bool(
        re.search(r"(?im)^\s*LIP\s*$", header)
        and re.search(r"(?i)Tanggal\s+(Masuk|Keluar)|Kelas\s+(Perawatan|Rawat)", text)
    )


def _has_billing_evidence(text: str) -> bool:
    return contains_keyword(text, BILLING_KEYWORDS) or bool(
        re.search(r"(?im)^\s*BILLING\s*$", text)
    )


def _extract_labeled_date(text: str, labels: list[str]) -> str:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]?\s*([0-3]?\d[\-/ ][01]?\d[\-/ ]\d{{2,4}}|\d{{4}}[\-/ ][01]?\d[\-/ ][0-3]?\d)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _extract_labeled_care_class(text: str, labels: list[str]) -> str:
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]?\s*([A-Za-z0-9 .\-/]+)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = re.split(r"\s{2,}|\n|\r", match.group(1).strip(), maxsplit=1)[0].strip(" .-/")
        if value:
            return value
    return ""


def _normalize_date_value(value: object) -> str:
    if value is None or str(value).strip() == "":
        return ""
    try:
        import pandas as pd
    except Exception:
        return ""
    text = str(value).strip()
    if len(text) >= 10 and text[4] in "-/" and text[7] in "-/":
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    else:
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        return ""
    return f"{int(parsed.year):04d}-{int(parsed.month):02d}-{int(parsed.day):02d}"


def _compare_dates(expected: object, detected: object) -> bool | None:
    expected_date = _normalize_date_value(expected)
    if not expected_date:
        return None
    return expected_date == _normalize_date_value(detected)


def _normalize_care_class(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    if "VVIP" in text:
        return "VVIP"
    if "VIP" in text:
        return "VIP"
    for token in ["NICU", "PICU", "ICU", "HCU"]:
        if contains_keyword(text, [token]):
            return token
    roman_map = {"III": "3", "II": "2", "I": "1"}
    for roman, digit in roman_map.items():
        if re.search(rf"(?<![A-Z0-9]){roman}(?![A-Z0-9])", text):
            return digit
    match = re.search(r"(?<!\d)([123])(?!\d)", text)
    if match:
        return match.group(1)
    return text


def _compare_care_class(expected: object, detected: object) -> bool | None:
    expected_class = _normalize_care_class(expected)
    if not expected_class:
        return None
    return expected_class == _normalize_care_class(detected)


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


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
    pages = page_texts if page_texts is not None else [text]
    component_pages: dict[str, list[int]] = {}
    for page_number, page_text in enumerate(pages, start=1):
        if extract_sep_values(page_text):
            component_pages.setdefault("SEP Terdeteksi Dalam PDF", []).append(page_number)
        if _is_lip_page(page_text):
            component_pages.setdefault("LIP Terdeteksi", []).append(page_number)
        if _has_billing_evidence(page_text):
            component_pages.setdefault("Rincian Tagihan Terdeteksi", []).append(page_number)
        for title in detect_document_titles_on_page(
            page_text,
            header_only_ocr=bool(
                header_only_ocr_pages
                and page_number <= len(header_only_ocr_pages)
                and header_only_ocr_pages[page_number - 1]
            ),
        ):
            component_pages.setdefault(title, []).append(page_number)
    return {
        "sep_values": extract_sep_values(text),
        "sep_keyword_detected": contains_keyword(normalized, SEP_KEYWORDS),
        "lip_detected": bool(component_pages.get("LIP Terdeteksi")),
        "billing_detected": any(_has_billing_evidence(page) for page in pages),
        "document_titles": document_titles,
        "component_pages": component_pages,
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
            try:
                page = document.load_page(page_index)
                page_text = page.get_text("text") or ""
            except Exception as exc:
                result.needs_manual_review = True
                result.notes.append(f"Halaman {page_index + 1} gagal dibaca: {exc}")
                page_contents.append("")
                header_only_ocr_pages.append(False)
                continue
            page_combined = page_text
            header_only_ocr = False
            try:
                page_has_scan = _page_has_scan(page, page_text, config)
            except Exception as exc:
                page_has_scan = False
                result.needs_manual_review = True
                result.notes.append(f"Gagal memeriksa gambar halaman {page_index + 1}: {exc}")
            if page_has_scan:
                result.scan_page_count += 1
                result.component_pages.setdefault("Hasil Scan Terdeteksi", []).append(page_index + 1)
            all_titles_found = titles_found >= all_title_categories
            if config.use_ocr and not all_titles_found and _page_needs_ocr(page, page_text, config, page_has_scan):
                try:
                    ocr_engine = _get_paddleocr_engine(config)
                    result.ocr_available = True
                except Exception as exc:
                    result.needs_manual_review = True
                    result.notes.append(
                        "PaddleOCR belum siap, halaman scan tidak diproses OCR: "
                        f"{exc}"
                    )
                    page_contents.append(page_combined)
                    header_only_ocr_pages.append(False)
                    titles_found.update(detect_document_titles_on_page(page_combined))
                    continue
                try:
                    ocr_text = _ocr_page(page, ocr_engine, config)
                except Exception as exc:
                    result.needs_manual_review = True
                    result.notes.append(f"OCR gagal pada halaman {page_index + 1}: {exc}")
                    page_contents.append(page_combined)
                    header_only_ocr_pages.append(False)
                    titles_found.update(detect_document_titles_on_page(page_combined))
                    continue
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
        for name, pages in components["component_pages"].items():
            result.component_pages.setdefault(name, []).extend(pages)

        if result.text_char_count < config.min_pdf_text_chars:
            result.notes.append("Teks digital PDF terlalu sedikit; pastikan SEP/LIP/Rincian Tagihan terbaca.")
            result.needs_manual_review = True
        if config.use_ocr and result.scan_page_count and result.ocr_page_count:
            skipped = result.scan_page_count - result.ocr_page_count
            note = f"OCR dipakai pada {result.ocr_page_count} halaman scan."
            if skipped > 0:
                note += f" {skipped} halaman scan tidak memerlukan OCR atau tidak menghasilkan teks OCR."
            result.notes.append(note)
    finally:
        document.close()

    return result


def _page_has_scan(page: object, page_text: str, config: PDFCheckConfig) -> bool:
    image_area = 0.0
    page_area = max(float(page.rect.width * page.rect.height), 1.0)

    image_infos = page.get_image_info(xrefs=True)

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

    has_minimal_text = len((page_text or "").strip()) < config.min_page_text_chars
    return has_minimal_text and image_ratio >= config.min_scan_fallback_image_area_ratio


def _page_needs_ocr(
    page: object,
    page_text: str,
    config: PDFCheckConfig,
    page_has_scan: bool,
) -> bool:
    text_is_minimal = len(normalize_text(page_text)) < config.min_page_text_chars
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
