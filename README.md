# Casemix File Auditor

Aplikasi web lokal untuk membantu tim casemix rumah sakit mereview berkas klaim JKN sebelum diajukan. Aplikasi memisahkan tiga proses kerja: analisis TXT e-Klaim, review kelengkapan jumlah berkas, dan review kelengkapan isi berkas.

Data diproses lokal di komputer user. Data klaim pasien tidak dikirim ke cloud. Aplikasi hanya memeriksa metadata versi terbaru dari GitHub saat fitur cek pembaruan dijalankan.

**Panduan instalasi lengkap untuk user:** [docs/INSTALASI.md](docs/INSTALASI.md)

## Instalasi Cepat (Windows)

Prasyarat: Python 3.11/3.12, Git for Windows.

```bat
cd /d D:\Casemix
git clone https://github.com/rutofui/casemix-file-auditor.git
cd casemix-file-auditor
install.bat
run_app.bat
```

Buka `http://localhost:8501`. Pembaruan aplikasi: gunakan tombol **Update** di dalam app atau jalankan `update.bat`.

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

**Metode utama:** clone repository Git lalu jalankan `install.bat` (lihat [docs/INSTALASI.md](docs/INSTALASI.md)).

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

### 1.0. Instalasi Opsional: Mode OCR

Mode OCR membutuhkan dependency tambahan (PaddleOCR, ukuran download ~300 MB+). Install **hanya jika** fitur OCR akan digunakan:

```bash
pip install -r requirements-ocr.txt
```

Di Windows:

```bat
pip install --no-cache-dir -r requirements-ocr.txt
```

Tanpa `requirements-ocr.txt`, semua fitur lain (analisis TXT, review jumlah berkas, review isi tanpa OCR) tetap berjalan normal.

## 1.1. Menjaga Folder Project Tetap Ringan

Folder `.venv` berisi dependency Python dan ukurannya jauh lebih besar daripada kode aplikasi. Folder ini boleh dihapus dan dibuat ulang kapan pun dengan `install.bat`.

Untuk pembaruan rutin, gunakan `update.bat` atau tombol **Update** di aplikasi (bukan copy folder manual).

File/folder seperti `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, log, dan hasil export Excel tidak perlu dibagikan ke user lain.

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

### Analisis TXT e-Klaim

Kelompok rawat inap/rawat jalan ditentukan oleh PTD dalam data, bukan kotak upload. Struktur kolom yang rusak ditolak dengan sumber dan nomor baris. SEP tidak valid, PTD di luar 1/2, dan seluruh baris dengan SEP yang saling konflik masuk karantina. Salinan klaim yang benar-benar identik dihitung sekali; rincian duplikat tetap tersedia. Kualitas data memeriksa seluruh input, sedangkan KPI memakai klaim di luar karantina.

Tarif RS, INA-CBG (`TOTAL_TARIF`), dan iDRG (`C2.idrg.total_tarif`) ditampilkan berdampingan. Setiap total dilengkapi jumlah klaim dan cakupan; nilai tidak lengkap adalah subtotal parsial. Selisih dihitung dari pasangan tarif valid. Persentase RS terhadap grouper memakai total Tarif RS pasangan tersebut; perubahan iDRG terhadap INA-CBG memakai total INA-CBG pasangan tersebut. Penyebut nol tidak menghasilkan persentase. Selisih tarif bukan biaya aktual, laba/rugi, atau bukti pembayaran.

CMI iDRG memakai rata-rata `cost_weight` valid, dengan penyebut, cakupan, dan versi bobot. `total_cost_weight` ditampilkan terpisah. Tanpa bobot valid atau bila versi berbeda, CMI gabungan tidak tersedia; profil per versi tetap ditampilkan. CMI INA-CBG memerlukan referensi bobot INA-CBG tersendiri.

Hasil tambahan mencakup aktivitas DPJP, pasien unik, ALOS/median/P90 rawat inap, komponen tarif RS dan top-up INA-CBG, profil kelompok kasus/kelas rawat, ICU/ventilator, kunjungan berulang rawat jalan, aktivitas harian/bulanan, serta kode status pulang. Perubahan bulanan hanya dihitung untuk bulan yang berurutan dalam file; cakupan seluruh pelayanan RS tidak diasumsikan. Jumlah pasien unik antar-DPJP tidak dapat langsung dijumlahkan.

Validasi meliputi identitas kosong, domain angka, tanggal/LOS, ICU, JSON C2, kode berulang, dan rekonsiliasi komponen tarif. LOS tidak dikoreksi otomatis. Aturan severity/LOS merupakan penapisan untuk telaah petugas, bukan kesimpulan kesalahan klaim. Produktivitas per jam/FTE, BOR/BTO/TOI, indeks efisiensi LOS, readmission terverifikasi, dan margin biaya memerlukan data tambahan yang dijelaskan dalam metodologi.

Excel memuat seluruh tabel beserta sumber, waktu proses, periode, versi, definisi, dan cakupan. Tarif dan persentase tetap numerik; teks dari input tidak dieksekusi sebagai formula Excel. Temuan kualitas, karantina, dan kedua basis tarif ikut tab tindak lanjut.

### 1. Review Jumlah Berkas

Secara umum proses ini mencocokkan data klaim dengan daftar/path PDF. Untuk acuan Excel, aplikasi tidak membaca isi PDF.

Jika `Sumber Acuan Klaim` memakai `TXT E-Klaim`, aplikasi juga membaca teks digital halaman LIP pada PDF yang cocok untuk memeriksa kecocokan kelas perawatan, tanggal masuk, dan tanggal keluar.

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
- Khusus acuan `TXT E-Klaim`: kelas perawatan, tanggal masuk, dan tanggal keluar pada LIP sesuai dengan TXT E-Klaim.

Output export: `hasil_review_jumlah_berkas.xlsx`.

Kolom `Temuan` dan filter temuan mencakup seluruh masalah per SEP. Duplikat atau salah folder tidak menghentikan pemeriksaan LIP/ICD yang tersedia. `Status Akhir` menunjukkan masalah dengan prioritas utama. Halaman LIP dicari di seluruh PDF; halaman lain tidak dipakai sebagai pengganti LIP.

### 2. Review Isi Berkas

Proses ini membaca teks digital PDF dan mendeteksi halaman/gambar hasil scan. OCR dapat diaktifkan untuk membaca judul pada halaman scan.

Review isi berkas memproses beberapa PDF sekaligus secara otomatis dengan batas worker konservatif (maks. 4 worker tanpa OCR, maks. 2 worker dengan OCR) agar lebih cepat pada batch besar tanpa membebani komputer secara berlebihan.

Mode scan isi PDF:

- `Tanpa OCR`: membaca teks digital dan mendeteksi gambar. Judul dokumen dapat dikenali bila berupa teks digital.
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

Rincian Tagihan membutuhkan penanda khusus rincian biaya/tagihan atau judul BILLING. Kata INA-CBG, total tarif, barang, jasa, atau fasilitas saja tidak cukup.
Hasil Scan dideteksi dari keberadaan gambar/halaman scan di PDF, bukan dari pembacaan isi gambar.

Review isi berkas tidak membutuhkan Excel atau `list_berkas_klaim.txt`. Hasilnya satu baris per PDF yang diperiksa.

Output export: `hasil_review_isi_berkas.xlsx`.

### Hasil dan tindak lanjut

Hasil mencantumkan sumber dan waktu proses. Perubahan input, mode, atau checklist membuat hasil sebelumnya kedaluwarsa; jalankan ulang sebelum mengekspor. Jika isi folder di disk berubah tanpa perubahan path, jalankan ulang pemeriksaan secara manual.

Tab `Tindak lanjut` menggabungkan temuan terbaru per SEP dari ketiga fungsi. Isi petugas, catatan koreksi, dan status penyelesaian, lalu unduh Excel sebelum menutup aplikasi. Catatan bertahan selama sesi; temuan yang berubah perlu ditinjau ulang. Status petugas tidak mengubah hasil pemeriksaan otomatis.

## Akses Domain Cloudflare

> **⚠️ PERINGATAN KEAMANAN — WAJIB DIBACA SEBELUM DEPLOYMENT PUBLIK**
>
> Tanpa Cloudflare Access, domain publik (`https://casemix.ahmadluthfi.online`) dapat diakses siapa pun yang mengetahui URL — termasuk data pasien berupa nama, No RM, dan diagnosis klinis.
>
> **Sebelum menggunakan mode publik dengan data klaim nyata, wajib salah satu dari:**
> 1. Aktifkan **Cloudflare Zero Trust Access** (autentikasi per user/email), atau
> 2. Batasi akses hanya dari jaringan internal (VPN / IP allowlist), atau
> 3. Jalankan aplikasi hanya secara lokal (`http://localhost:8501`) tanpa tunnel.

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
- `Data LIP Tidak Sesuai`: acuan TXT E-Klaim berbeda dengan kelas perawatan, tanggal masuk, atau tanggal keluar yang terbaca di halaman LIP.

Pada tab `Review Jumlah Berkas`, status `Lengkap` berarti jumlah/path PDF sudah sesuai. Pada tab `Review Isi Berkas`, status `Lengkap` berarti komponen wajib di dalam PDF terdeteksi lengkap.

Checklist berlaku terpisah dari pilihan OCR:

- Rawat inap: SEP, LIP, rincian tagihan, resume medis, dan SPRI.
- Rawat jalan: SEP, LIP, dan rincian tagihan.
- Petugas dapat mengubah dokumen tambahan sesuai SOP/kasus; dokumen yang tidak diwajibkan bertanda `Tidak berlaku`. Pisahkan batch bila persyaratan antar-kasus berbeda.
- `Bukti Halaman` memuat nomor halaman mulai dari 1. Perbedaan SEP nama file dan isi, beberapa SEP dalam satu PDF, atau kegagalan pembacaan memerlukan review manual.

## 6. Keterbatasan

- Deteksi SEP, LIP, dan Rincian Tagihan berbasis teks digital dan keyword.
- Tanpa OCR, aplikasi tidak membaca teks di dalam gambar scan. OCR hanya membaca bagian atas halaman sehingga judul di bagian lain dapat terlewat.
- Hasil Scan hanya memastikan ada gambar/halaman scan di PDF, bukan memvalidasi isi klinis hasil scan.
- Aplikasi tidak memvalidasi tanda tangan, cap/stempel, validitas klinis resume, atau validitas medis hasil lab.
- Aplikasi tidak memperbaiki PDF rusak dan tidak membuka file yang path-nya tidak dapat diakses oleh komputer/server Streamlit.
- Folder tanggal diambil dari folder tepat sebelum nama file PDF. Jika struktur folder berbeda, status folder bisa menjadi `Tanggal Folder Tidak Terdeteksi`.
- Pemeriksaan kelas/tanggal LIP pada `Review Jumlah Berkas` memakai teks digital tanpa OCR. Jika LIP berupa scan gambar tanpa teks digital, hasilnya perlu review manual.
