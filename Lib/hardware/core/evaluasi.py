"""
Evaluasi kuantitatif sistem rekomendasi rakitan PC.

Bagian A – Validitas rakitan (otomatis, tanpa label):
    Sistem dijalankan di banyak skenario (kebutuhan × budget), lalu dicek apakah hasilnya
    kompatibel, masuk budget, dan memenuhi syarat kebutuhan.

Bagian B – Relevansi ranking (butuh label manusia):
    Untuk tiap kebutuhan × kategori, 5 produk teratas sistem dan 5 produk teratas baseline
    (skor tanpa TF-IDF) dikumpulkan (metode pooling). Penilai memberi label 0/1/2 tanpa tahu
    asal produknya. Dari label itu dihitung Precision@5 dan nDCG@5.
"""
import math
import os
import time

from .rakit_pc import (
    PROFIL_KEBUTUHAN, ATURAN_WAJIB, KEBUTUHAN_DARI_FORM,
    hitung_skor_akhir, rekomendasi_rakitan, kapasitas_produk, skor_tfidf,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABEL_PATH = os.path.join(BASE_DIR, "data", "label_relevansi.xlsx")

SKENARIO_BUDGET = [5_000_000, 7_500_000, 10_000_000, 15_000_000, 20_000_000, 30_000_000]
K = 5                                   # Precision@K dan nDCG@K
NAMA_KEBUTUHAN = {v: k for k, v in KEBUTUHAN_DARI_FORM.items()}   # "gaming" → "Gaming"


def persen(a, b):
    return round(a / b * 100, 1) if b else 0.0


# ===================== A. VALIDITAS RAKITAN =====================

def cek_syarat(hasil):
    """True kalau rakitan memenuhi syarat wajib kebutuhannya (RAM, SSD, porsi GPU)."""
    aturan = ATURAN_WAJIB[hasil["kebutuhan"]]
    k = hasil["komponen"]
    return (
        kapasitas_produk(k["RAM"]) >= aturan["ram_min_gb"]
        and k["Storage"].get("component_type") == "ssd"
        and kapasitas_produk(k["Storage"]) >= aturan["ssd_min_gb"]
        and k["GPU"]["price"] >= aturan["porsi_gpu_min"] * hasil["budget"]
    )


def evaluasi_validitas(data):
    """Jalankan semua skenario. Hasil: ringkasan metrik + rincian per skenario."""
    baris = []
    for kebutuhan in PROFIL_KEBUTUHAN:
        for budget in SKENARIO_BUDGET:
            mulai = time.perf_counter()
            hasil = rekomendasi_rakitan(data, budget, kebutuhan)
            durasi = time.perf_counter() - mulai

            if not hasil:
                baris.append({"kebutuhan": NAMA_KEBUTUHAN[kebutuhan], "budget": budget,
                              "berhasil": False, "durasi": durasi})
                continue

            k = hasil["komponen"]
            cos_terpilih = sum(p["skor_tfidf"] for p in k.values()) / len(k)
            cos_kategori = sum(
                sum(p["skor_tfidf"] for p in data[kat]) / len(data[kat]) for kat in k
            ) / len(k)

            baris.append({
                "kebutuhan": NAMA_KEBUTUHAN[kebutuhan],
                "budget": budget,
                "berhasil": True,
                "socket_ok": k["CPU"]["socket"] == k["Motherboard"]["socket"],
                "ddr_ok": k["RAM"]["ddr"] == k["Motherboard"]["ddr"],
                "budget_ok": hasil["total"] <= budget,
                "syarat_ok": cek_syarat(hasil),
                "dilonggarkan": bool(hasil.get("catatan")),
                "utilisasi": hasil["total"] / budget,
                "cos_terpilih": cos_terpilih,
                "cos_kategori": cos_kategori,
                "total": hasil["total"],
                "durasi": durasi,
            })

    berhasil = [b for b in baris if b["berhasil"]]
    n, nb = len(baris), len(berhasil)

    # Cakupan kosakata: berapa kata profil yang benar-benar ada di data
    total_kata, kata_dikenal = 0, 0
    for kebutuhan, profil in PROFIL_KEBUTUHAN.items():
        for kategori, teks in profil.items():
            tak_dikenal = skor_tfidf(data[kategori], teks)
            jumlah = len(teks.split())
            total_kata += jumlah
            kata_dikenal += jumlah - len(tak_dikenal)

    rata = lambda kunci: sum(b[kunci] for b in berhasil) / nb if nb else 0
    ringkasan = {
        "n_skenario": n,
        "n_berhasil": nb,
        "berhasil_pct": persen(nb, n),
        "socket_pct": persen(sum(b["socket_ok"] for b in berhasil), nb),
        "ddr_pct": persen(sum(b["ddr_ok"] for b in berhasil), nb),
        "budget_pct": persen(sum(b["budget_ok"] for b in berhasil), nb),
        "syarat_pct": persen(sum(b["syarat_ok"] for b in berhasil), nb),
        "dilonggarkan": sum(b["dilonggarkan"] for b in berhasil),
        "utilisasi_pct": round(rata("utilisasi") * 100, 1),
        "cos_terpilih": rata("cos_terpilih"),
        "cos_kategori": rata("cos_kategori"),
        "lift": rata("cos_terpilih") / rata("cos_kategori") if nb and rata("cos_kategori") else 0,
        "durasi_rata": sum(b["durasi"] for b in baris) / n if n else 0,
        "cakupan_kata_pct": persen(kata_dikenal, total_kata),
        "kata_dikenal": kata_dikenal,
        "total_kata": total_kata,
    }
    return {"ringkasan": ringkasan, "baris": baris}


# ===================== B. RELEVANSI RANKING (POOLING + LABEL) =====================

def skor_baseline(p):
    """Baseline tanpa TF-IDF: bobot harga & ulasan dibagi ulang secara proporsional (0.3:0.2 → 0.6:0.4)."""
    return 0.6 * p["harga_n"] + 0.4 * p["ulasan_n"]


def ranking_per_kelompok(data):
    """Top-K sistem dan top-K baseline untuk tiap kebutuhan × kategori (dalam bentuk id)."""
    hasil = {}
    for kebutuhan, profil in PROFIL_KEBUTUHAN.items():
        for kategori, daftar in data.items():
            hitung_skor_akhir(daftar, profil[kategori])
            sistem = sorted(daftar, key=lambda p: -p["skor"])[:K]
            baseline = sorted(daftar, key=lambda p: -skor_baseline(p))[:K]
            hasil[(kebutuhan, kategori)] = {
                "sistem": [p["id"] for p in sistem],
                "baseline": [p["id"] for p in baseline],
                "produk": {p["id"]: p for p in sistem + baseline},
            }
    return hasil


def lembar_label(data):
    """Baris untuk lembar penilaian. Urutan diacak per kelompok supaya penilai tidak tahu asal produk."""
    import random
    acak = random.Random(42)                       # seed tetap → lembar selalu sama
    baris = []
    for (kebutuhan, kategori), r in ranking_per_kelompok(data).items():
        produk = list(r["produk"].values())
        acak.shuffle(produk)
        for p in produk:
            baris.append({
                "kebutuhan": NAMA_KEBUTUHAN[kebutuhan],
                "kategori": kategori,
                "id": p["id"],
                "nama": p["name"],
                "harga": p["price"],
                "url": p.get("url") or "",
            })
    return baris


def baca_label(path=LABEL_PATH):
    """Baca file label → {(kebutuhan, kategori, id): label}. None kalau file belum ada."""
    if not os.path.exists(path):
        return None
    from openpyxl import load_workbook
    ws = load_workbook(path, read_only=True, data_only=True)["Label"]
    baris = ws.iter_rows(values_only=True)
    header = [str(h).strip().lower() if h is not None else "" for h in next(baris)]
    i_keb, i_kat, i_id, i_label = (header.index(x) for x in ("kebutuhan", "kategori", "id", "label"))

    label = {}
    for r in baris:
        nilai = r[i_label]
        if nilai in (None, ""):
            continue
        try:
            nilai = int(nilai)
        except (TypeError, ValueError):
            continue
        if nilai in (0, 1, 2):
            kebutuhan = KEBUTUHAN_DARI_FORM.get(str(r[i_keb]).strip())
            label[(kebutuhan, str(r[i_kat]).strip(), int(r[i_id]))] = nilai
    return label


def precision_at_k(daftar_label):
    return sum(1 for l in daftar_label[:K] if l >= 1) / K


def dcg(daftar_label):
    return sum((2 ** l - 1) / math.log2(i + 2) for i, l in enumerate(daftar_label[:K]))


def ndcg_at_k(daftar_label, semua_label_kelompok):
    ideal = dcg(sorted(semua_label_kelompok, reverse=True))
    return dcg(daftar_label) / ideal if ideal else 0.0


def evaluasi_relevansi(data, path=LABEL_PATH):
    """Hitung P@K dan nDCG@K sistem vs baseline. None kalau label belum ada."""
    label = baca_label(path)
    if label is None:
        return None

    ranking = ranking_per_kelompok(data)
    per_kelompok = []
    for (kebutuhan, kategori), r in ranking.items():
        ambil = lambda ids: [label.get((kebutuhan, kategori, i)) for i in ids]
        l_sistem, l_baseline = ambil(r["sistem"]), ambil(r["baseline"])
        if None in l_sistem or None in l_baseline:       # kelompok belum dilabel lengkap → dilewati
            continue
        semua = [label[(kebutuhan, kategori, i)] for i in r["produk"]]
        per_kelompok.append({
            "kebutuhan": NAMA_KEBUTUHAN[kebutuhan],
            "kategori": kategori,
            "p_sistem": precision_at_k(l_sistem),
            "p_baseline": precision_at_k(l_baseline),
            "ndcg_sistem": ndcg_at_k(l_sistem, semua),
            "ndcg_baseline": ndcg_at_k(l_baseline, semua),
        })

    n = len(per_kelompok)
    rata = lambda kunci: sum(x[kunci] for x in per_kelompok) / n if n else 0
    return {
        "n_kelompok": n,
        "total_kelompok": len(ranking),
        "n_label": len(label),
        "p_sistem": rata("p_sistem"),
        "p_baseline": rata("p_baseline"),
        "ndcg_sistem": rata("ndcg_sistem"),
        "ndcg_baseline": rata("ndcg_baseline"),
        "per_kelompok": per_kelompok,
    }


if __name__ == "__main__":
    from .rakit_pc import siapkan_data

    data = siapkan_data()
    v = evaluasi_validitas(data)["ringkasan"]
    for kunci, nilai in v.items():
        print(f"{kunci:<18} {nilai}")

    r = evaluasi_relevansi(data)
    print("\nRelevansi:", "label belum ada" if r is None else
          {k: v for k, v in r.items() if k != "per_kelompok"})