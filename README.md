# EWS Yayasan & Perguruan Tinggi (prototipe)

## Menjalankan
```bash
pip install -r requirements.txt
streamlit run app.py
```
Pertama kali dijalankan, database `ews.db` (SQLite) dibuat otomatis dari `data/Contoh_Data_50_Yayasan.xlsx`.
Untuk mulai ulang dari data contoh: hapus `ews.db`.

## Cara memperbarui data
- **Kelola Data**: edit sel, tambah baris (ID otomatis jika dikosongkan), hapus baris. Ada validasi relasi, tanggal, dan kolom wajib.
- **Unggah Excel**: tambah/perbarui massal dengan format sheet yang sama. Tidak menghapus data.
- Setiap perubahan dicatat di **Log** (siapa, kapan, nilai lama/baru), dan perubahan warna status dicatat di **Riwayat Status**.

## Struktur
- `rules.py` mesin aturan (merah/kuning/hijau, status terburuk menang)
- `rules_config.json` aturan aktif dan parameter (bisa diubah dari menu Aturan)
- `db.py` penyimpanan, validasi, audit; `schema.py` definisi tabel dan pilihan isian
- `app.py` dashboard

## Catatan penting
- Aturan adalah usulan awal dari kolom data; wajib divalidasi ahli hukum.
- Belum ada autentikasi. Tambahkan login/peran (mis. streamlit-authenticator atau SSO) sebelum dipakai bersama.
- Untuk produksi, ganti SQLite dengan PostgreSQL (cukup ubah `db.py`).
