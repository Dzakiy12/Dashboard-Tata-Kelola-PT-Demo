"""Penyimpanan SQLite, validasi, pembaruan data, dan log audit."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
from schema import TABLES, ORDER, FKS, REQUIRED

BASE = Path(__file__).parent
DB_PATH = BASE / "ews.db"
SEED = BASE / "Contoh_Data_50_Yayasan.xlsx"


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _clean(name, df):
    meta = TABLES[name]
    df = df.copy()
    df = df[~df[meta["pk"]].astype(str).str.startswith("CONTOH") & df[meta["pk"]].notna()]
    for c in meta["dates"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in meta["ints"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round().astype("Int64")
    if "nik" in df.columns:
        df["nik"] = df["nik"].map(lambda x: None if pd.isna(x) or str(x).strip() == "" else
                                  (str(int(x)) if isinstance(x, (int, float)) else str(x).strip()))
    df = df.astype(object).where(df.notna(), None)
    return df.reset_index(drop=True)


def _to_sql(name, df, c):
    out = df.copy()
    for col in TABLES[name]["dates"]:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.astype(object).where(out.notna(), None)
    out.to_sql(name, c, if_exists="replace", index=False)


def init_db(force=False):
    if DB_PATH.exists() and not force:
        return
    if DB_PATH.exists():
        DB_PATH.unlink()
    sheets = pd.read_excel(SEED, sheet_name=None)
    c = conn()
    for t in ORDER:
        _to_sql(t, _clean(t, sheets[t]), c)
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT, pengguna TEXT,
                 tabel TEXT, kunci TEXT, aksi TEXT, kolom TEXT, nilai_lama TEXT, nilai_baru TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS riwayat_status(id INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT, tipe TEXT,
                 id_entitas TEXT, nama TEXT, dari TEXT, ke TEXT, pemicu TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS status_terakhir(tipe TEXT, id_entitas TEXT, status TEXT, PRIMARY KEY(tipe,id_entitas))")
    c.commit()
    c.close()


def load_table(name):
    c = conn()
    df = pd.read_sql(f"SELECT * FROM {name}", c)
    c.close()
    meta = TABLES[name]
    for col in meta["dates"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in meta["ints"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").round().astype("Int64")
    if "nik" in df.columns:
        df["nik"] = df["nik"].astype(object).where(df["nik"].notna(), None)
        df["nik"] = df["nik"].map(lambda x: None if x is None else str(x).split(".")[0])
    return df


def load_all():
    return {t: load_table(t) for t in ORDER}


def read_log(name, limit=500):
    c = conn()
    df = pd.read_sql(f"SELECT * FROM {name} ORDER BY id DESC LIMIT {limit}", c)
    c.close()
    return df


# ---------- util ----------
def norm(x):
    if x is None or (not isinstance(x, str) and pd.isna(x)):
        return None
    if isinstance(x, pd.Timestamp):
        return x.strftime("%Y-%m-%d")
    if hasattr(x, "isoformat") and not isinstance(x, str):
        return x.isoformat()[:10]
    if isinstance(x, float) and x == int(x):
        return int(x)
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, str):
        x = x.strip()
        return x or None
    return x


def next_id(name, existing):
    m = TABLES[name]
    nums = [int(s[len(m["prefix"]):]) for s in map(str, existing) if s.startswith(m["prefix"]) and s[len(m["prefix"]):].isdigit()]
    return f"{m['prefix']}{(max(nums) + 1 if nums else 1):0{m['pad']}d}"


def fill_ids(name, new_df, full_df):
    pk = TABLES[name]["pk"]
    df = new_df.copy()
    used = list(full_df[pk]) + [x for x in df[pk] if norm(x)]
    for i in df.index:
        if not norm(df.at[i, pk]):
            nid = next_id(name, used)
            df.at[i, pk] = nid
            used.append(nid)
    return df


def validate(name, new_df, state, deleted_keys=()):
    """state = {tabel: DataFrame} kondisi data lain (induk) saat ini. Mengembalikan daftar pesan error."""
    meta, err = TABLES[name], []
    pk = meta["pk"]
    keys = [norm(k) for k in new_df[pk]]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        err.append(f"[{name}] ID ganda: {', '.join(sorted(map(str, dup)))}")
    for col in REQUIRED.get(name, []):
        if col in new_df.columns:
            bad = [norm(r[pk]) for _, r in new_df.iterrows() if norm(r[col]) is None]
            if bad:
                err.append(f"[{name}] Kolom wajib '{col}' kosong pada: {', '.join(map(str, bad[:5]))}")
    for col, parent in FKS.get(name, {}).items():
        if col in new_df.columns:
            valid = set(state[parent][TABLES[parent]["pk"]].map(norm))
            bad = [(norm(r[pk]), norm(r[col])) for _, r in new_df.iterrows() if norm(r[col]) and norm(r[col]) not in valid]
            if bad:
                err.append(f"[{name}] {col} tidak ditemukan di {parent}: " + ", ".join(f"{k}→{v}" for k, v in bad[:5]))
    if {"tgl_mulai", "tgl_akhir"} <= set(new_df.columns):
        bad = [norm(r[pk]) for _, r in new_df.iterrows()
               if pd.notna(r["tgl_mulai"]) and pd.notna(r["tgl_akhir"]) and r["tgl_akhir"] < r["tgl_mulai"]]
        if bad:
            err.append(f"[{name}] tgl_akhir lebih awal dari tgl_mulai pada: {', '.join(map(str, bad[:5]))}")
    # penghapusan yang masih dirujuk tabel anak
    for k in deleted_keys:
        for child, fk in FKS.items():
            for col, parent in fk.items():
                if parent == name and k in set(state[child][col].map(norm)):
                    err.append(f"[{name}] {k} tidak bisa dihapus: masih dipakai di tabel {child} ({col}).")
    return err


def apply_changes(name, old_view, new_view, user, allow_delete=True):
    """Terapkan selisih old_view -> new_view ke DB + tulis audit. Mengembalikan (tambah, ubah, hapus)."""
    pk = TABLES[name]["pk"]
    cols = list(old_view.columns)
    rec = lambda df: {norm(r[pk]): {c: norm(r[c]) for c in cols} for _, r in df.iterrows()}
    old, new = rec(old_view), rec(new_view)
    now = datetime.now().isoformat(timespec="seconds")
    c = conn()
    log = lambda *a: c.execute("INSERT INTO audit_log(waktu,pengguna,tabel,kunci,aksi,kolom,nilai_lama,nilai_baru) VALUES(?,?,?,?,?,?,?,?)",
                               (now, user, name, *a))
    n_add = n_upd = n_del = 0
    for k, r in new.items():
        if k not in old:
            c.execute(f"INSERT INTO {name}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [r[x] for x in cols])
            log(k, "TAMBAH", None, None, json.dumps(r, ensure_ascii=False, default=str))
            n_add += 1
        else:
            diff = [x for x in cols if str(r[x]) != str(old[k][x])]
            if diff:
                c.execute(f"UPDATE {name} SET {','.join(x + '=?' for x in diff)} WHERE {pk}=?", [r[x] for x in diff] + [k])
                for x in diff:
                    log(k, "UBAH", x, None if old[k][x] is None else str(old[k][x]), None if r[x] is None else str(r[x]))
                n_upd += 1
    if allow_delete:
        for k in set(old) - set(new):
            c.execute(f"DELETE FROM {name} WHERE {pk}=?", [k])
            log(k, "HAPUS", None, json.dumps(old[k], ensure_ascii=False, default=str), None)
            n_del += 1
    c.commit()
    c.close()
    return n_add, n_upd, n_del


def record_status(status_df, pemicu, now=None):
    """Bandingkan status baru dengan snapshot terakhir; catat yang berubah. Return DataFrame perubahan."""
    now = now or datetime.now().isoformat(timespec="seconds")
    c = conn()
    prev = {(r["tipe"], r["id_entitas"]): r["status"] for r in c.execute("SELECT * FROM status_terakhir")}
    changes = []
    for _, r in status_df.iterrows():
        key = (r["tipe"], r["id"])
        if prev and prev.get(key) != r["status"]:
            changes.append(dict(waktu=now, tipe=r["tipe"], id_entitas=r["id"], nama=r["nama"],
                                dari=prev.get(key, "(baru)"), ke=r["status"], pemicu=pemicu))
        c.execute("INSERT OR REPLACE INTO status_terakhir VALUES(?,?,?)", (r["tipe"], r["id"], r["status"]))
    for ch in changes:
        c.execute("INSERT INTO riwayat_status(waktu,tipe,id_entitas,nama,dari,ke,pemicu) VALUES(?,?,?,?,?,?,?)",
                  (ch["waktu"], ch["tipe"], ch["id_entitas"], ch["nama"], ch["dari"], ch["ke"], ch["pemicu"]))
    c.commit()
    c.close()
    return pd.DataFrame(changes)
