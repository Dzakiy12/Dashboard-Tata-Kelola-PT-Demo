"""Mesin aturan Early Warning System (deterministik, bisa diaudit).

Status per entitas = temuan terburuk: Merah > Kuning > Hijau.
Setiap temuan menyimpan kode aturan, uraian, dan dasar (pasal statuta) agar bisa dijelaskan.

CATATAN: aturan di bawah adalah USULAN AWAL berdasarkan kolom data. Harus divalidasi ahli hukum
sebelum dipakai untuk keputusan nyata.
"""
import json
from datetime import date
from pathlib import Path
import pandas as pd
from dateutil.relativedelta import relativedelta

CFG_PATH = Path(__C:\Users\user\Downloads\ews_prototipe (1)\ews\data\Contoh_Data_50_Yayasan__).parent / "rules_config.json"
RANK = {"Hijau": 1, "Kuning": 2, "Merah": 3}

RULES = {
    "PIM-01": ("Penjaringan calon pimpinan", "Statuta mewajibkan penjaringan, tetapi dokumennya tidak ada (kuning jika statuta tidak mengatur)."),
    "PIM-02": ("Pertimbangan senat saat pengangkatan", "Statuta mewajibkan pertimbangan senat, tetapi dokumennya tidak ada (kuning jika tidak diatur)."),
    "PIM-03": ("Rangkap jabatan dengan organ yayasan", "Merah jika statuta melarang rangkap; kuning jika tidak diatur atau status rangkap tidak diketahui."),
    "PIM-04": ("Prosedur pemberhentian", "Pemberhentian tanpa dokumen padahal prosedur diatur (merah); tidak diatur/tidak diketahui (kuning)."),
    "PIM-05": ("Masa jabatan", "Jabatan melewati masa jabatan menurut statuta (+ toleransi hari)."),
    "PIM-06": ("Jumlah periode jabatan", "Seseorang menjabat lebih dari batas maksimum periode menurut statuta."),
    "PIM-07": ("Tanggal SK pengangkatan", "SK pengangkatan terbit setelah jabatan dimulai."),
    "PIM-08": ("Pimpinan non-definitif (Plt/Pj)", "Plt/Pj menjabat lebih lama dari batas bulan."),
    "PIM-09": ("Statuta berlaku saat pengangkatan", "Tidak ada versi statuta yang berlaku pada tanggal pengangkatan."),
    "PIM-10": ("Pengangkatan setelah perubahan AD", "Pimpinan diangkat dalam jendela waktu setelah perubahan AD yang menyentuh kewenangan pimpinan PT."),
    "PIM-11": ("Konsistensi data rangkap", "Data menyatakan tidak rangkap, tetapi nama sama dengan organ yayasan aktif."),
    "PT-01": ("Akreditasi PT", "Akreditasi kedaluwarsa atau belum terakreditasi."),
    "PT-02": ("Status PT", "PT dalam pembinaan atau tidak aktif."),
    "PT-03": ("Penyelenggara aktif", "PT harus punya tepat satu penyelenggara aktif yang sama dengan yayasan di data PT."),
    "PT-04": ("Alih kelola", "Alih kelola tanpa nomor SK (merah); karena sengketa/sanksi (kuning)."),
    "PT-05": ("Statuta PT", "PT tidak memiliki statuta."),
    "PT-06": ("Kewenangan akademik yayasan", "Statuta memberi yayasan kewenangan akademik."),
    "PT-07": ("Statuta belum disesuaikan dengan AD", "Statuta lebih lama daripada perubahan AD yayasan yang menyentuh pimpinan PT."),
    "PT-08": ("Kekosongan pimpinan", "PT aktif tanpa pimpinan yang sedang menjabat."),
    "YAY-01": ("Status yayasan", "Yayasan bersengketa/tidak aktif."),
    "YAY-02": ("Organ yayasan", "Lebih dari satu Ketua Pengurus berjalan (merah); organ wajib tidak lengkap (kuning)."),
    "YAY-03": ("Kesesuaian SK badan hukum", "Nomor SK badan hukum berbeda dengan SK pada akta pendirian."),
}


def load_cfg():
    try:
        cfg = json.loads(CFG_PATH.read_text())
    except Exception:
        cfg = {}
    cfg.setdefault("parameter", {})
    cfg["parameter"].setdefault("toleransi_hari_masa_jabatan", 31)
    cfg["parameter"].setdefault("batas_bulan_plt_pj", 6)
    cfg["parameter"].setdefault("jendela_bulan_pasca_perubahan_ad", 12)
    cfg.setdefault("aktif", {})
    return cfg


def save_cfg(cfg):
    CFG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def _d(df, cols):
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def _v(x):
    return None if pd.isna(x) else x


def _norm(s):
    return str(s).strip().lower() if not pd.isna(s) else ""


def evaluate(data, cfg=None, today=None, include_historis=True):
    cfg = cfg or load_cfg()
    P = cfg["parameter"]
    on = lambda code: cfg["aktif"].get(code, True)
    today = pd.Timestamp(today or date.today())

    yy = data["yayasan"]
    pt = data["pt"]
    pen = _d(data["riwayat_penyelenggara"], ["tgl_mulai", "tgl_akhir"])
    akta = _d(data["akta"], ["tgl_akta", "tgl_berlaku"])
    organ = _d(data["organ_yayasan"], ["tgl_mulai", "tgl_akhir"])
    pim = _d(data["pimpinan_pt"], ["tgl_mulai", "tgl_akhir", "tgl_sk_pengangkatan"])
    sta = _d(data["aturan_statuta"], ["tgl_berlaku", "tgl_berakhir"]).sort_values("tgl_berlaku")
    per = _d(data["riwayat_perubahan"], ["tgl_perubahan"])
    pt_yay = dict(zip(pt.kode_pt, pt.id_yayasan))
    F = []

    def add(code, tingkat, level, yid, kpt, ref, uraian, aktif=True, dasar=""):
        if on(code):
            F.append(dict(tingkat=tingkat, kode_aturan=code, level=level, id_yayasan=yid, kode_pt=kpt,
                          referensi=ref, uraian=uraian, dasar=dasar, aktif=bool(aktif)))

    sta_by_pt = {k: g for k, g in sta.groupby("kode_pt")}

    def pick(kpt, tgl):
        g = sta_by_pt.get(kpt)
        if g is None or pd.isna(tgl):
            return None, False
        ok = g[(g.tgl_berlaku <= tgl) & (g.tgl_berakhir.isna() | (g.tgl_berakhir >= tgl))]
        return (ok.iloc[-1], True) if len(ok) else (g.iloc[0], False)

    # perubahan AD yang menyentuh kewenangan pimpinan PT, per yayasan
    ad_dates = {}
    for _, a in akta[akta.ubah_kewenangan_terhadap_pt == "Ya"].iterrows():
        ad_dates.setdefault(a.id_yayasan, set()).add(a.tgl_berlaku)
    for _, r in per[(per.jenis_dokumen == "Anggaran Dasar") & (per.menyentuh_pasal_pimpinan == "Ya")].iterrows():
        ad_dates.setdefault(r.id_entitas, set()).add(r.tgl_perubahan)

    # ---------- aturan pimpinan ----------
    pim = pim.sort_values(["kode_pt", "nama_lengkap", "tgl_mulai"])
    periode_ke = pim.groupby(["kode_pt", pim.nama_lengkap.map(_norm)]).cumcount() + 1
    for (i, p), n in zip(pim.iterrows(), periode_ke.loc[pim.index]):
        s, valid = pick(p.kode_pt, p.tgl_sk_pengangkatan if not pd.isna(p.tgl_sk_pengangkatan) else p.tgl_mulai)
        akt = pd.isna(p.tgl_akhir) or p.tgl_akhir > today
        ref = f"{p.id_pimpinan} - {p.nama_lengkap} ({p.jabatan_pt})"
        kw = dict(level="Pimpinan", yid=p.id_yayasan, kpt=p.kode_pt, ref=ref, aktif=akt)
        if s is None:
            add("PIM-09", "Kuning", uraian="Statuta PT tidak ditemukan; aturan pimpinan tidak bisa diuji.", **kw)
            continue
        if not valid:
            add("PIM-09", "Kuning", uraian=f"Tidak ada statuta yang berlaku pada tanggal pengangkatan "
                f"({p.tgl_sk_pengangkatan:%d-%m-%Y}); diuji dengan statuta {s.versi_statuta}.", **kw)
        pasal_a, pasal_b = _v(s.pasal_pengangkatan) or "", _v(s.pasal_pemberhentian) or ""
        da = f"{s.versi_statuta}, {pasal_a}"
        db_ = f"{s.versi_statuta}, {pasal_b}"
        # 01 penjaringan
        if p.ada_dok_penjaringan == "Tidak":
            if s.wajib_penjaringan == "Ya":
                add("PIM-01", "Merah", uraian="Statuta mewajibkan penjaringan, dokumen penjaringan tidak ada.", dasar=da, **kw)
            else:
                add("PIM-01", "Kuning", uraian="Dokumen penjaringan tidak ada; statuta tidak mengatur kewajiban penjaringan.", dasar=da, **kw)
        # 02 senat
        if p.ada_dok_pertimbangan_senat == "Tidak":
            if s.wajib_pertimbangan_senat == "Ya" or "senat" in str(s.pengangkat_rektor).lower():
                add("PIM-02", "Merah", uraian="Pengangkatan wajib melalui pertimbangan senat, dokumen tidak ada.", dasar=da, **kw)
            else:
                add("PIM-02", "Kuning", uraian="Dokumen pertimbangan senat tidak ada; statuta tidak mengatur kewajibannya.", dasar=da, **kw)
        # 03 rangkap
        if p.merangkap_organ_yayasan == "Ya":
            if s.larangan_rangkap_organ_yayasan == "Ya":
                add("PIM-03", "Merah", uraian="Merangkap organ yayasan padahal statuta melarang.", dasar=da, **kw)
            else:
                add("PIM-03", "Kuning", uraian="Merangkap organ yayasan; statuta tidak mengatur larangan rangkap.", dasar=da, **kw)
        elif p.merangkap_organ_yayasan == "Tidak diketahui":
            add("PIM-03", "Kuning", uraian="Status rangkap jabatan dengan organ yayasan belum diketahui.", **kw)
        else:
            o = organ[(organ.id_yayasan == p.id_yayasan) & (organ.nama_lengkap.map(_norm) == _norm(p.nama_lengkap))
                      & (organ.tgl_mulai <= (p.tgl_akhir if not pd.isna(p.tgl_akhir) else today))
                      & (organ.tgl_akhir.isna() | (organ.tgl_akhir >= p.tgl_mulai))]
            if len(o):
                add("PIM-11", "Kuning", uraian=f"Data rangkap 'Tidak', tetapi nama sama dengan organ yayasan "
                    f"({o.iloc[0].jabatan_yayasan}). Verifikasi.", **kw)
        # 04 pemberhentian
        if p.alasan_berhenti == "Diberhentikan":
            if p.ada_dok_pemberhentian == "Tidak":
                if s.prosedur_pemberhentian_diatur == "Ya":
                    add("PIM-04", "Merah", uraian="Diberhentikan tanpa dokumen pemberhentian, padahal prosedur diatur statuta.", dasar=db_, **kw)
                else:
                    add("PIM-04", "Kuning", uraian="Diberhentikan tanpa dokumen; prosedur pemberhentian tidak diatur statuta.", dasar=db_, **kw)
            elif p.ada_dok_pemberhentian == "Tidak diketahui":
                add("PIM-04", "Kuning", uraian="Dokumen pemberhentian belum diketahui.", dasar=db_, **kw)
        # 05 masa jabatan
        masa = _v(s.masa_jabatan_rektor_tahun)
        if masa:
            batas = p.tgl_mulai + relativedelta(years=int(masa)) + pd.Timedelta(days=P["toleransi_hari_masa_jabatan"])
            akhir = today if pd.isna(p.tgl_akhir) else p.tgl_akhir
            if akhir > batas:
                lebih = (akhir - (batas - pd.Timedelta(days=P["toleransi_hari_masa_jabatan"]))).days
                ket = "masih menjabat" if pd.isna(p.tgl_akhir) else "menjabat"
                add("PIM-05", "Merah", uraian=f"Pimpinan {ket} melewati masa jabatan {int(masa)} tahun sebanyak {lebih} hari.",
                    dasar=s.versi_statuta, **kw)
        # 06 periode
        mx = _v(s.maks_periode_rektor)
        if mx and n > mx:
            add("PIM-06", "Merah", uraian=f"Menjabat periode ke-{n}, melebihi batas {int(mx)} periode.", dasar=s.versi_statuta, **kw)
        # 07 SK
        if not pd.isna(p.tgl_sk_pengangkatan) and p.tgl_sk_pengangkatan > p.tgl_mulai:
            add("PIM-07", "Kuning", uraian=f"SK pengangkatan ({p.tgl_sk_pengangkatan:%d-%m-%Y}) terbit setelah jabatan dimulai ({p.tgl_mulai:%d-%m-%Y}).", **kw)
        # 08 plt/pj
        if p.status_definitif in ("Plt", "Pj"):
            akhir = today if pd.isna(p.tgl_akhir) else p.tgl_akhir
            if akhir > p.tgl_mulai + relativedelta(months=P["batas_bulan_plt_pj"]):
                add("PIM-08", "Kuning", uraian=f"{p.status_definitif} menjabat lebih dari {P['batas_bulan_plt_pj']} bulan.", **kw)
        # 10 pasca perubahan AD
        for D in ad_dates.get(p.id_yayasan, []):
            if D <= p.tgl_mulai <= D + relativedelta(months=P["jendela_bulan_pasca_perubahan_ad"]):
                add("PIM-10", "Kuning", uraian=f"Diangkat dalam {P['jendela_bulan_pasca_perubahan_ad']} bulan setelah perubahan AD "
                    f"({D:%d-%m-%Y}) yang menyentuh kewenangan pimpinan PT. Periksa dasar kewenangan.", **kw)

    # ---------- aturan PT ----------
    for _, t in pt.iterrows():
        kw = dict(level="PT", yid=t.id_yayasan, kpt=t.kode_pt, ref=f"{t.kode_pt} - {t.nama_pt}")
        if t.akreditasi_pt in ("Kedaluwarsa", "Belum terakreditasi"):
            add("PT-01", "Kuning", uraian=f"Akreditasi PT: {t.akreditasi_pt}.", **kw)
        if t.status_pt != "Aktif":
            add("PT-02", "Kuning", uraian=f"Status PT: {t.status_pt}.", **kw)
        ps = pen[pen.kode_pt == t.kode_pt]
        aktif_ps = ps[ps.tgl_akhir.isna() | (ps.tgl_akhir > today)]
        if len(aktif_ps) == 0:
            add("PT-03", "Merah", uraian="PT tidak memiliki penyelenggara aktif.", **kw)
        elif len(aktif_ps) > 1:
            add("PT-03", "Merah", uraian="PT memiliki lebih dari satu penyelenggara aktif.", **kw)
        elif aktif_ps.iloc[0].id_yayasan != t.id_yayasan:
            add("PT-03", "Merah", uraian=f"Penyelenggara aktif ({aktif_ps.iloc[0].id_yayasan}) berbeda dengan yayasan pada data PT ({t.id_yayasan}).", **kw)
        for _, h in ps[ps.jenis_perpindahan.astype(str).str.contains("Alih kelola", na=False)].iterrows():
            akt = pd.isna(h.tgl_akhir) or h.tgl_akhir > today
            yid = h.id_yayasan_sebelumnya if not pd.isna(h.id_yayasan_sebelumnya) else t.id_yayasan
            k2 = dict(kw, yid=yid, aktif=False)
            if pd.isna(h.no_sk_alih_kelola):
                add("PT-04", "Merah", uraian="Alih kelola tanpa nomor SK.", **k2)
            elif str(h.alasan_alih_kelola) in ("Sengketa yayasan", "Tindak lanjut sanksi/pembinaan"):
                add("PT-04", "Kuning", uraian=f"Alih kelola karena: {h.alasan_alih_kelola}.", **k2)
        sg = sta_by_pt.get(t.kode_pt)
        if sg is None:
            add("PT-05", "Kuning", uraian="PT belum memiliki data statuta.", **kw)
        else:
            s = sg.iloc[-1]
            if s.yayasan_berwenang_akademik == "Ya":
                add("PT-06", "Kuning", uraian="Statuta memberi yayasan kewenangan akademik.", dasar=s.versi_statuta, **kw)
            ds = [d for d in ad_dates.get(t.id_yayasan, []) if d > s.tgl_berlaku]
            if ds:
                add("PT-07", "Kuning", uraian=f"Statuta ({s.versi_statuta}) lebih lama dari perubahan AD yayasan "
                    f"tanggal {max(ds):%d-%m-%Y}.", dasar=s.versi_statuta, **kw)
        if t.status_pt == "Aktif":
            pp = pim[(pim.kode_pt == t.kode_pt) & (pim.tgl_akhir.isna() | (pim.tgl_akhir > today))]
            if len(pp) == 0:
                add("PT-08", "Kuning", uraian="Tidak ada pimpinan PT yang sedang menjabat.", **kw)

    # ---------- aturan yayasan ----------
    for _, y in yy.iterrows():
        kw = dict(level="Yayasan", yid=y.id_yayasan, kpt=None, ref=f"{y.id_yayasan} - {y.nama_yayasan}")
        if y.status_yayasan != "Aktif":
            add("YAY-01", "Kuning", uraian=f"Status yayasan: {y.status_yayasan}.", **kw)
        og = organ[(organ.id_yayasan == y.id_yayasan) & (organ.tgl_akhir.isna() | (organ.tgl_akhir > today))]
        n_ketua = (og.jabatan_yayasan == "Ketua Pengurus").sum()
        if n_ketua > 1:
            add("YAY-02", "Merah", uraian=f"Terdapat {n_ketua} Ketua Pengurus yang berjalan bersamaan.", **kw)
        else:
            hilang = [j for j in ("Pembina", "Ketua Pengurus", "Pengawas") if j not in set(og.jabatan_yayasan)]
            if hilang:
                add("YAY-02", "Kuning", uraian="Organ berjalan tidak lengkap: " + ", ".join(hilang) + ".", **kw)
        ap = akta[(akta.id_yayasan == y.id_yayasan) & (akta.jenis_perubahan == "Pendirian")]
        if len(ap) and str(ap.iloc[0].no_sk_kemenkum).strip() != str(y.no_sk_badan_hukum).strip():
            add("YAY-03", "Kuning", uraian="No. SK badan hukum berbeda dengan SK pada akta pendirian.", **kw)

    cols = ["tingkat", "kode_aturan", "level", "id_yayasan", "kode_pt", "referensi", "uraian", "dasar", "aktif"]
    fd = pd.DataFrame(F, columns=cols)
    if not include_historis:
        fd = fd[fd.aktif]

    def agg(df, key, master, idcol, namecol, tipe):
        out = []
        for _, m in master.iterrows():
            g = df[df[key] == m[idcol]]
            nm, nk = (g.tingkat == "Merah").sum(), (g.tingkat == "Kuning").sum()
            st = "Merah" if nm else "Kuning" if nk else "Hijau"
            top = g.sort_values("tingkat", key=lambda c: c.map(RANK), ascending=False).head(1)
            out.append(dict(tipe=tipe, id=m[idcol], nama=m[namecol], status=st, n_merah=int(nm), n_kuning=int(nk),
                            alasan_utama=(top.iloc[0].kode_aturan + ": " + top.iloc[0].uraian) if len(top) else "Semua aturan lolos"))
        return out

    st_y = pd.DataFrame(agg(fd, "id_yayasan", yy, "id_yayasan", "nama_yayasan", "Yayasan"))
    st_p = pd.DataFrame(agg(fd, "kode_pt", pt, "kode_pt", "nama_pt", "PT"))
    st_y = st_y.merge(yy[["id_yayasan", "kota", "provinsi"]], left_on="id", right_on="id_yayasan").drop(columns="id_yayasan")
    st_p = st_p.merge(pt[["kode_pt", "id_yayasan", "jenis_pt"]], left_on="id", right_on="kode_pt").drop(columns="kode_pt")
    return fd, st_y, st_p
