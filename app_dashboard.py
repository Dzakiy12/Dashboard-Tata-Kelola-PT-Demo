"""Dashboard peringatan dini tata kelola yayasan-PT (contoh/prototipe).

Jalankan:
    pip install streamlit pandas rapidfuzz openpyxl plotly
    streamlit run app_dashboard.py

Sumber data (urutan prioritas):
1. Database, bila DB_URL diisi (lihat fungsi ambil_url). Perlu: pip install sqlalchemy
2. Unggah template Excel master (sheet: yayasan, pt, organ_yayasan, pimpinan_pt, aturan_statuta, dst.)
3. Data contoh fiktif bawaan (buat_sample.py), agar dashboard tetap bisa dicoba tanpa data.

Perhitungan flag (F) dan indikator risiko (R) ada di indikator.py -- pisahkan logika dari tampilan
supaya mudah diuji dan diperluas.
"""
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from indikator import buang_contoh, hitung_f1_f2, hitung_risiko_per_pt, semua_flag, skor_komposit

st.set_page_config(page_title="Peringatan Dini Tata Kelola Yayasan-PT", layout="wide")
STATUS_FILE = Path("status_temuan.csv")
STATUS_OPSI = ["Belum ditinjau", "Sedang diverifikasi", "Terbukti", "Tidak terbukti"]
WARNA = {"Hijau": "#2e7d32", "Kuning": "#b58900", "Merah": "#c62828"}


# ---------- Sumber data ----------
def ambil_url():
    if os.environ.get("DB_URL"):
        return os.environ["DB_URL"]
    try:
        return st.secrets["db_url"]
    except Exception:
        return None


@st.cache_data(ttl=600)
def muat_excel(file):
    s = pd.read_excel(file, sheet_name=None, skiprows=[1] if file is not None else None)
    return buang_contoh(s)


@st.cache_data(ttl=600)
def muat_db(url):
    from sqlalchemy import create_engine, text
    engine = create_engine(url, pool_pre_ping=True)
    tabel = ["yayasan", "pt", "riwayat_penyelenggara", "akta", "organ_yayasan", "pimpinan_pt",
             "aturan_statuta", "riwayat_perubahan"]
    s = {}
    for t in tabel:
        try:
            s[t] = pd.read_sql(text(f"SELECT * FROM {t}"), engine)
        except Exception:
            s[t] = pd.DataFrame()
    return buang_contoh(s)


@st.cache_data
def muat_contoh():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from buat_sample import SHEETS
    return SHEETS


def tgl(t):
    if pd.isna(t):
        return "-"
    return "sekarang" if pd.Timestamp(t) >= pd.Timestamp("2099-01-01") else pd.Timestamp(t).strftime("%Y-%m-%d")


# ---------- Status tinjauan ----------
def baca_status():
    if STATUS_FILE.exists():
        return pd.read_csv(STATUS_FILE, dtype=str).fillna("").set_index("id_temuan")
    return pd.DataFrame(columns=["status", "catatan", "pemeriksa", "waktu"]).rename_axis("id_temuan")


def simpan_status(id_temuan, status, catatan, pemeriksa):
    df = baca_status()
    df.loc[id_temuan] = [status, catatan, pemeriksa, pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")]
    df.to_csv(STATUS_FILE)


# ---------- Sidebar: pilih sumber data ----------
st.sidebar.header("Data")
url = ambil_url()
sumber = None
if url:
    data = muat_db(url)
    sumber = "database"
else:
    unggah = st.sidebar.file_uploader("Unggah template Excel (opsional)", type="xlsx")
    if unggah:
        data = muat_excel(unggah)
        sumber = "unggahan"
    else:
        data = muat_contoh()
        sumber = "contoh"

if sumber == "contoh":
    st.sidebar.info("Memakai **data contoh fiktif**. Unggah template Excel untuk memakai data asli.")
else:
    st.sidebar.success(f"Sumber data: {sumber}")

wilayah_semua = sorted(data.get("pt", pd.DataFrame()).get("wilayah_lldikti", pd.Series(dtype=str)).dropna().unique())
wilayah_pilih = st.sidebar.multiselect("Filter wilayah LLDikti", wilayah_semua, default=wilayah_semua)

# ---------- Hitung indikator ----------
risiko = hitung_risiko_per_pt(data)
if not risiko.empty:
    risiko = skor_komposit(risiko)
flag_frames = semua_flag(data)
flag_semua = pd.concat(flag_frames, ignore_index=True) if flag_frames else pd.DataFrame()

if wilayah_pilih and not risiko.empty:
    risiko_v = risiko[risiko["wilayah_lldikti"].isin(wilayah_pilih)]
    kode_terpilih = set(risiko_v["kode_pt"])
    flag_v = flag_semua[flag_semua["kode_pt"].isin(kode_terpilih)] if not flag_semua.empty else flag_semua
else:
    risiko_v, flag_v = risiko, flag_semua

status_df = baca_status()
if not flag_v.empty:
    flag_v = flag_v.copy()
    flag_v["status"] = flag_v["id_temuan"].map(status_df["status"]).fillna("Belum ditinjau")

# ==================== HALAMAN ====================
halaman = st.sidebar.radio("Halaman", ["Ringkasan", "Detail temuan"])
st.sidebar.caption("Ambang level risiko dan bobot indikator di sini adalah usulan awal ilustratif, "
                   "belum disepakati pakar kelembagaan. Jangan dipakai sebagai dasar keputusan final.")

if halaman == "Ringkasan":
    st.title("Ringkasan tata kelola yayasan-PT")
    if risiko_v.empty:
        st.warning("Data pt/pimpinan_pt/aturan_statuta belum cukup untuk menghitung indikator.")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total PT", len(risiko_v))
    c2.metric("Level merah", int((risiko_v["level"] == "Merah").sum()))
    c3.metric("Level kuning", int((risiko_v["level"] == "Kuning").sum()))
    c4.metric("Flag pelanggaran", len(flag_v))

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Sebaran level risiko")
        agg = risiko_v["level"].value_counts().reindex(["Hijau", "Kuning", "Merah"]).fillna(0).reset_index()
        agg.columns = ["level", "jumlah"]
        fig = px.bar(agg, x="level", y="jumlah", color="level",
                     color_discrete_map=WARNA, text="jumlah")
        fig.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig, width="stretch")
    with col2:
        st.subheader("Flag pelanggaran per jenis")
        if flag_v.empty:
            st.info("Tidak ada flag pelanggaran pada data/filter saat ini.")
        else:
            agg2 = flag_v["_kelompok"].value_counts().reset_index()
            agg2.columns = ["jenis", "jumlah"]
            fig2 = px.bar(agg2, x="jenis", y="jumlah", text="jumlah")
            fig2.update_layout(height=320)
            st.plotly_chart(fig2, width="stretch")

    st.subheader("Daftar prioritas (skor risiko tertinggi)")
    tampil = risiko_v.sort_values("skor_risiko", ascending=False)[
        ["nama_pt", "nama_yayasan", "wilayah_lldikti", "skor_risiko", "level"]
    ].rename(columns={"nama_pt": "PT", "nama_yayasan": "Yayasan", "wilayah_lldikti": "Wilayah",
                      "skor_risiko": "Skor", "level": "Level"})
    st.dataframe(tampil, hide_index=True, width="stretch", height=320)

    if not flag_v.empty:
        st.subheader("Ringkasan flag pelanggaran")
        ringkas_flag = flag_v.groupby(["_kelompok", "nama_pt"]).size().reset_index(name="jumlah")
        st.dataframe(ringkas_flag.rename(columns={"_kelompok": "Jenis flag", "nama_pt": "PT", "jumlah": "Jumlah"}),
                    hide_index=True, width="stretch")

    st.caption("Skor risiko = rata-rata indikator R1-R13 yang ternormalisasi (0-1), bobot sama rata. "
              "Data pengaduan/kasus konflik belum tersedia di sheet ini sehingga sebagian indikator (R2, R16) "
              "hanya sebagian terhitung atau ditandai kosong.")

else:
    st.title("Detail temuan")
    if flag_v.empty:
        st.success("Tidak ada temuan flag pelanggaran pada data/filter saat ini.")
        st.stop()

    pilih_status = st.sidebar.multiselect("Status tinjauan", STATUS_OPSI, default=STATUS_OPSI)
    view = flag_v[flag_v["status"].isin(pilih_status)]
    if view.empty:
        st.info("Tidak ada temuan dengan status yang dipilih.")
        st.stop()

    idx = st.selectbox("Pilih temuan", view.index,
                       format_func=lambda i: f"{view.at[i,'id_temuan']} | {view.at[i,'nama_pt']}")
    r = flag_v.loc[idx]
    kel = r["_kelompok"]

    kiri, kanan = st.columns([4, 1])
    kiri.subheader(r["nama_pt"])
    kiri.caption(f"{r.get('nama_yayasan','')} · {r['id_temuan']}")
    kanan.markdown(f":red[**Flag: {kel}**]")

    if kel == "F1/F2":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Keyakinan", r["keyakinan"].split(" (")[0])
        c2.metric("Irisan mulai", tgl(r["irisan_mulai"]))
        c3.metric("Lama irisan", f"{r['lama_bulan']} bulan")
        c4.metric("Status", r["status"])
        st.markdown("#### Bukti")
        bukti = pd.DataFrame([
            {"Sisi": "Yayasan", "Nama": r["nama_lengkap_org"], "Jabatan": r["jabatan_yayasan"],
             "Mulai": tgl(r["tgl_mulai_org"]), "Akhir": tgl(r["tgl_akhir_org"])},
            {"Sisi": "Perguruan tinggi", "Nama": r["nama_lengkap_pim"],
             "Jabatan": f"{r['jabatan_pt']} ({r['status_definitif']})",
             "Mulai": tgl(r["tgl_mulai_pim"]), "Akhir": tgl(r["tgl_akhir_pim"])},
        ])
        st.dataframe(bukti, hide_index=True, width="stretch")
        if r.get("f2"):
            st.error(f"{r.get('versi_statuta','-')}, {r.get('pasal_pengangkatan','-')}: "
                    "statuta melarang rangkap dengan organ yayasan (F2).")
        else:
            st.info("Statuta tidak/belum ditemukan melarang secara tegas (F1 tetap berlaku sebagai indikasi umum).")
    elif kel == "F3":
        c1, c2 = st.columns(2)
        c1.metric("Lama menjabat", f"{r['lama_tahun']} tahun")
        c2.metric("Batas statuta", f"{r['masa_jabatan_rektor_tahun']} tahun ({r['versi_statuta']})")
        st.write(f"**{r['nama_lengkap']}** menjabat {r['jabatan_pt']} sejak {tgl(r['tgl_mulai'])}.")
    elif kel == "F6":
        c1, c2 = st.columns(2)
        c1.metric("Lama menjabat", f"{r['lama_tahun']} tahun (dari {r['masa_jabatan_rektor_tahun']} tahun)")
        c2.metric("Alasan tercatat", r.get("alasan_berhenti") or "-")
        st.write(f"**{r['nama_lengkap']}** ({r['jabatan_pt']}) berhenti {tgl(r['tgl_akhir'])}, "
                f"dokumen proses pemberhentian: {r.get('ada_dok_pemberhentian','-')}.")
    elif kel == "F7":
        st.metric("Lewat masa jabatan", f"{r['bulan_lewat']} bulan")
        st.write(f"**{r['nama_lengkap']}** ({r['jabatan_yayasan']}) di {r.get('nama_yayasan','-')}, "
                f"masa jabatan berakhir {tgl(r['tgl_akhir'])} tanpa akta pembaruan yang tercatat.")

    st.markdown("#### Tinjauan pakar")
    riwayat = status_df.loc[r["id_temuan"]] if r["id_temuan"] in status_df.index else None
    with st.form(f"tinjau_{idx}"):
        baru = st.selectbox("Status", STATUS_OPSI, index=STATUS_OPSI.index(r["status"]))
        catatan = st.text_area("Catatan pemeriksa", value=riwayat["catatan"] if riwayat is not None else "")
        pemeriksa = st.text_input("Pemeriksa", value=riwayat["pemeriksa"] if riwayat is not None else "")
        if st.form_submit_button("Simpan"):
            simpan_status(r["id_temuan"], baru, catatan, pemeriksa)
            st.rerun()
    if riwayat is not None:
        st.caption(f"Terakhir diperbarui {riwayat['waktu']} oleh {riwayat['pemeriksa'] or '-'}")
