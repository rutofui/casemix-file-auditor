# Audit fungsi analisis TXT e-Klaim

Tanggal audit: 24 September 2026. Ruang lingkup: parser TXT, perhitungan, tampilan, ekspor Excel, dan kedua file contoh. Sesuai pilihan pengguna, INA-CBG dan iDRG dibandingkan berdampingan. Bagian 1-6 merekam audit sebelum perbaikan; status penerapan ada di bagian 7. Referensi nomor baris pada temuan awal merujuk kode sebelum perubahan.

Hasil dasar pada contoh berhasil direkonsiliasi. Namun, perlindungan terhadap duplikasi, kerusakan struktur, dan bobot yang tidak tersedia belum cukup kuat. Selisih tarif belum dapat dipakai sebagai ukuran laba, biaya aktual, atau efisiensi klinis.

## 1. Temuan akurasi, menurut prioritas

### P1 - SEP duplikat dapat menggandakan hasil

Lokasi: [parser_eklaim_txt.py:178](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/parser_eklaim_txt.py:178>), [eklaim_analyzer.py:54](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/eklaim_analyzer.py:54>).

Pemeriksaan hanya mencari irisan SEP antara dua file. SEP berulang dalam satu file tidak menimbulkan peringatan duplikasi. Duplikat antarfile pun tetap masuk agregasi setelah peringatan. Reproduksi: dua baris identik dengan satu SEP menghasilkan dua klaim dan dua kali tarif; kualitas data hanya memperlihatkan satu SEP unik. Kedua file contoh tidak memiliki duplikasi.

Perbaikan: tampilkan jumlah baris, SEP unik, duplikat identik, dan duplikat dengan isi berbeda. Karantina konflik dari KPI final sampai aturan pemilihan klaim disepakati. Jangan menghapus baris konflik secara otomatis atau menganggap seluruh baris sebagai episode unik.

### P2 - JSON C2 yang sah dapat kehilangan data iDRG

Lokasi: [parser_eklaim_txt.py:194](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/parser_eklaim_txt.py:194>), [parser_eklaim_txt.py:228](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/parser_eklaim_txt.py:228>).

Pemindai menghitung kurung kurawal tanpa memperhatikan string JSON. Teks sah seperti `"drg_description":"brace } text"` membuat ekstraksi gagal. Selain itu, jika `cost_weight` hilang, seluruh objek dilewati, termasuk `total_tarif` yang sebenarnya tersedia. Kedua masalah direproduksi dengan data sintetis; tidak ditemukan pada contoh.

Perbaikan: gunakan decoder JSON standar untuk objek yang disisipkan di C2; ekstrak setiap field secara mandiri. Bedakan C2 kosong, JSON rusak, objek iDRG tidak ditemukan, dan field numerik tidak valid.

### P2 - Jumlah kolom per baris belum divalidasi

Lokasi: [parser_eklaim_txt.py:60](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/parser_eklaim_txt.py:60>).

Pada reproduksi header 15 kolom dengan baris 16 field, pembaca menerima field pertama sebagai indeks dan menggeser seluruh nilai. Peringatan SEP/bobot muncul kemudian, tetapi akar masalah struktur tidak disebutkan. Baris 14 field diterima dengan field terakhir kosong. Kedua contoh asli memiliki 78 kolom dan seluruh baris konsisten.

Perbaikan: validasi jumlah field berdasarkan header sebelum normalisasi; laporkan sumber dan nomor baris. Jangan memperbaiki pergeseran secara diam-diam. Variasi jumlah kolom antarversi harus mengikuti header masing-masing, bukan angka 78 yang dipatok permanen.

### P2 - CMI tidak tersedia ditampilkan sebagai nol

Lokasi: [eklaim_analyzer.py:180](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/eklaim_analyzer.py:180>), [txt_analysis.py:211](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/ui/txt_analysis.py:211>).

Jika seluruh bobot kosong, hasil menjadi `CMI = 0` dan `Jumlah Klaim = 0`, walaupun klaim ada. Jika sebagian bobot kosong, kolom `Jumlah Klaim` hanya menghitung klaim berbobot. Rata-rata bobot tersedia secara aritmetis benar, tetapi penyebut dan keterwakilannya perlu dijelaskan.

Perbaikan: tampilkan total klaim, klaim dengan bobot valid, cakupan, dan CMI pada subset tersebut. Tanpa bobot valid, tampilkan "tidak tersedia". Jangan mengganti bobot hilang menjadi nol. Cakupan kedua contoh adalah 100%.

### P2 - Kualitas data belum memeriksa konsistensi identitas, tanggal, dan domain angka

Lokasi: [eklaim_analyzer.py:113](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/eklaim_analyzer.py:113>), [parser_eklaim_txt.py:73](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/parser_eklaim_txt.py:73>).

Contoh RANAP memiliki satu MRN kosong. Pada 620 klaim, LOS sama dengan selisih tanggal pulang-masuk ditambah satu; dua klaim memakai selisih tanggal tanpa tambahan satu. Ini perlu telaah terhadap definisi LOS ekspor, belum membuktikan kesalahan. Pemeriksaan saat ini tidak mendeteksi keduanya.

Tarif dan bobot negatif diterima sebagai angka valid. `ICU_INDIKATOR` belum dibatasi pada domain yang diizinkan. `VENT_HOUR` dan `TARIF_INACBG` sudah diparse tetapi tidak masuk tabel kualitas angka. Validasi tanggal, urutan masuk-pulang, identitas pasien, DPJP kosong, ICU_LOS terhadap LOS, dan rekonsiliasi rincian tarif belum tersedia.

Perbaikan: terapkan aturan per field dan versi skema. Nilai negatif pada kolom klaim memerlukan penjelasan/koreksi; jika skema mengizinkan penyesuaian negatif, pisahkan secara eksplisit. Simpan nilai asli dan alasan pengecualian.

### P3 - Top ICD mencampur peran kode dan memakai label deskripsi yang keliru

Lokasi: [eklaim_analyzer.py:339](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/eklaim_analyzer.py:339>).

Semua kode DIAGLIST dihitung bersama tanpa membedakan diagnosis utama dan sekunder. Kolom `Deskripsi` hanya berisi `ICD-10` atau `ICD-9-CM`. Kode berulang dalam satu klaim juga dihitung berulang; contoh tidak memiliki pengulangan tersebut.

Perbaikan: pisahkan frekuensi kemunculan dari jumlah klaim yang memuat kode. Untuk tabel diagnosis utama, gunakan posisi kode hanya setelah aturan urutan DIAGLIST dikonfirmasi. Ganti label menjadi "Jenis kode" atau isi deskripsi dari master sesuai versi. Tindakan kosong juga perlu konteks pelayanan, bukan otomatis dianggap kesalahan coding.

## 2. Rekonsiliasi contoh dan dua basis tarif

Angka rupiah di tabel merupakan nilai dalam file. Pada contoh, `TOTAL_TARIF` merepresentasikan total pada bagian INA-CBG dan direkonsiliasi dengan `TARIF_INACBG`; iDRG berasal dari `C2.idrg.total_tarif`. Keberadaan kedua nilai tidak membuktikan tarif mana yang dibayar atau disetujui penjamin.

| Indikator | RANAP | RAJAL |
| --- | ---: | ---: |
| Baris klaim / SEP unik valid | 622 / 622 | 864 / 864 |
| Identitas pasien unik menurut NOKARTU | 622 | 740 |
| Nama DPJP setelah normalisasi | 8 | 15 |
| Total Tarif RS | Rp2.730.803.581 | Rp181.912.241 |
| Total tarif INA-CBG (`TOTAL_TARIF`) | Rp1.758.846.300 | Rp205.974.800 |
| Total tarif iDRG (`C2.idrg.total_tarif`) | Rp2.514.000.970 | Rp253.496.922 |
| Selisih RS - INA-CBG | Rp971.957.281 | -Rp24.062.559 |
| Selisih RS - iDRG | Rp216.802.611 | -Rp71.584.681 |
| Selisih RS - INA-CBG, dibagi Tarif RS | 35,59% | -13,23% |
| Selisih RS - iDRG, dibagi Tarif RS | 7,94% | -39,35% |
| Rata-rata `cost_weight` iDRG | 0,4948 | 0,6358 |
| Rata-rata `total_cost_weight` iDRG | 0,5026 | 0,6358 |
| Cakupan kedua field bobot | 100% | 100% |

Total gabungan: 1.486 klaim; Tarif RS Rp2.912.715.822; INA-CBG Rp1.964.821.100; iDRG Rp2.767.497.892. Selisih RS-INA-CBG Rp947.894.722, sedangkan RS-iDRG Rp145.217.930. Perbedaan kedua basis tarif Rp802.676.792.

Kode saat ini secara konsisten menggunakan `TOTAL_TARIF`, sesuai README dan tes. Ini bukan salah penjumlahan. Celahnya: tarif iDRG sudah diekstrak tetapi belum ditampilkan atau dipakai sebagai pembanding terpisah. Rujukan: [parser_eklaim_txt.py:83](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/parser_eklaim_txt.py:83>), [eklaim_analyzer.py:153](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/eklaim_analyzer.py:153>).

Perubahan basis turut mengubah daftar telaah:

| Penapisan | RANAP INA-CBG | RANAP iDRG | RAJAL INA-CBG | RAJAL iDRG |
| --- | ---: | ---: | ---: | ---: |
| Tarif grouper lebih besar dari Tarif RS | 23 | 220 | 642 | 740 |
| (Tarif RS - grouper) / Tarif RS > 30% | 434 | 94 | 83 | 52 |

Perbandingan wajib menggunakan pasangan klaim yang sama dengan kedua tarif valid. Jika salah satu basis tidak tersedia, jumlah klaim yang dikecualikan harus disebutkan. Persentase agregat dihitung dari total berpasangan, bukan rata-rata persentase per klaim. Nol pada penyebut menghasilkan "tidak tersedia".

Pada 111 klaim RANAP, `cost_weight` berbeda dari `total_cost_weight`. Jumlah masing-masing 307,76 dan 312,61; RAJAL sama-sama 549,32. Rumus saat ini benar untuk rata-rata `cost_weight`. Belum ada dasar terverifikasi untuk menggantinya atau menyebut rata-rata `total_cost_weight` sebagai CMI resmi. CMI INA-CBG memerlukan bobot referensi INA-CBG tersendiri; bobot iDRG tidak boleh dipakai sebagai penggantinya. CMI RI dan RJ juga tidak boleh dibandingkan sebagai tingkat kinerja tanpa kesetaraan skala bobot.

## 3. Analisis tambahan yang layak

| Prioritas | Analisis | Isi hasil dan batas penggunaan |
| --- | --- | --- |
| Utama | Rekonsiliasi kualitas data | Baris masuk, episode unik, duplikat, klaim valid/karantina, cakupan setiap indikator, periode, versi grouper, alasan pengecualian. |
| Utama | Tarif INA-CBG dan iDRG berdampingan | Tarif RS, dua tarif grouper, selisih terhadap RS, perubahan iDRG-INA-CBG; agregat dan per DPJP, kelompok kasus, kelas rawat. Sertakan komponen top-up sesuai skema. |
| Utama | Profil aktivitas DPJP | Episode unik, pasien unik, pangsa volume, total dan rata-rata tarif per episode untuk kedua basis, total bobot, CMI dan cakupan, ALOS/median RI, proporsi ICU. Bandingkan layanan dan kelompok kasus yang setara. |
| Tinggi | Lama rawat RANAP | ALOS = jumlah LOS valid / jumlah episode RI dengan LOS valid; median dan persentil ke-90. Pisahkan per diagnosis/kelompok kasus, severity INA-CBG, DPJP, kelas, serta status pulang. |
| Tinggi | Komposisi tarif RS | Kontribusi obat, laboratorium, radiologi, kamar, tindakan; nilai per episode dan per hari. Rekonsiliasi jumlah komponen terhadap Tarif RS. Sebut komponen tarif, bukan biaya aktual. |
| Tinggi | Indikator casemix | Distribusi kelompok INA-CBG dan iDRG, proporsi severity INA-CBG I/II/III, total bobot, CMI iDRG per kelompok/DPJP. Cantumkan versi dan cakupan. |
| Menengah | Pola RAJAL | Kunjungan per pasien, pasien dengan kunjungan berulang, distribusi hari layanan dan perubahan antarperiode. Kunjungan berulang bukan otomatis readmission atau pelayanan tidak perlu. |
| Menengah | Pemanfaatan intensif dan hasil pulang | Persentase episode ICU, total/median ICU_LOS, ventilator, distribusi DISCHARGE_STATUS. Konfirmasi arti kode dan satuan. Gunakan sebagai deskripsi, bukan penilaian mutu tanpa penyesuaian risiko. |

Contoh tambahan yang sudah dapat dihitung dari dua TXT:

- ALOS berdasarkan field LOS RANAP: 2.803 / 622 = 4,51 hari; median 4 hari. Dua perbedaan terhadap tanggal tetap harus diberi catatan.
- ICU RANAP: 17/622 = 2,73%, dengan total ICU_LOS 40. Seluruh komponen `RAWAT_INTENSIF` bernilai nol; perlu rekonsiliasi pencatatan tarif, bukan langsung kesimpulan tagihan hilang.
- RAJAL: 864 kunjungan untuk 740 identitas pasien unik; 99 pasien memiliki lebih dari satu kunjungan dalam file. Rata-rata 1,17 kunjungan per pasien.
- Kamar/akomodasi menyumbang Rp1.342.883.361 atau 49,18% Tarif RS RANAP. Berguna sebagai prioritas telaah tarif; tidak membuktikan pemborosan.
- Jumlah 18 komponen tarif RS cocok dengan `TARIF_RS` pada seluruh 1.486 baris.

Rekap DPJP saat ini baru jumlah klaim dan tarif ([eklaim_analyzer.py:293](</Users/ahmadluthfi/Documents/Casemix File Auditor/src/eklaim_analyzer.py:293>)). Sebut "aktivitas DPJP" sampai tersedia penyebut tenaga/waktu. Nama yang berbeda format perlu master DPJP; penggabungan nama secara samar berisiko menyatukan dokter berbeda.

## 4. Indeks yang memerlukan data tambahan

| Indikator | Data tambahan / syarat |
| --- | --- |
| Produktivitas DPJP per jam/hari/FTE | Jam atau sesi layanan, jadwal kerja, FTE dan penugasan. Hari dengan klaim hanya hari aktivitas teramati, bukan seluruh hari kerja. Satu DPJP pada klaim juga belum mencakup kerja seluruh tim. |
| BOR, BTO, TOI | Kapasitas tempat tidur tersedia menurut waktu dan sensus lengkap seluruh pasien. Jumlah LOS klaim keluar tidak sama dengan hari perawatan pada periode kalender. |
| Indeks efisiensi LOS | LOS harapan per kelompok kasus dan versi, populasi pembanding yang sesuai, penyesuaian risiko. Rumus operasional: total LOS aktual / total LOS harapan pada episode yang sama. Jangan memakai batas lima hari sebagai standar efisiensi universal. |
| Margin atau efisiensi biaya | Biaya aktual dari akuntansi/costing dan pendapatan yang diakui/dibayar. Selisih Tarif RS-grouper hanya selisih tarif. |
| Readmission 7/30 hari | Identitas stabil, episode sebelum dan sesudah periode, cakupan layanan, pemisahan terencana/tidak terencana dan transfer. Batch satu bulan belum cukup untuk menyimpulkan angka resmi. |
| Mortalitas dan indikator mutu | Pemetaan DISCHARGE_STATUS terverifikasi, populasi lengkap dan penyesuaian risiko. Indikator berbasis ambang 48 jam memerlukan ketelitian waktu yang sesuai; tanggal saja tidak cukup. |

Batas severity/LOS yang sudah ada memang diberi keterangan sebagai penapisan, bukan kesimpulan kesalahan. Pertahankan batas interpretasi tersebut. Tujuh klaim memenuhi severity > 1 dan LOS < 5; 49 klaim memenuhi severity I dan LOS > 5. Keduanya tidak membuktikan upcoding atau inefisiensi.

## 5. Ketentuan hasil yang akurat

1. Tentukan populasi dan periode secara eksplisit. Tanggal pulang contoh berada pada Agustus 2026, tetapi tanggal masuk RANAP mulai 27 Juli. Dua file ini belum membuktikan cakupan seluruh pelayanan rumah sakit.
2. Setiap KPI menyertakan unit, sumber field, rumus, penyebut, jumlah yang dikecualikan, dan cakupan. Pisahkan RI/RJ, INA-CBG/iDRG, serta versi grouper.
3. Pisahkan nol, kosong, tidak valid, dan tidak berlaku. Total tarif parsial harus bertuliskan "subtotal parsial" dengan cakupannya; kode sudah mengosongkan selisih jika tarif tidak lengkap, tetapi label total masih umum.
4. Tampilkan daftar telaah beserta sumber/nomor baris dan alasan. Jumlah antarjenis temuan tidak boleh dijumlahkan sebagai jumlah pasien karena satu klaim bisa memiliki banyak temuan.
5. Samakan basis data, definisi, filter, dan pembulatan pada layar serta Excel. Simpan presisi perhitungan; bulatkan saat penyajian. Ekspor perlu menyertakan sumber file, waktu proses, periode, versi, rumus, dan keterbatasan.
6. Urutan pengembangan: perbaikan integritas data; dua basis tarif dan kejelasan CMI; profil DPJP/LOS/komponen tarif; indeks dengan pembanding eksternal setelah datanya tersedia.

## 6. Verifikasi dan batas audit

- Pemeriksaan langsung: 622 baris RANAP, 864 baris RAJAL, masing-masing 78 kolom; seluruh SEP/PTD valid dan tidak ada duplikasi pada kedua file.
- Perhitungan pembanding memakai pembaca CSV, Decimal, dan decoder JSON standar; agregat tarif, bobot, proporsi, serta hitungan penapisan diperiksa terhadap keluaran aplikasi.
- 22 tes terkait parser/analisis TXT dan format/ekspor lulus: `tests/test_eklaim_txt.py` dan `tests/test_eklaim_formatting.py`.
- Ekspor kedua contoh diuji dalam memori: 18 sheet, ringkasan cocok, agregat DPJP cocok. Tidak dibuat salinan ekspor berisi identitas pasien.
- Uji sintetis tambahan mereproduksi duplikat satu file, struktur baris terlalu panjang/pendek, kurung kurawal dalam string C2, bobot hilang, serta domain negatif. Celah ini belum dicakup memadai oleh tes yang lulus.
- Tes berjalan pada Python 3.14 lokal, bukan seluruh matriks Python 3.11/3.12 proyek. Tampilan dibaca dari kode; browser tidak diuji. Tidak dilakukan verifikasi regulasi, kebenaran klinis, status bayar, atau keseluruhan klaim RS.
- Laporan hanya memuat agregat. Isi file diperlakukan sebagai data, bukan instruksi. Tidak ada kode aplikasi atau data sumber yang diubah.

Identitas sumber untuk pengulangan audit (SHA-256):

```text
TXT RANAP AGUSTUS UNC DETAIL.TXT
c116d787e87148aea761fb422eb7202174a92c1b946469209882f5940385f0a9

TXT RAJAL AGUSTUS UNC DETAIL.TXT
cd03ed4aa9be5225824507515ceaeef09c47cb8b512325d0e2f3f75cd88761b3
```

## 7. Perbaikan diterapkan dan diverifikasi

| Rencana | Hasil penerapan | Bukti pemeriksaan |
| --- | --- | --- |
| Integritas struktur TXT dan C2 | Validasi jumlah field/header, sumber dan baris fisik, decoder JSON standar, ekstraksi setiap field iDRG mandiri | Tes struktur terlalu panjang/pendek, header duplikat, BOM, record multiline, unggahan dibaca ulang, string JSON berkurung kurawal, tarif tanpa bobot |
| Duplikasi dan karantina | Salinan identik dihitung sekali; semua baris SEP konflik, SEP tidak valid, PTD tidak valid dikecualikan dari KPI | Tes duplikat lintas file, konflik dalam file, semua klaim dikarantina; rekonsiliasi baris masuk = dianalisis + dikecualikan |
| Domain dan konsistensi | Angka negatif/domain ICU tidak valid dikecualikan per field; identitas, tanggal, LOS, ICU, kode berulang, komponen tarif ditelaah | Kedua contoh menghasilkan 20 temuan: 1 MRN kosong, 2 perbedaan LOS/tanggal, 17 tarif intensif nol pada episode ICU |
| Dua basis tarif | INA-CBG dan iDRG berdampingan dengan total, rata-rata, cakupan, pasangan valid, selisih dan persentase | Hitungan Decimal langsung dari TXT cocok; selisih RS-INA-CBG Rp947.894.722 dan RS-iDRG Rp145.217.930 |
| CMI dan versi | Total klaim/penyebut/cakupan eksplisit, kosong tidak menjadi nol, bobot dasar dan total terpisah, versi berbeda tidak digabung sebagai CMI | Tes bobot kosong/negatif dan versi campuran; sampel CMI RI 0,4948, RJ 0,6358 |
| DPJP, LOS, kelompok kasus/kelas | Volume, pasien unik, kedua tarif, CMI, ALOS/median/P90, ICU; profil INA-CBG, iDRG, severity dan kelas | Seluruh 23 baris rekap DPJP direkonsiliasi terhadap data mentah; jumlah kelompok cocok dengan populasi masing-masing |
| Komponen dan pola layanan | 18 komponen RS, 7 komponen INA-CBG, kunjungan berulang, harian/bulanan, ICU/ventilator, kode status pulang | Seluruh 36 total komponen RS cocok; RAJAL 740 pasien unik dan 99 dengan kunjungan berulang; tes jeda bulan dan tanggal terbalik |
| Layar, Excel, tindak lanjut | Semua tabel, definisi, sumber, waktu, periode dan versi tersedia; temuan baru masuk tindak lanjut | 33 sheet Excel; tarif/persen numerik; teks input dipertahankan sebagai teks, bukan formula; tes hasil kedaluwarsa dan seluruh klaim dikarantina |
| Batas indikator | Produktivitas per jam/FTE, BOR/BTO/TOI, efisiensi biaya/LOS, readmission resmi, dan mutu tidak direkayasa dari data yang tidak tersedia | Kebutuhan data dan batas interpretasi ditampilkan pada metodologi di aplikasi dan Excel |

Verifikasi akhir: 148 tes proyek lulus pada lingkungan Python 3.14 dengan dependensi sesuai rentang proyek; kompilasi Python dan pemeriksaan whitespace lulus. Tabel metadata memakai teks untuk tampilan dan tetap mempertahankan tipe numerik pada Excel. Matriks CI Python 3.11/3.12 tetap didefinisikan dalam proyek dan tidak diklaim sudah dijalankan lokal.

Kedua file asli juga diunggah dan dianalisis melalui browser. Tampilan desktop dan lebar ponsel 390 piksel diperiksa. Aplikasi utama pada port 8501 berhasil menampilkan 1.486 klaim beserta kedua tarif dan CMI. Hash kedua file sumber tetap sama. Tidak ada identitas pasien dimasukkan ke laporan atau fixture pengujian.
