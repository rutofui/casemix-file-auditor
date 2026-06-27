# Panduan Instalasi Casemix File Auditor

Aplikasi ini diinstall di PC Windows masing-masing user dan diakses secara lokal di browser (`http://localhost:8501`). Data klaim diproses di komputer Anda; tidak dikirim ke cloud.

## A. Prasyarat

Sebelum instalasi, pastikan sudah terpasang:

| Software | Versi | Unduhan |
|----------|-------|---------|
| Windows | 10 atau 11 | - |
| Python | 3.11 atau 3.12 | https://www.python.org/downloads/ |
| Git for Windows | Terbaru | https://git-scm.com/download/win |

Saat instalasi Python, centang **"Add python.exe to PATH"**.

## B. Instalasi Pertama Kali

1. Buka **Command Prompt** (cmd).
2. Pindah ke folder kerja yang diinginkan, contoh:

```bat
cd /d D:\Casemix
```

3. Clone repository (repo publik, tidak perlu akun GitHub):

```bat
git clone https://github.com/rutofui/casemix-file-auditor.git
cd casemix-file-auditor
```

4. Jalankan installer:

```bat
install.bat
```

Proses ini membuat virtual environment (`.venv`) dan mengunduh dependency Python. Pertama kali bisa memakan waktu beberapa menit.

5. Setelah instalasi selesai, jalankan aplikasi:

```bat
run_app.bat
```

6. Buka browser ke:

```text
http://localhost:8501
```

## C. Memperbarui Aplikasi

### Cara 1 — Dari dalam aplikasi (disarankan)

1. Buka aplikasi dengan `run_app.bat`.
2. Di bagian atas halaman, periksa **Versi terpasang**.
3. Jika ada versi baru, tombol berubah menjadi **Update**.
4. Klik **Update**, tunggu proses selesai, lalu **tutup** jendela terminal/browser.
5. Jalankan ulang `run_app.bat`.

Tombol **Check for Updates** dapat digunakan kapan saja untuk memeriksa versi terbaru di GitHub.

### Cara 2 — Manual lewat Command Prompt

```bat
cd /d D:\Casemix\casemix-file-auditor
update.bat
```

Setelah selesai, jalankan ulang `run_app.bat`.

## D. Troubleshooting

### `git pull` gagal / konflik

Jangan mengubah file di dalam folder aplikasi. Jika terjadi konflik:

1. Backup folder kerja Anda (Excel/PDF export) di luar folder aplikasi.
2. Hapus folder `casemix-file-auditor`.
3. Clone ulang dari awal (langkah B.3–B.5).

### Python atau Git tidak dikenali

- Install ulang Python dengan opsi **Add to PATH**.
- Install Git for Windows, lalu buka Command Prompt baru.

### Port 8501 sudah dipakai

Tutup jendela `run_app.bat` / Streamlit yang masih berjalan, lalu jalankan ulang.

### Mode OCR lambat pertama kali

Normal. Model PaddleOCR diunduh saat pertama kali digunakan dan disimpan lokal.

### Tidak ada koneksi internet

Aplikasi tetap bisa dipakai untuk review berkas. Fitur cek/update versi membutuhkan internet.

## E. File Penting

| File | Fungsi |
|------|--------|
| `install.bat` | Instalasi pertama |
| `run_app.bat` | Menjalankan aplikasi |
| `update.bat` | Memperbarui kode & dependency |
| `clean.bat` | Membersihkan cache lokal |
| `BUILD_INFO.json` | Penanda versi terpasang (tanggal & jam) |
