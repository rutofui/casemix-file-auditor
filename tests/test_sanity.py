from __future__ import annotations

from pathlib import Path
import tempfile

import pandas as pd

from src.config import PDFCheckConfig
from src.matcher import build_file_review, build_pdf_content_review
from src.parser_excel import read_claims_excel
from src.parser_file_list import build_file_entry, parse_file_list_text, scan_pdf_folder
from src.pdf_parallel import check_pdfs_parallel
from src.pdf_checker import check_pdf


def _write_pdf(path: Path, text: str, *, with_scan_image: bool = False) -> None:
    import fitz
    from PIL import Image, ImageDraw, ImageFont

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), text, fontsize=10)

    image_path = None
    if with_scan_image:
        image_path = path.with_suffix(".png")
        image = Image.new("RGB", (1600, 1000), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=42)
        y = 80
        for line in ["HASIL SCAN BERKAS KLAIM", "Dokumen scan dari rekam medis"]:
            draw.text((80, y), line, fill="black", font=font)
            y += 70
        image.save(image_path)
        page.insert_image(fitz.Rect(60, 180, 535, 520), filename=str(image_path))

    doc.save(path)
    doc.close()
    if image_path:
        image_path.unlink(missing_ok=True)


def _complete_claim_text(sep: str) -> str:
    return "\n".join(
        [
            f"Nomor SEP {sep}",
            "Berkas Klaim Individual Pasien",
            "Rincian Tagihan Barang Jasa Fasilitas Total Tarif INA-CBG",
        ]
    )


def test_file_review_and_content_review_with_scan_component() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        excel_path = root / "klaim.xlsx"
        sep_complete = "0132R0770526V001270"
        sep_missing_pdf = "0132R0770526V001271"
        sep_wrong_folder = "0132R0770526V001272"

        pd.DataFrame(
            [
                {
                    "No SEP": sep_complete,
                    "Tanggal Pulang": "2026-05-01",
                    "No RM": "RM001",
                    "Nama Pasien": "Pasien A",
                    "Diagnosa": "A00",
                },
                {
                    "No SEP": sep_missing_pdf,
                    "Tanggal Pulang": "2026-05-02",
                    "No RM": "RM002",
                    "Nama Pasien": "Pasien B",
                    "Diagnosa": "B00",
                },
                {
                    "No SEP": "",
                    "Tanggal Pulang": "2026-05-03",
                    "No RM": "RM003",
                    "Nama Pasien": "Pasien C",
                    "Diagnosa": "C00",
                },
                {
                    "No SEP": sep_wrong_folder,
                    "Tanggal Pulang": "2026-05-01",
                    "No RM": "RM004",
                    "Nama Pasien": "Pasien D",
                    "Diagnosa": "D00",
                },
            ]
        ).to_excel(excel_path, index=False)

        pdf_path = root / "Casemix" / "Pending" / "2026" / "05. Mei" / "Rawat inap" / "01" / f"{sep_complete}.pdf"
        _write_pdf(pdf_path, _complete_claim_text(sep_complete), with_scan_image=True)
        wrong_folder_pdf_path = (
            root
            / "Casemix"
            / "Pending"
            / "2026"
            / "05. Mei"
            / "Rawat inap"
            / "02"
            / f"{sep_wrong_folder}.pdf"
        )
        _write_pdf(wrong_folder_pdf_path, _complete_claim_text(sep_wrong_folder), with_scan_image=True)
        list_text = "\n".join(
            [
                str(pdf_path.parent),
                str(pdf_path),
                str(wrong_folder_pdf_path),
                str(root / "readme.txt"),
            ]
        )

        claims = read_claims_excel(str(excel_path)).df
        files = parse_file_list_text(list_text).df
        pdf_results = {
            row["source_id"]: check_pdf(
                str(row["source_id"]),
                str(row["local_path"]),
                PDFCheckConfig(),
            )
            for _, row in files.iterrows()
        }
        file_review_df, orphan_df, file_summary = build_file_review(claims, files)
        content_review_df, _, content_summary = build_pdf_content_review(files, pdf_results)

        assert file_summary["Total klaim"] == 4
        assert file_summary["Total SEP valid"] == 3
        assert file_review_df.loc[0, "Status Akhir"] == "Lengkap"
        assert file_review_df.loc[0, "Status Folder"] == "Sesuai"
        assert file_review_df.loc[1, "Status Akhir"] == "Kurang PDF"
        assert file_review_df.loc[2, "Status Akhir"] == "Perlu Review Manual"
        assert file_review_df.loc[3, "Status Akhir"] == "Salah Folder"
        assert content_summary["Total PDF"] == 2
        assert content_summary["Isi lengkap"] == 2
        assert content_summary["Hasil scan"] == 2
        assert content_review_df.loc[0, "Hasil Scan Terdeteksi"] == "Ya"
        assert content_review_df.loc[0, "Status Akhir"] == "Lengkap"
        assert orphan_df.empty


def test_content_review_requires_scan_image() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        sep = "0132R0770526V001270"
        pdf_path = root / f"{sep}.pdf"
        _write_pdf(pdf_path, _complete_claim_text(sep), with_scan_image=False)
        entry = build_file_entry(
            pdf_path.name,
            local_path=str(pdf_path),
            source="upload",
            is_index_source=False,
            is_content_source=True,
        )
        files = pd.DataFrame([entry])
        pdf_results = {
            entry["source_id"]: check_pdf(
                str(entry["source_id"]),
                str(entry["local_path"]),
                PDFCheckConfig(),
            )
        }

        review_df, _, summary = build_pdf_content_review(files, pdf_results)

        assert summary["Kurang komponen"] == 1
        assert review_df.loc[0, "Status Akhir"] == "Kurang Komponen"
        assert review_df.loc[0, "Hasil Scan Terdeteksi"] == "Tidak"
        assert "Hasil Scan Terdeteksi" in review_df.loc[0, "Catatan"]


def test_parallel_pdf_check_matches_serial_results() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        sep_complete = "0132R0770526V001270"
        sep_missing_scan = "0132R0770526V001271"
        complete_pdf = root / f"{sep_complete}.pdf"
        missing_scan_pdf = root / f"{sep_missing_scan}.pdf"
        config = PDFCheckConfig()

        _write_pdf(complete_pdf, _complete_claim_text(sep_complete), with_scan_image=True)
        _write_pdf(missing_scan_pdf, _complete_claim_text(sep_missing_scan), with_scan_image=False)

        jobs = [
            ("complete", str(complete_pdf)),
            ("missing_scan", str(missing_scan_pdf)),
        ]
        serial_results = {
            source_id: check_pdf(source_id, local_path, config)
            for source_id, local_path in jobs
        }
        parallel_results = check_pdfs_parallel(jobs, config)

        assert set(parallel_results) == set(serial_results)
        for source_id in serial_results:
            assert parallel_results[source_id].readable == serial_results[source_id].readable
            assert parallel_results[source_id].sep_values == serial_results[source_id].sep_values
            assert parallel_results[source_id].lip_detected == serial_results[source_id].lip_detected
            assert parallel_results[source_id].billing_detected == serial_results[source_id].billing_detected
            assert parallel_results[source_id].scan_detected == serial_results[source_id].scan_detected


def test_file_review_can_scan_local_folder_instead_of_txt_list() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        excel_path = root / "klaim.xlsx"
        sep_complete = "0132R0770526V001270"
        sep_missing_pdf = "0132R0770526V001271"
        sep_wrong_folder = "0132R0770526V001272"

        pd.DataFrame(
            [
                {
                    "No SEP": sep_complete,
                    "Tanggal Pulang": "2026-05-01",
                    "No RM": "RM001",
                    "Nama Pasien": "Pasien A",
                    "Diagnosa": "A00",
                },
                {
                    "No SEP": sep_missing_pdf,
                    "Tanggal Pulang": "2026-05-02",
                    "No RM": "RM002",
                    "Nama Pasien": "Pasien B",
                    "Diagnosa": "B00",
                },
                {
                    "No SEP": sep_wrong_folder,
                    "Tanggal Pulang": "2026-05-01",
                    "No RM": "RM003",
                    "Nama Pasien": "Pasien C",
                    "Diagnosa": "C00",
                },
            ]
        ).to_excel(excel_path, index=False)

        pdf_root = root / "Casemix" / "Pending" / "2026" / "05. Mei" / "Rawat inap"
        complete_pdf = pdf_root / "01" / f"{sep_complete}.pdf"
        wrong_folder_pdf = pdf_root / "02" / f"{sep_wrong_folder}.pdf"
        _write_pdf(complete_pdf, _complete_claim_text(sep_complete), with_scan_image=True)
        _write_pdf(wrong_folder_pdf, _complete_claim_text(sep_wrong_folder), with_scan_image=True)

        claims = read_claims_excel(str(excel_path)).df
        folder_entries = scan_pdf_folder(str(pdf_root), source_name="folder", is_index_source=True).df
        review_df, orphan_df, summary = build_file_review(claims, folder_entries)

        assert summary["Total klaim"] == 3
        assert summary["PDF ditemukan"] == 2
        assert summary["Belum ada PDF"] == 1
        assert review_df.loc[0, "Status Akhir"] == "Lengkap"
        assert review_df.loc[1, "Status Akhir"] == "Kurang PDF"
        assert review_df.loc[2, "Status Akhir"] == "Salah Folder"
        assert orphan_df.empty
