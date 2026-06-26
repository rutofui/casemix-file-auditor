from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import traceback
from typing import Callable, Iterable

from .config import PDFCheckConfig
from .pdf_checker import PDFCheckResult, check_pdf


MAX_AUTO_PDF_WORKERS = 4


def automatic_pdf_worker_count(total_pdfs: int) -> int:
    if total_pdfs <= 1:
        return 1
    cpu_count = os.cpu_count() or 2
    return max(1, min(total_pdfs, max(cpu_count - 1, 1), MAX_AUTO_PDF_WORKERS))


def check_pdfs_parallel(
    jobs: Iterable[tuple[str, str]],
    config: PDFCheckConfig,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, PDFCheckResult]:
    job_list = list(jobs)
    total = len(job_list)
    if total == 0:
        return {}

    worker_count = automatic_pdf_worker_count(total)
    if worker_count == 1:
        return _check_pdfs_serial(job_list, config, progress_callback=progress_callback)

    results: dict[str, PDFCheckResult] = {}
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_check_pdf_worker, source_id, local_path, config): (source_id, local_path)
            for source_id, local_path in job_list
        }
        for completed, future in enumerate(as_completed(futures), start=1):
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
) -> dict[str, PDFCheckResult]:
    results: dict[str, PDFCheckResult] = {}
    total = len(jobs)
    for completed, (source_id, local_path) in enumerate(jobs, start=1):
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
