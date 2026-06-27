# Casemix File Auditor

Aplikasi web lokal untuk membantu tim casemix rumah sakit mereview berkas klaim JKN sebelum diajukan. Aplikasi memisahkan dua proses kerja: review kelengkapan jumlah berkas dan review kelengkapan isi berkas.

Data diproses lokal di komputer/server internal. Aplikasi tidak memakai API eksternal dan tidak mengirim data pasien ke cloud.

## Struktur Project

```text
app.py
requirements.txt
README.md
src/
  parser_excel.py
  parser_file_list.py
  pdf_checker.py
  matcher.py
  exporter.py
  config.py
```

## 1. Install Dependency

Disarankan memakai virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Di Windows:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`install.bat` di Windows memakai `pip install --no-cache-dir` supaya cache download dependency tidak menambah ukuran folder.

## 1.1. Menjaga Folder Project Tetap Ringan

Folder `.venv` berisi dependency Python dan ukurannya jauh lebih besar daripada kode aplikasi. Folder ini boleh dihapus dan dibuat ulang kapan pun dengan `install.bat`.

Saat menyimpan atau membagikan aplikasi, cukup sertakan:

- `app.py`
- `src/`
- `requirements.txt`
- `install.bat`
- `run_app.bat`
- `clean.bat`
- `README.md`
- `scripts/`
- `tests/`

File/folder seperti `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, log, dan hasil export Excel tidak perlu ikut dibagikan.

Untuk membersihkan cache dan file generated lokal:

```bat
clean.bat
```

## 2. Menjalankan Aplikasi

```bash
streamlit run app.py
```

Browser akan membuka aplikasi Streamlit. Jika tidak terbuka otomatis, buka URL yang muncul di terminal, biasanya `http://localhost:8501`.

## Proses Review

### 1. Review Jumlah Berkas

Proses ini hanya mencocokkan data Excel dengan daftar/path PDF. Tidak membaca isi PDF.

Input proses ini terpisah dari review isi berkas:

- Excel daftar klaim untuk review jumlah berkas.
- Sumber data PDF, pilih salah satu:
  - `list_berkas_klaim.txt`.
  - Folder Berkas Lokal yang dapat diakses komputer/server aplikasi.

Yang dicek:

- SEP di Excel memiliki PDF atau belum.
- PDF berada di folder tanggal yang sesuai dengan `Tanggal Pulang`.
- Duplikat PDF berdasarkan nomor SEP.
- PDF yang ada di folder/list tetapi SEP-nya tidak ada di Excel.

Output export: `hasil_review_jumlah_berkas.xlsx`.

### 2. Review Isi Berkas

Proses ini membaca teks digital PDF dan mendeteksi apakah PDF juga memuat halaman/gambar hasil scan. Aplikasi tidak menjalankan OCR.

Review isi berkas memproses beberapa PDF sekaligus secara otomatis dengan batas worker konservatif (maks. 4 worker tanpa OCR, maks. 2 worker dengan OCR) agar lebih cepat pada batch besar tanpa membebani komputer secara berlebihan.

Mode scan isi PDF:

- `Tanpa OCR`: mode cepat seperti sebelumnya. Komponen yang dicek adalah SEP, LIP, Rincian Tagihan, dan Hasil Scan.
- `Dengan OCR`: aplikasi memakai PaddleOCR 3.x (model **PP-OCRv6_small**) hanya pada bagian **1/3 atas** halaman scan tanpa teks digital, untuk mendeteksi judul Resume Medis, Triage, Surat Perintah Rawat Inap, Hasil Pemeriksaan, dan Pemeriksaan Radiologi. OCR berhenti lebih awal jika semua judul sudah terdeteksi.

Pada mode OCR, halaman yang teks digitalnya sudah terbaca tidak diproses OCR. OCR membutuhkan dependency lebih besar (`paddlepaddle` >= 3.3 dan `paddleocr` >= 3.7) dan proses pertama kali bisa lebih lama karena model OCR perlu diunduh/disiapkan. Untuk batch OCR di mesin RAM terbatas, kurangi jumlah PDF sekaligus atau tutup aplikasi lain.

Input proses ini terpisah dari review jumlah berkas:

- Upload satu atau beberapa PDF.
- Folder PDF lokal untuk batch folder.

Yang dicek:

- SEP.
- LIP / Berkas Klaim Individual Pasien.
- Rincian Tagihan.
- Hasil Scan.

Rincian Tagihan dideteksi dari dokumen billing/rincian biaya atau kata kunci barang, jasa, dan fasilitas.
Hasil Scan dideteksi dari keberadaan gambar/halaman scan di PDF, bukan dari pembacaan isi gambar.

Review isi berkas tidak membutuhkan Excel atau `list_berkas_klaim.txt`. Hasilnya satu baris per PDF yang diperiksa.

Output export: `hasil_review_isi_berkas.xlsx`.

## Akses Domain Cloudflare

Aplikasi ini sudah dikonfigurasi melalui Cloudflare Tunnel:

- Domain publik: `https://casemix.ahmadluthfi.online`
- Service lokal: `http://127.0.0.1:8501`
- Tunnel: `casemix-auditor`
- Config tunnel: `~/.cloudflared/casemix-auditor.yml`

Jalankan service:

```bash
bash scripts/start_services.sh
```

Cek status:

```bash
bash scripts/status_services.sh
```

Hentikan service:

```bash
bash scripts/stop_services.sh
```

Log Streamlit tersimpan di `.streamlit.log`. Log Cloudflare Tunnel tersimpan di `~/.cloudflared/casemix-auditor.log`.

Catatan keamanan: tanpa Cloudflare Access, domain publik dapat dibuka siapa pun yang mengetahui URL. Untuk data pasien/berkas klaim nyata, aktifkan Cloudflare Zero Trust Access atau batasi akses jaringan sebelum dipakai operasional.

## 4. Input PDF Untuk Review Jumlah Berkas

Review jumlah berkas dapat memakai salah satu dari dua sumber data PDF.

### Opsi A: `list_berkas_klaim.txt`

Di komputer Windows yang menyimpan folder klaim, buka Command Prompt pada folder utama klaim atau gunakan path lengkap, lalu jalankan:

```bat
dir /s /b > list_berkas_klaim.txt
```

Upload file `list_berkas_klaim.txt` ke aplikasi. File ini boleh berisi folder dan file lain; aplikasi hanya memakai baris yang berakhiran `.pdf`.

Gunakan opsi ini jika daftar file dibuat dari komputer lain atau user lebih mudah mengirim file TXT.

### Opsi B: Folder Berkas Lokal

Jika aplikasi berjalan di komputer/server yang bisa mengakses folder klaim langsung, pilih `Folder Berkas Lokal`, lalu isi path folder utama berkas klaim.

Aplikasi akan mencari semua file `.pdf` di dalam folder tersebut secara rekursif sampai subfolder terdalam, lalu mencocokkan nomor SEP dari nama/path PDF dengan Excel daftar klaim.

Jika path di list berasal dari komputer Windows lain dan tidak bisa diakses dari komputer yang menjalankan aplikasi, gunakan `Folder Berkas Lokal` pada komputer/server yang memiliki akses ke folder PDF tersebut.

## 5. Penjelasan Status

- `Lengkap`: file PDF ada, folder tanggal sesuai, tidak duplikat, dan komponen wajib terdeteksi.
- `Kurang PDF`: SEP di Excel belum memiliki PDF.
- `Kurang Komponen`: PDF ada, tetapi salah satu komponen wajib belum terdeteksi.
- `Salah Folder`: folder tanggal tepat sebelum nama file tidak sama dengan day dari Tanggal Pulang.
- `Duplikat`: ditemukan lebih dari satu PDF untuk nomor SEP yang sama.
- `Perlu Review Manual`: SEP kosong/tidak valid, folder tanggal tidak terbaca, PDF rusak, PDF tidak bisa diakses, atau teks digital PDF terlalu sedikit.

Pada tab `Review Jumlah Berkas`, status `Lengkap` berarti jumlah/path PDF sudah sesuai. Pada tab `Review Isi Berkas`, status `Lengkap` berarti komponen wajib di dalam PDF terdeteksi lengkap.

Komponen PDF yang dicek tanpa OCR:

- SEP
- LIP / Berkas Klaim Individual Pasien
- Rincian Tagihan
- Hasil Scan

Komponen PDF yang dicek dengan OCR:

- SEP
- LIP / Berkas Klaim Individual Pasien
- Rincian Tagihan
- Resume Medis
- Triage
- Surat Perintah Rawat Inap
- Hasil Pemeriksaan
- Pemeriksaan Radiologi

## 6. Keterbatasan

- Deteksi SEP, LIP, dan Rincian Tagihan berbasis teks digital dan keyword.
- Aplikasi tidak membaca teks di dalam gambar scan karena OCR dinonaktifkan.
- Hasil Scan hanya memastikan ada gambar/halaman scan di PDF, bukan memvalidasi isi klinis hasil scan.
- Aplikasi tidak memvalidasi tanda tangan, cap/stempel, validitas klinis resume, atau validitas medis hasil lab.
- Aplikasi tidak memperbaiki PDF rusak dan tidak membuka file yang path-nya tidak dapat diakses oleh komputer/server Streamlit.
- Folder tanggal diambil dari folder tepat sebelum nama file PDF. Jika struktur folder berbeda, status folder bisa menjadi `Tanggal Folder Tidak Terdeteksi`.
