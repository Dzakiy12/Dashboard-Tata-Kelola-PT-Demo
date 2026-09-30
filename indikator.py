"""Perhitungan flag pelanggaran (F) dan indikator risiko (R) dari template master data.

Semua fungsi menerima `s`: dict nama_sheet -> DataFrame (hasil pd.read_excel(sheet_name=None)).
Ambang batas (AMBANG_*) adalah usulan awal untuk didiskusikan bersama pakar kelembagaan,
lalu diuji terhadap kasus yang sudah diketahui sebelum dipakai sebagai dasar keputusan.
"""
from datetime import date

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

HARI_INI = pd.Timestamp(date.today())
FAR = pd.Timestamp("2100-01-01")
TGL_SE_RANGKAP = pd.Timestamp("2021-03-26")  # SE Dirjen Dikti No. 3/2021; verifikasi status hukum ke tim hukum
AMBANG_NAMA = 92
JENDELA_TAHUN = 3          # jendela "3 tahun terakhir" untuk R1, R4
JENDELA_BERSAMAAN_HARI = 183  # ~6 bulan, untuk R8/R9
GELAR = {"prof", "dr", "drs", "dra", "ir", "h", "hj", "s.h", "m.h", "s.e", "m.m",
         "m.si", "s.t", "m.t", "s.kom", "m.kom", "m.pd", "s.pd", "s.sos", "m.a"}


# ---------- util ----------
def _norm_nama(nama):
    if pd.isna(nama):
        return ""
    kata = [k.strip(".") for k in str(nama).lower().replace(",", " ").split()]
    kata = [k for k in kata if k and k not in GELAR]
    return " ".join("".join(ch for ch in k if ch.isalpha()) for k in kata).strip()


def _akhir_efektif(seri_tanggal):
    return seri_tanggal.fillna(FAR)


def _ya(nilai):
    return nilai.isin(["Ya", "Dilarang"])


def _get(s, nama, kolom=None):
    df = s.get(nama, pd.DataFrame()).copy()
    if kolom:
        for c in kolom:
            if c not in df.columns:
                df[c] = pd.NA
        df = df[kolom]
    for c in [c for c in df.columns if str(c).startswith("tgl_")]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def buang_contoh(s):
    """Buang baris contoh (id berawalan CONTOH-) yang tersisa dari template yang belum diisi penuh."""
    out = {}
    for k, df in s.items():
        if df.empty or df.columns.empty:
            out[k] = df
            continue
        kol_id = df.columns[0]
        out[k] = df[~df[kol_id].astype(str).str.startswith("CONTOH", na=False)].reset_index(drop=True)
    return out


# ---------- F1 & F2: rangkap jabatan yayasan <-> pimpinan PT ----------
def hitung_f1_f2(s):
    o = _get(s, "organ_yayasan", ["id_organ", "id_yayasan", "id_akta_sumber", "nama_lengkap", "nik",
                                  "jabatan_yayasan", "tgl_mulai", "tgl_akhir"])
    p = _get(s, "pimpinan_pt", ["id_pimpinan", "kode_pt", "id_yayasan", "nama_lengkap", "nik", "jabatan_pt",
                                "status_definitif", "tgl_mulai", "tgl_akhir", "no_sk_pengangkatan"])
    if o.empty or p.empty:
        return pd.DataFrame()
    m = o.merge(p, on="id_yayasan", suffixes=("_org", "_pim"))
    if m.empty:
        return m
    nik_sama = m["nik_org"].notna() & (m["nik_org"].astype(str) == m["nik_pim"].astype(str))
    m["skor_nama"] = [fuzz.token_sort_ratio(_norm_nama(a), _norm_nama(b))
                      for a, b in zip(m["nama_lengkap_org"], m["nama_lengkap_pim"])]
    m["keyakinan"] = np.where(nik_sama, "Tinggi (NIK sama)", "Perlu verifikasi (nama mirip)")
    m["irisan_mulai"] = m[["tgl_mulai_org", "tgl_mulai_pim"]].max(axis=1)
    m["irisan_akhir"] = pd.concat([_akhir_efektif(m["tgl_akhir_org"]), _akhir_efektif(m["tgl_akhir_pim"])], axis=1).min(axis=1)
    f = m[(nik_sama | (m["skor_nama"] >= AMBANG_NAMA)) & (m["irisan_mulai"] <= m["irisan_akhir"])].copy()
    if f.empty:
        return f
    f["id_temuan"] = "F1-" + f["id_organ"].astype(str) + "-" + f["id_pimpinan"].astype(str)
    akhir = f["irisan_akhir"].where(f["irisan_akhir"] < FAR, HARI_INI)
    f["lama_bulan"] = ((akhir - f["irisan_mulai"]).dt.days / 30.4).round().astype(int)
    f["setelah_se_rangkap"] = f["irisan_akhir"] >= TGL_SE_RANGKAP

    a = _get(s, "aturan_statuta", ["kode_pt", "versi_statuta", "tgl_berlaku", "tgl_berakhir",
                                    "larangan_rangkap_organ_yayasan", "pasal_pengangkatan", "kutipan_pengangkatan"])
    x = f[["id_temuan", "kode_pt", "irisan_mulai"]].merge(a, on="kode_pt", how="left")
    berlaku = (x["tgl_berlaku"] <= x["irisan_mulai"]) & (x["tgl_berakhir"].isna() | (x["tgl_berakhir"] >= x["irisan_mulai"]))
    f = f.merge(x[berlaku].drop(columns=["kode_pt", "irisan_mulai"]), on="id_temuan", how="left")
    f["f2"] = _ya(f["larangan_rangkap_organ_yayasan"].fillna(""))
    f = f.merge(_get(s, "pt", ["kode_pt", "nama_pt"]), on="kode_pt", how="left")
    f = f.merge(_get(s, "yayasan", ["id_yayasan", "nama_yayasan"]), on="id_yayasan", how="left")
    return f.reset_index(drop=True)


# ---------- F3: jabatan melebihi ketentuan statuta ----------
def hitung_f3(s):
    p = _get(s, "pimpinan_pt", ["id_pimpinan", "kode_pt", "nama_lengkap", "jabatan_pt", "status_definitif",
                                "tgl_mulai", "tgl_akhir"])
    a = _get(s, "aturan_statuta", ["kode_pt", "versi_statuta", "tgl_berlaku", "tgl_berakhir",
                                    "masa_jabatan_rektor_tahun"])
    if p.empty or a.empty:
        return pd.DataFrame()
    m = p.merge(a, on="kode_pt")
    berlaku = (m["tgl_berlaku"] <= m["tgl_mulai"]) & (m["tgl_berakhir"].isna() | (m["tgl_berakhir"] >= m["tgl_mulai"]))
    m = m[berlaku].copy()
    if m.empty:
        return m
    akhir = _akhir_efektif(m["tgl_akhir"]).where(lambda x: x < FAR, HARI_INI)
    m["lama_tahun"] = (akhir - m["tgl_mulai"]).dt.days / 365.25
    f = m[(m["status_definitif"] == "Definitif") & (m["masa_jabatan_rektor_tahun"].notna()) &
          (m["lama_tahun"] > m["masa_jabatan_rektor_tahun"] + 0.5)].copy()
    if f.empty:
        return f
    f["id_temuan"] = "F3-" + f["id_pimpinan"].astype(str)
    f["lama_tahun"] = f["lama_tahun"].round(1)
    return f.merge(_get(s, "pt", ["kode_pt", "nama_pt"]), on="kode_pt", how="left")


# ---------- F6: pemberhentian dini tanpa dasar sah ----------
def hitung_f6(s):
    p = _get(s, "pimpinan_pt", ["id_pimpinan", "kode_pt", "nama_lengkap", "jabatan_pt", "tgl_mulai", "tgl_akhir",
                                "alasan_berhenti", "ada_dok_pemberhentian"])
    a = _get(s, "aturan_statuta", ["kode_pt", "versi_statuta", "tgl_berlaku", "tgl_berakhir",
                                    "masa_jabatan_rektor_tahun", "alasan_pemberhentian_sah"])
    p = p[p["tgl_akhir"].notna()].copy()
    if p.empty or a.empty:
        return pd.DataFrame()
    m = p.merge(a, on="kode_pt")
    berlaku = (m["tgl_berlaku"] <= m["tgl_mulai"]) & (m["tgl_berakhir"].isna() | (m["tgl_berakhir"] >= m["tgl_mulai"]))
    m = m[berlaku].copy()
    if m.empty:
        return m
    m["lama_tahun"] = (m["tgl_akhir"] - m["tgl_mulai"]).dt.days / 365.25
    dini = m["masa_jabatan_rektor_tahun"].notna() & (m["lama_tahun"] < m["masa_jabatan_rektor_tahun"] - 0.5)

    def alasan_sah(row):
        if pd.isna(row["alasan_berhenti"]) or pd.isna(row["alasan_pemberhentian_sah"]):
            return None
        daftar = [x.strip().lower() for x in str(row["alasan_pemberhentian_sah"]).split(";")]
        return str(row["alasan_berhenti"]).strip().lower() in daftar

    m["alasan_sah"] = m.apply(alasan_sah, axis=1)
    tanpa_dasar = (m["alasan_sah"] == False) | (m["ada_dok_pemberhentian"] == "Tidak")  # noqa: E712
    f = m[dini & tanpa_dasar].copy()
    if f.empty:
        return f
    f["id_temuan"] = "F6-" + f["id_pimpinan"].astype(str)
    f["lama_tahun"] = f["lama_tahun"].round(1)
    return f.merge(_get(s, "pt", ["kode_pt", "nama_pt"]), on="kode_pt", how="left")


# ---------- F7: organ yayasan lewat masa jabatan tanpa akta pembaruan ----------
def hitung_f7(s):
    o = _get(s, "organ_yayasan", ["id_organ", "id_yayasan", "nama_lengkap", "jabatan_yayasan",
                                  "tgl_mulai", "tgl_akhir", "status_periode"])
    if o.empty:
        return pd.DataFrame()
    f = o[(o["status_periode"] == "Berjalan") & o["tgl_akhir"].notna() & (o["tgl_akhir"] < HARI_INI)].copy()
    if f.empty:
        return f
    f["id_temuan"] = "F7-" + f["id_organ"].astype(str)
    f["bulan_lewat"] = ((HARI_INI - f["tgl_akhir"]).dt.days / 30.4).round().astype(int)
    return f.merge(_get(s, "yayasan", ["id_yayasan", "nama_yayasan"]), on="id_yayasan", how="left")


# ---------- Indikator risiko (R) per PT, dinormalisasi 0-1 ----------
def hitung_risiko_per_pt(s):
    pt = _get(s, "pt", ["kode_pt", "nama_pt", "id_yayasan", "wilayah_lldikti", "jumlah_mahasiswa_aktif"])
    yay = _get(s, "yayasan", ["id_yayasan", "nama_yayasan", "status_yayasan"])
    pim = _get(s, "pimpinan_pt", ["kode_pt", "id_yayasan", "nama_lengkap", "jabatan_pt", "status_definitif",
                                  "tgl_mulai", "tgl_akhir"])
    org = _get(s, "organ_yayasan", ["id_yayasan", "tgl_mulai", "tgl_akhir"])
    atr = _get(s, "aturan_statuta", ["kode_pt", "tgl_berlaku", "tgl_berakhir", "wajib_penjaringan",
                                     "wajib_pertimbangan_senat", "larangan_rangkap_organ_yayasan",
                                     "ada_senat", "ada_spi", "yayasan_berwenang_akademik"])
    riw = _get(s, "riwayat_perubahan", ["id_entitas", "tgl_perubahan", "menyentuh_pasal_pimpinan"])
    if pt.empty:
        return pd.DataFrame()

    batas = HARI_INI - pd.Timedelta(days=365 * JENDELA_TAHUN)
    out = pt.merge(yay, on="id_yayasan", how="left")

    # R1: frekuensi pergantian pimpinan definitif dalam 3 tahun terakhir
    p_def = pim[pim["status_definitif"] == "Definitif"]
    r1 = p_def[p_def["tgl_mulai"] >= batas].groupby("kode_pt").size().rename("R1_frekuensi_pergantian_pimpinan")
    out = out.merge(r1, on="kode_pt", how="left")

    # R2: berhenti sebelum masa jabatan berakhir (memakai hasil F6 sebagai proksi jumlah, tanpa detail alasan)
    berhenti = pim[pim["tgl_akhir"].notna()].merge(
        atr[["kode_pt", "tgl_berlaku"]], on="kode_pt", how="left")
    r2 = berhenti.groupby("kode_pt").size().rename("R2_jumlah_pernah_berhenti")
    out = out.merge(r2, on="kode_pt", how="left")

    # R3: lama status Plt/Pj yang sedang berjalan (bulan)
    aktif_sementara = pim[pim["status_definitif"].isin(["Plt", "Pj", "Plh"]) & pim["tgl_akhir"].isna()]
    r3 = ((HARI_INI - aktif_sementara["tgl_mulai"]).dt.days / 30.4).round()
    r3 = aktif_sementara.assign(R3_lama_plt_bulan=r3).groupby("kode_pt")["R3_lama_plt_bulan"].max()
    out = out.merge(r3, on="kode_pt", how="left")

    # R4: frekuensi pergantian organ yayasan dalam 3 tahun (per yayasan, disebar ke semua PT-nya)
    r4 = org[org["tgl_mulai"] >= batas].groupby("id_yayasan").size().rename("R4_frekuensi_pergantian_organ")
    out = out.merge(r4, on="id_yayasan", how="left")

    # R7: yayasan berstatus bersengketa
    out["R7_yayasan_bersengketa"] = (out["status_yayasan"] == "Bersengketa").astype(int)

    # R9: perubahan aturan (statuta/AD) dalam <=6 bulan sebelum pergantian pimpinan (indikasi)
    def cek_r9(kode_pt, id_yayasan):
        mulai_baru = pim[(pim["kode_pt"] == kode_pt)]["tgl_mulai"]
        peru = riw[(riw["id_entitas"].isin([kode_pt, id_yayasan])) & (riw["menyentuh_pasal_pimpinan"] == "Ya")]
        if peru.empty or mulai_baru.empty:
            return 0
        for tp in peru["tgl_perubahan"]:
            if ((mulai_baru - tp).dt.days.between(0, JENDELA_BERSAMAAN_HARI)).any():
                return 1
        return 0
    out["R9_aturan_berubah_menjelang_pergantian"] = out.apply(
        lambda r: cek_r9(r["kode_pt"], r["id_yayasan"]), axis=1)

    # R12: kelengkapan aturan statuta -- proporsi kolom kunci yang "Tidak diatur" (versi berlaku sekarang)
    kolom_atur = ["wajib_penjaringan", "wajib_pertimbangan_senat", "larangan_rangkap_organ_yayasan",
                  "ada_senat", "ada_spi"]
    berlaku_skrg = atr[atr["tgl_berlaku"] <= HARI_INI].copy()
    berlaku_skrg = berlaku_skrg.sort_values("tgl_berlaku").groupby("kode_pt").tail(1)
    if not berlaku_skrg.empty:
        berlaku_skrg["R12_kelengkapan_statuta"] = berlaku_skrg[kolom_atur].apply(
            lambda row: (row == "Tidak diatur").sum() / len(kolom_atur), axis=1)
        out = out.merge(berlaku_skrg[["kode_pt", "R12_kelengkapan_statuta", "yayasan_berwenang_akademik"]],
                         on="kode_pt", how="left")
        out["R13_kewenangan_akademik_yayasan"] = (out["yayasan_berwenang_akademik"] == "Ya").astype(int)
    else:
        out["R12_kelengkapan_statuta"] = np.nan
        out["R13_kewenangan_akademik_yayasan"] = 0

    # R16: kepadatan pengaduan -- dilewati bila sheet pengaduan tidak tersedia di file ini
    out["R16_pengaduan_per_1000_mhs"] = np.nan

    return out


def skor_komposit(df_risiko):
    """Normalisasi min-max per kolom R_* lalu jumlahkan dengan bobot sama. Bobot & ambang: usulan awal,
    perlu disepakati bersama pakar kelembagaan dan diuji terhadap kasus yang sudah diketahui."""
    kolom_r = [c for c in df_risiko.columns if c.startswith("R") and c[1].isdigit()]
    df = df_risiko.copy()
    norm_cols = []
    for c in kolom_r:
        nilai = df[c].fillna(0)
        rentang = nilai.max() - nilai.min()
        df[c + "_n"] = (nilai - nilai.min()) / rentang if rentang > 0 else 0.0
        norm_cols.append(c + "_n")
    df["skor_risiko"] = df[norm_cols].mean(axis=1).round(3) if norm_cols else 0.0
    df["level"] = pd.cut(df["skor_risiko"], [-0.01, 0.33, 0.66, 1.01], labels=["Hijau", "Kuning", "Merah"])
    return df


def semua_flag(s):
    hasil = []
    for nama, fn in [("F1/F2", hitung_f1_f2), ("F3", hitung_f3), ("F6", hitung_f6), ("F7", hitung_f7)]:
        try:
            df = fn(s)
        except Exception:
            df = pd.DataFrame()
        if not df.empty:
            df = df.assign(_kelompok=nama)
            hasil.append(df)
    return hasil
