from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
import os
import traceback
from typing import Callable, Iterable

from .config import PDFCheckConfig
from .pdf_checker import (
    FirstPageCodeCheckResult,
    LipMetadataCheckResult,
    PDFCheckResult,
    check_first_page_codes,
    check_lip_metadata,
    check_pdf,
)


MAX_AUTO_PDF_WORKERS = 4
MAX_OCR_PDF_WORKERS = 2


def automatic_pdf_worker_count(total_pdfs: int) -> int:
    if total_pdfs <= 1:
        return 1
    cpu_count = os.cpu_count() or 2
    return max(1, min(total_pdfs, max(cpu_count - 1, 1), MAX_AUTO_PDF_WORKERS))


def resolve_pdf_worker_count(total_pdfs: int, *, use_ocr: bool) -> int:
    worker_count = automatic_pdf_worker_count(total_pdfs)
    if use_ocr:
        return min(worker_count, MAX_OCR_PDF_WORKERS)
    return worker_count


def check_pdfs_parallel(
    jobs: Iterable[tuple[str, str]],
    config: PDFCheckConfig,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    tick_callback: Callable[[], None] | None = None,
) -> dict[str, PDFCheckResult]:
    job_list = list(jobs)
    total = len(job_list)
    if total == 0:
        return {}

    worker_count = resolve_pdf_worker_count(total, use_ocr=config.use_ocr)
    if worker_count == 1:
        return _check_pdfs_serial(
            job_list,
            config,
            progress_callback=progress_callback,
            tick_callback=tick_callback,
        )

    results: dict[str, PDFCheckResult] = {}
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_check_pdf_worker, source_id, local_path, config): (source_id, local_path)
            for source_id, local_path in job_list
        }
        pending = set(futures.keys())
        completed = 0
        while pending:
            done, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
            if tick_callback is not None:
                tick_callback()
            for future in done:
                completed += 1
                source_id, local_path = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = _failed_pdf_result(
                        source_id,
                        local_path,
                        "PDF gagal diproses di worker paralel:\n" + traceback.format_exc(),
                    )
                results[source_id] = result
                if progress_callback is not None:
                    progress_callback(completed, total, source_id)
    return results


def _check_pdfs_serial(
    jobs: list[tuple[str, str]],
    config: PDFCheckConfig,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    tick_callback: Callable[[], None] | None = None,
) -> dict[str, PDFCheckResult]:
    results: dict[str, PDFCheckResult] = {}
    total = len(jobs)
    for completed, (source_id, local_path) in enumerate(jobs, start=1):
        if tick_callback is not None:
            tick_callback()
        try:
            result = check_pdf(source_id=source_id, local_path=local_path, config=config)
        except Exception:
            result = _failed_pdf_result(
                source_id,
                local_path,
                "PDF gagal diproses:\n" + traceback.format_exc(),
            )
        results[source_id] = result
        if progress_callback is not None:
            progress_callback(completed, total, source_id)
    return results


def _check_pdf_worker(
    source_id: str,
    local_path: str,
    config: PDFCheckConfig,
) -> PDFCheckResult:
    return check_pdf(source_id=source_id, local_path=local_path, config=config)


def _failed_pdf_result(source_id: str, local_path: str, error: str) -> PDFCheckResult:
    return PDFCheckResult(
        source_id=source_id,
        local_path=local_path,
        needs_manual_review=True,
        error=error,
    )


def check_first_page_codes_parallel(
    jobs: Iterable[tuple[str, list[str], list[str], list[str]]],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    tick_callback: Callable[[], None] | None = None,
) -> dict[str, FirstPageCodeCheckResult]:
    job_list = list(jobs)
    total = len(job_list)
    if total == 0:
        return {}

    worker_count = automatic_pdf_worker_count(total)
    if worker_count == 1:
        return _check_first_page_codes_serial(
            job_list,
            progress_callback=progress_callback,
            tick_callback=tick_callback,
        )

    results: dict[str, FirstPageCodeCheckResult] = {}
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_check_first_page_codes_worker, sep, local_paths, icd10_codes, icd9_codes): sep
            for sep, local_paths, icd10_codes, icd9_codes in job_list
        }
        pending = set(futures.keys())
        completed = 0
        while pending:
            done, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
            if tick_callback is not None:
                tick_callback()
            for future in done:
                completed += 1
                sep = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = _failed_first_page_result(
                        [],
                        [],
                        "Pengecekan kode ICD gagal di worker paralel:\n" + traceback.format_exc(),
                    )
                results[sep] = result
                if progress_callback is not None:
                    progress_callback(completed, total, sep)
    return results


def _check_first_page_codes_serial(
    jobs: list[tuple[str, list[str], list[str], list[str]]],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    tick_callback: Callable[[], None] | None = None,
) -> dict[str, FirstPageCodeCheckResult]:
    results: dict[str, FirstPageCodeCheckResult] = {}
    total = len(jobs)
    for completed, (sep, local_paths, icd10_codes, icd9_codes) in enumerate(jobs, start=1):
        if tick_callback is not None:
            tick_callback()
        try:
            result = check_first_page_codes(local_paths, icd10_codes, icd9_codes)
        except Exception:
            result = _failed_first_page_result(
                icd10_codes,
                icd9_codes,
                "Pengecekan kode ICD gagal:\n" + traceback.format_exc(),
            )
        results[sep] = result
        if progress_callback is not None:
            progress_callback(completed, total, sep)
    return results


def _check_first_page_codes_worker(
    sep: str,
    local_paths: list[str],
    icd10_codes: list[str],
    icd9_codes: list[str],
) -> FirstPageCodeCheckResult:
    return check_first_page_codes(local_paths, icd10_codes, icd9_codes)


def _failed_first_page_result(
    icd10_codes: list[str],
    icd9_codes: list[str],
    error: str,
) -> FirstPageCodeCheckResult:
    return FirstPageCodeCheckResult(
        readable=False,
        icd10_missing=list(icd10_codes),
        icd9_missing=list(icd9_codes),
        error=error,
    )


def check_lip_metadata_parallel(
    jobs: Iterable[tuple[str, list[str], str, str, str]],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    tick_callback: Callable[[], None] | None = None,
) -> dict[str, LipMetadataCheckResult]:
    job_list = list(jobs)
    total = len(job_list)
    if total == 0:
        return {}

    worker_count = automatic_pdf_worker_count(total)
    if worker_count == 1:
        return _check_lip_metadata_serial(
            job_list,
            progress_callback=progress_callback,
            tick_callback=tick_callback,
        )

    results: dict[str, LipMetadataCheckResult] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _check_lip_metadata_worker,
                sep,
                local_paths,
                tanggal_masuk,
                tanggal_keluar,
                kelas_perawatan,
            ): sep
            for sep, local_paths, tanggal_masuk, tanggal_keluar, kelas_perawatan in job_list
        }
        pending = set(futures.keys())
        completed = 0
        while pending:
            done, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
            if tick_callback is not None:
                tick_callback()
            for future in done:
                completed += 1
                sep = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = LipMetadataCheckResult(
                        readable=False,
                        error="Pengecekan data LIP gagal di worker paralel:\n" + traceback.format_exc(),
                    )
                results[sep] = result
                if progress_callback is not None:
                    progress_callback(completed, total, sep)
    return results


def _check_lip_metadata_serial(
    jobs: list[tuple[str, list[str], str, str, str]],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    tick_callback: Callable[[], None] | None = None,
) -> dict[str, LipMetadataCheckResult]:
    results: dict[str, LipMetadataCheckResult] = {}
    total = len(jobs)
    for completed, (sep, local_paths, tanggal_masuk, tanggal_keluar, kelas_perawatan) in enumerate(jobs, start=1):
        if tick_callback is not None:
            tick_callback()
        try:
            result = check_lip_metadata(
                local_paths,
                expected_tanggal_masuk=tanggal_masuk,
                expected_tanggal_keluar=tanggal_keluar,
                expected_kelas_perawatan=kelas_perawatan,
            )
        except Exception:
            result = LipMetadataCheckResult(
                readable=False,
                error="Pengecekan data LIP gagal:\n" + traceback.format_exc(),
            )
        results[sep] = result
        if progress_callback is not None:
            progress_callback(completed, total, sep)
    return results


def _check_lip_metadata_worker(
    sep: str,
    local_paths: list[str],
    tanggal_masuk: str,
    tanggal_keluar: str,
    kelas_perawatan: str,
) -> LipMetadataCheckResult:
    return check_lip_metadata(
        local_paths,
        expected_tanggal_masuk=tanggal_masuk,
        expected_tanggal_keluar=tanggal_keluar,
        expected_kelas_perawatan=kelas_perawatan,
    )
