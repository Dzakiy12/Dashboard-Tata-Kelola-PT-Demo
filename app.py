"""Dashboard Early Warning System Yayasan & Perguruan Tinggi (Streamlit)."""
import io
import pandas as pd
import streamlit as st
import db
import rules
from schema import TABLES, ORDER, ENUMS, FKS

st.set_page_config(page_title="EWS Yayasan & PT", page_icon="🚦", layout="wide")
db.init_db()
EMO = {"Merah": "🔴", "Kuning": "🟡", "Hijau": "🟢"}
st.session_state.setdefault("ver", 0)

# ---------------- sidebar ----------------
st.sidebar.title("🚦 EWS Yayasan & PT")
page = st.sidebar.radio("Menu", ["Ringkasan", "Detail Yayasan", "Kelola Data", "Unggah Excel", "Log & Riwayat Status", "Aturan"])
user = st.sidebar.text_input("Nama pengguna (wajib untuk mengubah data)", key="user")
historis = st.sidebar.toggle("Hitung temuan historis", value=False,
                             help="Mati: status hanya dari pimpinan yang sedang menjabat dan kondisi saat ini. Hidup: semua riwayat ikut dihitung.")
st.sidebar.caption("Prototipe. Aturan perlu divalidasi ahli hukum. Tambahkan autentikasi sebelum dipakai bersama.")

data = db.load_all()
cfg = rules.load_cfg()
findings, st_y, st_p = rules.evaluate(data, cfg, include_historis=historis)


def after_save(pemicu):
    """Evaluasi ulang setelah perubahan, catat perubahan status."""
    d = db.load_all()
    _, sy, sp = rules.evaluate(d, rules.load_cfg(), include_historis=historis)
    ch = db.record_status(pd.concat([sy, sp]), pemicu)
    st.session_state["ver"] += 1
    return ch


def show_changes(ch):
    if ch is not None and len(ch):
        st.warning(f"{len(ch)} entitas berubah status akibat pembaruan ini:")
        ch = ch.assign(dari=ch.dari.map(lambda x: EMO.get(x, "") + " " + x), ke=ch.ke.map(lambda x: EMO.get(x, "") + " " + x))
        st.dataframe(ch[["tipe", "id_entitas", "nama", "dari", "ke"]], hide_index=True, width="stretch")


def with_emoji(df):
    df = df.copy()
    df["status"] = df["status"].map(lambda s: f"{EMO[s]} {s}")
    return df


# ---------------- Ringkasan ----------------
if page == "Ringkasan":
    st.title("Ringkasan Early Warning System")
    c = st.columns(6)
    for i, (lab, df) in enumerate([("Yayasan", st_y), ("Perguruan Tinggi", st_p)]):
        vc = df.status.value_counts()
        for j, s in enumerate(["Merah", "Kuning", "Hijau"]):
            c[i * 3 + j].metric(f"{EMO[s]} {lab}", int(vc.get(s, 0)))
    tab_y, tab_p, tab_f = st.tabs(["Yayasan", "Perguruan Tinggi", "Semua temuan"])
    with tab_y:
        f1, f2, f3 = st.columns(3)
        sel = f1.multiselect("Status", ["Merah", "Kuning", "Hijau"], default=["Merah", "Kuning", "Hijau"], key="fy")
        prov = f2.multiselect("Provinsi", sorted(st_y.provinsi.unique()), key="fp")
        q = f3.text_input("Cari nama/ID", key="fq")
        v = st_y[st_y.status.isin(sel)]
        if prov:
            v = v[v.provinsi.isin(prov)]
        if q:
            v = v[v.nama.str.contains(q, case=False) | v.id.str.contains(q, case=False)]
        v = v.sort_values("status", key=lambda s: s.map(rules.RANK), ascending=False)
        st.dataframe(with_emoji(v)[["status", "id", "nama", "kota", "provinsi", "n_merah", "n_kuning", "alasan_utama"]],
                     hide_index=True, width="stretch")
    with tab_p:
        sel = st.multiselect("Status", ["Merah", "Kuning", "Hijau"], default=["Merah", "Kuning", "Hijau"], key="fpt")
        v = st_p[st_p.status.isin(sel)].sort_values("status", key=lambda s: s.map(rules.RANK), ascending=False)
        st.dataframe(with_emoji(v)[["status", "id", "nama", "jenis_pt", "id_yayasan", "n_merah", "n_kuning", "alasan_utama"]],
                     hide_index=True, width="stretch")
    with tab_f:
        tf = st.multiselect("Tingkat", ["Merah", "Kuning"], default=["Merah", "Kuning"], key="ftf")
        rl = st.multiselect("Kode aturan", sorted(findings.kode_aturan.unique()), key="frl")
        v = findings[findings.tingkat.isin(tf)]
        if rl:
            v = v[v.kode_aturan.isin(rl)]
        st.caption(f"{len(v)} temuan")
        st.dataframe(v.assign(tingkat=v.tingkat.map(lambda s: f"{EMO[s]} {s}"))
                     [["tingkat", "kode_aturan", "id_yayasan", "referensi", "uraian", "dasar", "aktif"]],
                     hide_index=True, width="stretch")
        st.download_button("Unduh temuan (CSV)", v.to_csv(index=False).encode("utf-8-sig"), "temuan_ews.csv", "text/csv")

# ---------------- Detail Yayasan ----------------
elif page == "Detail Yayasan":
    st.title("Detail Yayasan")
    opts = dict(zip(st_y.id, st_y.id + " - " + st_y.nama))
    yid = st.selectbox("Pilih yayasan", list(opts), format_func=opts.get)
    row = st_y[st_y.id == yid].iloc[0]
    st.subheader(f"{EMO[row.status]} {row.status} - {row.nama}")
    st.caption(f"{row.kota}, {row.provinsi}")
    fy = findings[findings.id_yayasan == yid]
    if len(fy):
        st.dataframe(fy.assign(tingkat=fy.tingkat.map(lambda s: f"{EMO[s]} {s}"))
                     [["tingkat", "kode_aturan", "level", "referensi", "uraian", "dasar", "aktif"]],
                     hide_index=True, width="stretch")
    else:
        st.success("Tidak ada temuan. Semua aturan lolos.")
    st.markdown("**Perguruan tinggi di bawah yayasan ini**")
    sp = st_p[st_p.id_yayasan == yid]
    st.dataframe(with_emoji(sp)[["status", "id", "nama", "jenis_pt", "alasan_utama"]], hide_index=True, width="stretch")
    with st.expander("Akta"):
        st.dataframe(data["akta"][data["akta"].id_yayasan == yid], hide_index=True, width="stretch")
    with st.expander("Organ yayasan"):
        st.dataframe(data["organ_yayasan"][data["organ_yayasan"].id_yayasan == yid], hide_index=True, width="stretch")
    with st.expander("Pimpinan PT"):
        st.dataframe(data["pimpinan_pt"][data["pimpinan_pt"].id_yayasan == yid], hide_index=True, width="stretch")
    st.info("Untuk mengubah data, buka menu **Kelola Data** dan pilih yayasan ini pada filter.")

# ---------------- Kelola Data ----------------
elif page == "Kelola Data":
    st.title("Kelola Data")
    st.caption("Ubah sel langsung, tambah baris di bagian bawah tabel, atau hapus baris (pilih lalu tekan Delete). "
               "Kosongkan kolom ID pada baris baru agar ID dibuat otomatis. Status dihitung ulang setelah disimpan.")
    c1, c2 = st.columns([2, 2])
    tname = c1.selectbox("Tabel", ORDER, format_func=lambda t: TABLES[t]["label"])
    yopts = {"(semua yayasan)": None} | dict(zip(st_y.nama, st_y.id))
    ylab = c2.selectbox("Filter yayasan", list(yopts))
    yid = yopts[ylab]
    meta, full = TABLES[tname], data[tname]
    pks = meta["pk"]
    view = full
    if yid:
        pt_codes = set(data["pt"][data["pt"].id_yayasan == yid].kode_pt) | \
            set(data["riwayat_penyelenggara"][data["riwayat_penyelenggara"].id_yayasan == yid].kode_pt)
        if tname == "yayasan":
            view = full[full.id_yayasan == yid]
        elif "id_yayasan" in full.columns:
            view = full[full.id_yayasan == yid]
        elif "kode_pt" in full.columns:
            view = full[full.kode_pt.isin(pt_codes)]
        elif tname == "riwayat_perubahan":
            view = full[full.id_entitas.isin(pt_codes | {yid})]
    view = view.reset_index(drop=True)

    cc = {}
    for col in view.columns:
        if col in meta["dates"]:
            cc[col] = st.column_config.DateColumn(col, format="YYYY-MM-DD")
        elif col in meta["ints"]:
            cc[col] = st.column_config.NumberColumn(col, step=1)
        elif col in ENUMS:
            cc[col] = st.column_config.SelectboxColumn(col, options=ENUMS[col])
        elif col in FKS.get(tname, {}):
            parent = FKS[tname][col]
            cc[col] = st.column_config.SelectboxColumn(col, options=list(data[parent][TABLES[parent]["pk"]]))
    cc[pks] = st.column_config.TextColumn(pks, help="Kosongkan pada baris baru untuk ID otomatis")

    st.write(f"{len(view)} baris")
    edited = st.data_editor(view, num_rows="dynamic", column_config=cc, width="stretch", hide_index=True,
                            key=f"ed_{tname}_{yid}_{st.session_state['ver']}")
    if st.button("💾 Simpan perubahan", type="primary"):
        if not user.strip():
            st.error("Isi nama pengguna di sidebar terlebih dahulu.")
        else:
            new = db.fill_ids(tname, edited.reset_index(drop=True), full)
            old_keys = {db.norm(k) for k in view[pks]}
            new_keys = {db.norm(k) for k in new[pks]}
            deleted = old_keys - new_keys
            others = full[~full[pks].map(db.norm).isin(old_keys)]
            # ID baru tidak boleh bentrok dengan baris di luar filter
            clash = new_keys & set(others[pks].map(db.norm))
            state = dict(data)
            state[tname] = pd.concat([others, new], ignore_index=True)
            errs = db.validate(tname, new, state, deleted)
            if clash:
                errs.append(f"ID sudah dipakai di luar filter: {', '.join(sorted(map(str, clash)))}")
            if errs:
                st.error("Perubahan tidak disimpan:\n\n" + "\n\n".join("- " + e for e in errs))
            else:
                a, u, h = db.apply_changes(tname, view, new, user.strip())
                if a + u + h == 0:
                    st.info("Tidak ada perubahan.")
                else:
                    ch = after_save(f"{tname}: +{a} ~{u} -{h} oleh {user.strip()}")
                    st.success(f"Tersimpan: {a} ditambah, {u} diubah, {h} dihapus.")
                    show_changes(ch)
                    st.button("Muat ulang tabel")

# ---------------- Unggah Excel ----------------
elif page == "Unggah Excel":
    st.title("Unggah Excel (tambah / perbarui massal)")
    st.caption("Gunakan format yang sama dengan file contoh (nama sheet = nama tabel). Baris dengan ID yang sudah ada akan "
               "diperbarui, ID baru ditambahkan. Tidak ada baris yang dihapus. Semua perubahan dicatat di log.")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        for t in ORDER:
            data[t].to_excel(w, sheet_name=t, index=False)
    st.download_button("Unduh data saat ini (Excel)", buf.getvalue(), "data_ews_saat_ini.xlsx")
    up = st.file_uploader("File .xlsx", type=["xlsx"])
    if up:
        sheets = pd.read_excel(up, sheet_name=None)
        state, plan, errs = dict(data), {}, []
        for t in ORDER:
            if t not in sheets:
                continue
            raw = sheets[t]
            miss = [c for c in data[t].columns if c not in raw.columns and c == TABLES[t]["pk"]]
            if miss:
                errs.append(f"[{t}] kolom kunci {miss[0]} tidak ada.")
                continue
            up_df = db._clean(t, raw)
            for c in data[t].columns:
                if c not in up_df.columns:
                    up_df[c] = None
            up_df = up_df[list(data[t].columns)]
            up_df = db.fill_ids(t, up_df, state[t])
            pkn = TABLES[t]["pk"]
            keep = state[t][~state[t][pkn].map(db.norm).isin(set(up_df[pkn].map(db.norm)))]
            merged = pd.concat([keep, up_df], ignore_index=True)
            errs += db.validate(t, up_df, {**state, t: merged})
            plan[t] = (data[t], merged)
            state[t] = merged
        if errs:
            st.error("Unggahan ditolak:\n\n" + "\n\n".join("- " + e for e in errs[:30]))
        elif not plan:
            st.warning("Tidak ada sheet yang namanya cocok dengan tabel.")
        else:
            rows = []
            for t, (old, new) in plan.items():
                ok = {db.norm(r[TABLES[t]["pk"]]): {c: db.norm(r[c]) for c in old.columns} for _, r in old.iterrows()}
                a = u = 0
                for _, r in new.iterrows():
                    k = db.norm(r[TABLES[t]["pk"]])
                    if k not in ok:
                        a += 1
                    elif any(str(db.norm(r[c])) != str(ok[k][c]) for c in old.columns):
                        u += 1
                rows.append(dict(tabel=t, ditambah=a, diubah=u))
            st.dataframe(pd.DataFrame(rows), hide_index=True)
            if st.button("Terapkan", type="primary"):
                if not user.strip():
                    st.error("Isi nama pengguna di sidebar terlebih dahulu.")
                else:
                    tot = 0
                    for t, (old, new) in plan.items():
                        a, u, _ = db.apply_changes(t, old, new, user.strip(), allow_delete=False)
                        tot += a + u
                    ch = after_save(f"unggah Excel ({tot} baris) oleh {user.strip()}")
                    st.success(f"Selesai: {tot} baris ditambah/diperbarui.")
                    show_changes(ch)

# ---------------- Log ----------------
elif page == "Log & Riwayat Status":
    st.title("Log perubahan data dan riwayat status")
    t1, t2 = st.tabs(["Perubahan status (peringatan)", "Log audit data"])
    with t1:
        h = db.read_log("riwayat_status")
        if len(h):
            h = h.assign(dari=h.dari.map(lambda x: EMO.get(x, "") + " " + x), ke=h.ke.map(lambda x: EMO.get(x, "") + " " + x))
            st.dataframe(h.drop(columns="id"), hide_index=True, width="stretch")
        else:
            st.info("Belum ada perubahan status. Akan tercatat setelah data diperbarui.")
    with t2:
        a = db.read_log("audit_log")
        st.dataframe(a.drop(columns="id"), hide_index=True, width="stretch") if len(a) else st.info("Belum ada perubahan data.")

# ---------------- Aturan ----------------
else:
    st.title("Aturan dan parameter")
    st.caption("Aturan di bawah adalah usulan awal berdasarkan kolom data. Validasi dengan ahli hukum sebelum dipakai.")
    rdf = pd.DataFrame([dict(kode=k, aktif=cfg["aktif"].get(k, True), nama=v[0], uraian=v[1]) for k, v in rules.RULES.items()])
    ed = st.data_editor(rdf, hide_index=True, width="stretch", disabled=["kode", "nama", "uraian"], key="rules_ed")
    p = cfg["parameter"]
    c = st.columns(3)
    p["toleransi_hari_masa_jabatan"] = c[0].number_input("Toleransi masa jabatan (hari)", 0, 365, int(p["toleransi_hari_masa_jabatan"]))
    p["batas_bulan_plt_pj"] = c[1].number_input("Batas Plt/Pj (bulan)", 1, 36, int(p["batas_bulan_plt_pj"]))
    p["jendela_bulan_pasca_perubahan_ad"] = c[2].number_input("Jendela pasca perubahan AD (bulan)", 1, 60, int(p["jendela_bulan_pasca_perubahan_ad"]))
    if st.button("Simpan aturan", type="primary"):
        cfg["aktif"] = {r.kode: bool(r.aktif) for r in ed.itertuples()}
        rules.save_cfg(cfg)
        ch = after_save("perubahan konfigurasi aturan")
        st.success("Tersimpan.")
        show_changes(ch)
