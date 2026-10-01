"""Definisi tabel, kunci, relasi, dan pilihan isian."""
TABLES = {
    "yayasan": dict(label="Yayasan", pk="id_yayasan", prefix="Y", pad=3, dates=["tgl_sk_badan_hukum"], ints=[]),
    "pt": dict(label="Perguruan Tinggi", pk="kode_pt", prefix="P", pad=3, dates=["tgl_izin"],
               ints=["jumlah_mahasiswa_aktif", "jumlah_dosen_tetap"]),
    "riwayat_penyelenggara": dict(label="Riwayat Penyelenggara PT", pk="id_penyelenggara", prefix="H", pad=4,
                                  dates=["tgl_mulai", "tgl_akhir", "tgl_sk_alih_kelola"], ints=[]),
    "akta": dict(label="Akta Yayasan", pk="id_akta", prefix="A", pad=4,
                 dates=["tgl_akta", "tgl_berlaku", "tgl_sk_kemenkum"], ints=["no_akta"]),
    "organ_yayasan": dict(label="Organ Yayasan", pk="id_organ", prefix="O", pad=4, dates=["tgl_mulai", "tgl_akhir"], ints=[]),
    "pimpinan_pt": dict(label="Pimpinan PT", pk="id_pimpinan", prefix="K", pad=4,
                        dates=["tgl_mulai", "tgl_akhir", "tgl_sk_pengangkatan"], ints=[]),
    "aturan_statuta": dict(label="Statuta PT", pk="id_statuta", prefix="S", pad=4, dates=["tgl_berlaku", "tgl_berakhir"],
                           ints=["masa_jabatan_rektor_tahun", "maks_periode_rektor", "batas_usia_rektor"]),
    "riwayat_perubahan": dict(label="Riwayat Perubahan AD/Statuta", pk="id_perubahan", prefix="R", pad=4,
                              dates=["tgl_perubahan"], ints=[]),
}
ORDER = list(TABLES)  # urutan induk -> anak

# tabel -> {kolom: tabel_induk}
FKS = {
    "pt": {"id_yayasan": "yayasan"},
    "riwayat_penyelenggara": {"kode_pt": "pt", "id_yayasan": "yayasan"},
    "akta": {"id_yayasan": "yayasan"},
    "organ_yayasan": {"id_yayasan": "yayasan", "id_akta_sumber": "akta"},
    "pimpinan_pt": {"kode_pt": "pt", "id_yayasan": "yayasan"},
    "aturan_statuta": {"kode_pt": "pt"},
}
REQUIRED = {
    "yayasan": ["nama_yayasan"], "pt": ["nama_pt", "id_yayasan"],
    "riwayat_penyelenggara": ["kode_pt", "id_yayasan", "tgl_mulai"], "akta": ["id_yayasan", "tgl_akta"],
    "organ_yayasan": ["id_yayasan", "nama_lengkap", "jabatan_yayasan", "tgl_mulai"],
    "pimpinan_pt": ["kode_pt", "id_yayasan", "nama_lengkap", "jabatan_pt", "tgl_mulai"],
    "aturan_statuta": ["kode_pt", "tgl_berlaku"], "riwayat_perubahan": ["id_entitas", "tgl_perubahan"],
}
YA_TIDAK = ["Ya", "Tidak"]
ENUMS = {
    "status_yayasan": ["Aktif", "Bersengketa", "Tidak aktif", "Dibubarkan"],
    "status_pt": ["Aktif", "Dalam pembinaan", "Ditutup"],
    "akreditasi_pt": ["Unggul", "Baik Sekali", "Baik", "Kedaluwarsa", "Belum terakreditasi"],
    "jenis_pt": ["Universitas", "Institut", "Sekolah Tinggi", "Politeknik", "Akademi"],
    "jenis_perpindahan": ["Penyelenggara awal", "Alih kelola ke yayasan lain"],
    "jenis_perubahan": ["Pendirian", "Perubahan organ", "Perubahan kewenangan", "Perubahan lainnya"],
    "ubah_kewenangan_terhadap_pt": YA_TIDAK,
    "jabatan_yayasan": ["Pembina", "Ketua Pengurus", "Sekretaris", "Bendahara", "Pengawas"],
    "status_periode": ["Berjalan", "Selesai"],
    "jabatan_pt": ["Rektor", "Direktur", "Ketua"],
    "status_definitif": ["Definitif", "Plt", "Pj"],
    "alasan_berhenti": ["Habis masa jabatan", "Mengundurkan diri", "Diberhentikan", "Berhalangan tetap"],
    "ada_dok_penjaringan": YA_TIDAK, "ada_dok_pertimbangan_senat": YA_TIDAK,
    "ada_dok_pemberhentian": ["Ya", "Tidak", "Tidak diketahui"],
    "merangkap_organ_yayasan": ["Ya", "Tidak", "Tidak diketahui"],
    "pengangkat_rektor": ["Yayasan", "Yayasan setelah pertimbangan senat", "Senat", "Menteri"],
    "wajib_penjaringan": ["Ya", "Tidak diatur"], "wajib_pertimbangan_senat": ["Ya", "Tidak diatur"],
    "larangan_rangkap_organ_yayasan": ["Ya", "Tidak diatur"], "prosedur_pemberhentian_diatur": ["Ya", "Tidak diatur"],
    "wajib_pertimbangan_senat_berhenti": ["Ya", "Tidak diatur"], "hak_membela_diri": ["Ya", "Tidak diatur"],
    "ada_senat": ["Ya", "Tidak"], "ada_spi": ["Ya", "Tidak diatur"], "yayasan_berwenang_akademik": YA_TIDAK,
    "menyentuh_pasal_pimpinan": YA_TIDAK,
    "jenis_dokumen": ["Anggaran Dasar", "Statuta"],
}
