from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from .models import Produk
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from scrapper_app.scrape_tokopedia import scrape_query,scrape_for_django
import json
import os
from django.conf import settings
import subprocess
from django.shortcuts import render
import sys
import urllib.parse
import threading
from .rakit_pc import (
    siapkan_data, rekomendasi_rakitan, KEBUTUHAN_DARI_FORM, PROFIL_KEBUTUHAN, BOBOT_SKOR,
    rincian_tfidf, pembanding_heatmap,
)
from .evaluasi import evaluasi_validitas, evaluasi_relevansi, lembar_label, LABEL_PATH, K as K_EVALUASI
from datetime import datetime

# ===== Data rakitan: dimuat sekali, dipakai berulang =====
_DATA_RAKITAN = None
KUNCI_RAKITAN = threading.Lock()


def ambil_data_rakitan():
    """Muat data komponen sekali saja (request pertama), lalu simpan di memori."""
    global _DATA_RAKITAN
    if _DATA_RAKITAN is None:
        print("⏳ Memuat data komponen untuk rakitan PC...")
        _DATA_RAKITAN = siapkan_data()
        print("✅ Data rakitan siap")
    return _DATA_RAKITAN


# ===== Evaluasi: dihitung sekali, relevansi dihitung ulang kalau file label berubah =====
_EVALUASI = {"validitas": None, "relevansi": None, "label_mtime": None}


def ambil_evaluasi(data):
    """Wajib dipanggil di dalam KUNCI_RAKITAN, karena evaluasi ikut menghitung ulang skor produk."""
    if _EVALUASI["validitas"] is None:
        print("⏳ Menjalankan evaluasi validitas rakitan...")
        _EVALUASI["validitas"] = evaluasi_validitas(data)
        print("✅ Evaluasi validitas selesai")

    mtime = os.path.getmtime(LABEL_PATH) if os.path.exists(LABEL_PATH) else None
    if mtime != _EVALUASI["label_mtime"]:
        _EVALUASI["relevansi"] = evaluasi_relevansi(data) if mtime else None
        _EVALUASI["label_mtime"] = mtime
    return _EVALUASI

# ===== Bantuan tampilan halaman hasil rakitan =====
LABEL_KATEGORI = {
    "CPU": "CPU", "Motherboard": "Motherboard", "RAM": "RAM",
    "GPU": "GPU", "Storage": "Penyimpanan",
}
WARNA_KATEGORI = {
    "CPU": "bg-blue-500", "Motherboard": "bg-amber-500", "RAM": "bg-violet-500",
    "GPU": "bg-emerald-500", "Storage": "bg-rose-500",
}
NAMA_BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def format_rupiah(angka):
    """10000000 → 'Rp 10.000.000'"""
    return "Rp " + f"{int(angka):,}".replace(",", ".")


def format_tanggal(iso_teks):
    """'2026-02-02T10:15:00' → '2 Februari 2026'"""
    try:
        t = datetime.fromisoformat(iso_teks)
    except (TypeError, ValueError):
        return ""
    return f"{t.day} {NAMA_BULAN[t.month - 1]} {t.year}"


def angka(x, desimal=4):
    """0.406612 → '0.4066' (titik desimal, biar sama dengan rumus)."""
    return f"{x:.{desimal}f}"


def siapkan_tampilan(hasil, budget_int):
    """Ubah hasil rakitan jadi data yang siap ditampilkan template."""
    komponen = []
    for kategori, p in hasil["komponen"].items():
        lokal = (p.get("local_image") or "").replace("\\", "/")
        komponen.append({
            "kategori": kategori,
            "label": LABEL_KATEGORI[kategori],
            "warna": WARNA_KATEGORI[kategori],
            "produk": p,
            "harga_str": format_rupiah(p["price"]),
            "persen": round(p["price"] / budget_int * 100),
            "gambar": p.get("image_url") or "",
            "gambar_cadangan": "/local-image/?filename=" + urllib.parse.quote(os.path.basename(lokal)) if lokal else "",
            "link_cari": "https://www.tokopedia.com/search?st=product&q=" + urllib.parse.quote_plus(p["name"][:80]),
            # Angka disalin sekarang (masih di dalam kunci), karena data produk dipakai bareng semua request
            "cosine": angka(p["skor_tfidf"]),
            "skor": angka(p["skor"]),
            "tfidf_n": angka(p["tfidf_n"]),
            "harga_n": angka(p["harga_n"]),
            "ulasan_n": angka(p["ulasan_n"]),
            "porsi_tfidf": angka(BOBOT_SKOR["tfidf"] * p["tfidf_n"]),
            "porsi_harga": angka(BOBOT_SKOR["harga"] * p["harga_n"]),
            "porsi_ulasan": angka(BOBOT_SKOR["ulasan"] * p["ulasan_n"]),
            "nilai_cosine": p["skor_tfidf"],
            "nilai_skor": p["skor"],
        })

    tanggal = [p["last_updated"] for p in hasil["komponen"].values() if p.get("last_updated")]
    tanggal_data = format_tanggal(min(tanggal)) if tanggal else ""
    return komponen, tanggal_data

def siapkan_rincian(hasil, data, budget_int):
    """Tabel perhitungan TF-IDF dan heatmap untuk 5 komponen terpilih."""
    profil = PROFIL_KEBUTUHAN[hasil["kebutuhan"]]
    tabel_tfidf, heatmap = [], []

    for kategori, terpilih in hasil["komponen"].items():
        batas_harga = terpilih["price"] + hasil["sisa"]          # harga maksimal pengganti tanpa lewat budget
        daftar_produk = pembanding_heatmap(kategori, data[kategori], terpilih, batas_harga)
        r = rincian_tfidf(data[kategori], profil[kategori], daftar_produk)
        utama = r["baris"][0]                                   # produk terpilih

        baris_kata = []
        for k in r["kata"]:
            kata = k["kata"]
            baris_kata.append({
                "kata": kata,
                "tf": utama["tf"][kata],
                "df": k["df"],
                "idf": angka(k["idf"]),
                "wq": angka(k["bobot_profil"]),
                "wd": angka(utama["bobot"][kata]),
                "kontribusi": angka(utama["kontribusi"][kata]),
                "aktif": utama["tf"][kata] > 0,
            })
        penyumbang = sorted(
            ((kata, nilai) for kata, nilai in utama["kontribusi"].items() if nilai > 0),
            key=lambda x: -x[1],
        )
        tabel_tfidf.append({
            "kategori": kategori,
            "label": LABEL_KATEGORI[kategori],
            "nama": terpilih["name"],
            "teks_nama": utama["teks"],
            "teks_profil": r["teks_profil"],
            "n_dokumen": r["n_dokumen"],
            "kata_tak_dikenal": r["kata_tak_dikenal"],
            "baris": baris_kata,
            "n_cocok": sum(1 for b in baris_kata if b["aktif"]),
            "cosine": angka(utama["cosine"]),
            "penyumbang": [{"kata": k, "nilai": angka(v)} for k, v in penyumbang[:3]],
        })

        # Heatmap: warna = bobot TF-IDF relatif terhadap bobot terbesar di tabel kategori ini
        terbesar = max((b for baris in r["baris"] for b in baris["bobot"].values()), default=0)
        baris_heatmap = []
        for baris in r["baris"]:
            sel = []
            for k in r["kata"]:
                nilai = baris["bobot"][k["kata"]]
                alpha = (0.12 + 0.88 * nilai / terbesar) if nilai > 0 and terbesar else 0
                sel.append({"nilai": angka(nilai, 2), "alpha": round(alpha, 3), "gelap": alpha > 0.55})
            baris_heatmap.append({
                "nama": baris["produk"]["name"],
                "harga_str": format_rupiah(baris["produk"]["price"]),
                "terpilih": baris["produk"] is terpilih,
                "sel": sel,
                "cosine": angka(baris["cosine"]),
                "skor": angka(baris["produk"]["skor"]),
            })
        heatmap.append({
            "label": LABEL_KATEGORI[kategori],
            "kata": [k["kata"] for k in r["kata"]],
            "baris": baris_heatmap,
        })

    return tabel_tfidf, heatmap


def siapkan_evaluasi(evaluasi):
    """Format angka evaluasi untuk template."""
    v = evaluasi["validitas"]
    ringkasan = dict(v["ringkasan"])
    ringkasan["cos_terpilih"] = angka(ringkasan["cos_terpilih"])
    ringkasan["cos_kategori"] = angka(ringkasan["cos_kategori"])
    ringkasan["lift"] = angka(ringkasan["lift"], 2)
    ringkasan["durasi_rata"] = angka(ringkasan["durasi_rata"], 2)

    baris = []
    for b in v["baris"]:
        baris.append({
            "kebutuhan": b["kebutuhan"],
            "budget_str": format_rupiah(b["budget"]),
            "berhasil": b["berhasil"],
            "total_str": format_rupiah(b["total"]) if b["berhasil"] else "-",
            "utilisasi": f"{b['utilisasi'] * 100:.1f}%" if b["berhasil"] else "-",
            "socket_ok": b.get("socket_ok"),
            "ddr_ok": b.get("ddr_ok"),
            "budget_ok": b.get("budget_ok"),
            "syarat_ok": b.get("syarat_ok"),
            "dilonggarkan": b.get("dilonggarkan"),
            "cos_terpilih": angka(b["cos_terpilih"]) if b["berhasil"] else "-",
        })

    relevansi = None
    r = evaluasi["relevansi"]
    if r is not None:
        relevansi = {
            "n_kelompok": r["n_kelompok"],
            "total_kelompok": r["total_kelompok"],
            "n_label": r["n_label"],
            "p_sistem": angka(r["p_sistem"]),
            "p_baseline": angka(r["p_baseline"]),
            "ndcg_sistem": angka(r["ndcg_sistem"]),
            "ndcg_baseline": angka(r["ndcg_baseline"]),
            "per_kelompok": [{
                "kebutuhan": x["kebutuhan"],
                "kategori": LABEL_KATEGORI[x["kategori"]],
                "p_sistem": angka(x["p_sistem"], 2),
                "p_baseline": angka(x["p_baseline"], 2),
                "ndcg_sistem": angka(x["ndcg_sistem"], 3),
                "ndcg_baseline": angka(x["ndcg_baseline"], 3),
            } for x in r["per_kelompok"]],
        }
    return {"ringkasan": ringkasan, "baris": baris, "relevansi": relevansi, "k": K_EVALUASI}


def baca_input_rakitan(request):
    """Ambil budget & kebutuhan dari POST (lalu simpan ke session) atau dari session."""
    if request.method == "POST":
        # Form baru pakai "budget"; form lama (min/max) tetap jalan, yang dipakai max_budget
        budget = request.POST.get("budget") or request.POST.get("max_budget", "")
        usage = request.POST.get("usage", "")
        request.session["pc_search_data"] = {"budget": budget, "usage": usage}
    else:
        sesi = request.session.get("pc_search_data", {})
        budget = sesi.get("budget", "")
        usage = sesi.get("usage", "")

    try:
        budget_int = int(str(budget).replace(".", "").replace(",", "").strip()) if budget else 0
    except ValueError:
        budget_int = 0
    return budget, budget_int, usage


def hitung_rakitan(budget_int, kebutuhan, dengan_evaluasi=True):
    """
    Semua perhitungan + penyalinan angka dilakukan di dalam kunci,
    supaya angka yang tampil tidak ketimpa request lain.
    """
    with KUNCI_RAKITAN:
        data = ambil_data_rakitan()
        evaluasi = siapkan_evaluasi(ambil_evaluasi(data)) if dengan_evaluasi else None
        hasil = rekomendasi_rakitan(data, budget_int, kebutuhan)
        if not hasil:
            return None
        komponen, tanggal_data = siapkan_tampilan(hasil, budget_int)
        tabel_tfidf, heatmap = siapkan_rincian(hasil, data, budget_int)
    return {
        "hasil": hasil,
        "komponen": komponen,
        "tanggal_data": tanggal_data,
        "tabel_tfidf": tabel_tfidf,
        "heatmap": heatmap,
        "evaluasi": evaluasi,
    }


def home(request):
    return render(request, "index.html")


def processor(request):
    # ambil hanya produk yang kegunaannya Processor
    produk_list = Produk.objects.filter(kegunaan="Processor")

    context = {"produk_list": produk_list}
    return render(request, "processor.html", context)


def processor_detail(request, slug):
    produk = get_object_or_404(Produk, slug=slug)
    return render(request, "details/processor/index.html", {"produk": produk})


def ram(request):
    return render(request, "ram.html")


def vga(request):
    return render(request, "vga.html")


def psu(request):
    return render(request, "psu.html")


def ssd(request):
    return render(request, "ssd.html")

def load_tokopedia_data(product_type="all"):
    """
    Load data dari file JSON di folder data
    product_type: 'pc_component', 'laptop', atau 'all'
    """
    try:
        # Path ke file JSON - sesuaikan dengan struktur project
        json_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'tokopedia_products_latest.json')
        json_path = os.path.abspath(json_path)
        
        print(f"📂 Loading data from: {json_path}")
        
        if not os.path.exists(json_path):
            print("❌ File JSON tidak ditemukan")
            return []
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both formats: direct array or with metadata
        if isinstance(data, list):
            products = data
        elif isinstance(data, dict) and 'products' in data:
            products = data['products']
        else:
            products = []
        
        # Filter berdasarkan product_type jika bukan 'all'
        if product_type != "all":
            products = [p for p in products if p.get('product_type') == product_type]
        
        print(f"✅ Loaded {len(products)} {product_type} products from JSON")
        return products
        
    except Exception as e:
        print(f"❌ Error loading JSON data: {e}")
        return []

def filter_products_by_criteria(products, product_type, min_budget=None, max_budget=None, usage=None, components=None):
    """
    Filter produk berdasarkan kriteria
    """
    if not products:
        return []
    
    filtered_products = []
    
    # Filter berdasarkan budget jika diisi
    if min_budget is not None and max_budget is not None:
        try:
            min_budget = int(min_budget)
            max_budget = int(max_budget)
            print(f"💰 Filtering with budget range: Rp {min_budget:,} - {max_budget:,}")
            
            for product in products:
                price = product.get('price', 0)
                if isinstance(price, (int, float)) and min_budget <= price <= max_budget:
                    filtered_products.append(product)
        except (ValueError, TypeError):
            filtered_products = products
    else:
        filtered_products = products
    
    print(f"📊 After budget filter: {len(filtered_products)} products")
    
    # Filter berdasarkan usage/kegunaan (jika produk laptop)
    if product_type == "laptop" and usage:
        usage_keywords = {
            "Gaming": ["gaming", "game", "rtx", "gtx", "gpu", "graphic", "nvidia", "amd", "rog", "predator", "tuf", "legion"],
            "Office/Kerja": ["office", "kerja", "bisnis", "business", "ultrabook", "thinkpad", "latitude", "elitebook", "vivobook"],
            "Design/Video Editing": ["design", "editing", "video", "creative", "render", "studio", "creator", "workstation"],
            "Programming": ["programming", "developer", "code", "development", "ideapad", "thinkbook"]
        }
        
        if usage in usage_keywords:
            keywords = usage_keywords[usage]
            usage_filtered = []
            for product in filtered_products:
                product_name = product.get('name', '').lower()
                if any(keyword.lower() in product_name for keyword in keywords):
                    usage_filtered.append(product)
            
            filtered_products = usage_filtered
            print(f"🎯 After usage filter '{usage}': {len(filtered_products)} products")
    
    # Filter berdasarkan komponen (jika produk PC component)
    if product_type == "pc_component" and components:
        components_lower = [c.lower() for c in components]
        components_filtered = []
        
        # Mapping komponen PC
        pc_components_keywords = {
            "CPU": ["cpu", "processor", "intel", "amd", "ryzen", "core i"],
            "GPU": ["gpu", "vga", "graphic card", "nvidia", "geforce", "rtx", "gtx", "radeon"],
            "RAM": ["ram", "memory", "ddr4", "ddr5"],
            "Motherboard": ["motherboard", "mainboard", "mobo"],
            "SSD": ["ssd", "nvme", "solid state"],
            "HDD": ["hdd", "hard disk"],
            "PSU": ["psu", "power supply"],
            "Casing": ["casing", "case", "chassis"]
        }
        
        for product in filtered_products:
            product_name = product.get('name', '').lower()
            component_type = product.get('component_type', '').lower()
            
            # Cek berdasarkan nama komponen atau tipe komponen
            for comp in components_lower:
                if comp in pc_components_keywords:
                    keywords = pc_components_keywords[comp]
                    if any(keyword in product_name for keyword in keywords):
                        components_filtered.append(product)
                        break
                elif comp == component_type:
                    components_filtered.append(product)
                    break
        
        # Hapus duplikat
        components_filtered = list({p['id']: p for p in components_filtered}.values())
        filtered_products = components_filtered
        print(f"🔧 After components filter: {len(filtered_products)} products")
    
    # Urutkan berdasarkan rating dan review count
    filtered_products.sort(key=lambda x: (
        x.get('rating', 0) or 0, 
        x.get('review_count', 0) or 0,
        -(x.get('price', 0))
    ), reverse=True)
    
    return filtered_products[:15]  # Return top 15

def rekomendasi_pc_view(request):
    """Rekomendasi rakitan PC: budget + kebutuhan → CPU, Motherboard, RAM, GPU, Storage."""
    budget, budget_int, usage = baca_input_rakitan(request)
    kebutuhan = KEBUTUHAN_DARI_FORM.get(usage)
    pesan_error = ""
    rakitan = None

    if budget:
        if budget_int < 1_000_000:
            pesan_error = "Budget minimal Rp 1.000.000."
        elif not kebutuhan:
            pesan_error = "Pilih kebutuhan terlebih dahulu."
        else:
            rakitan = hitung_rakitan(budget_int, kebutuhan)
            if not rakitan:
                pesan_error = "Budget belum cukup untuk merakit PC lengkap. Coba naikkan budget."

    hasil = rakitan["hasil"] if rakitan else None
    return render(request, "hasil_rakitan.html", {
        "hasil": hasil,
        "komponen": rakitan["komponen"] if rakitan else [],
        "tabel_tfidf": rakitan["tabel_tfidf"] if rakitan else [],
        "heatmap": rakitan["heatmap"] if rakitan else [],
        "evaluasi": rakitan["evaluasi"] if rakitan else None,
        "bobot": BOBOT_SKOR,
        "pesan_error": pesan_error,
        "usage": usage,
        "budget_str": format_rupiah(budget_int),
        "total_str": format_rupiah(hasil["total"]) if hasil else "",
        "sisa_str": format_rupiah(hasil["sisa"]) if hasil else "",
        "tanggal_data": rakitan["tanggal_data"] if rakitan else "",
        "page_title": "Rekomendasi Rakitan PC",
    })


# ===== Download Excel: data scraping 5 komponen hasil rakitan =====

def gaya_header(ws, baris=1):
    """Header tebal, latar hitam, tulisan putih (sama dengan gaya situs)."""
    from openpyxl.styles import Font, PatternFill
    for sel in ws[baris]:
        sel.font = Font(bold=True, color="FFFFFF")
        sel.fill = PatternFill("solid", fgColor="000000")


def lebar_kolom(ws, lebar):
    from openpyxl.utils import get_column_letter
    for i, w in enumerate(lebar, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def download_rakitan_excel(request):
    """Buat file .xlsx dari rakitan yang sedang tampil (budget & kebutuhan diambil dari session)."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font

    budget, budget_int, usage = baca_input_rakitan(request)
    kebutuhan = KEBUTUHAN_DARI_FORM.get(usage)
    if budget_int < 1_000_000 or not kebutuhan:
        return HttpResponse("Belum ada rakitan. Buat rekomendasi dulu dari halaman utama.", status=400)

    rakitan = hitung_rakitan(budget_int, kebutuhan, dengan_evaluasi=False)
    if not rakitan:
        return HttpResponse("Budget belum cukup untuk merakit PC lengkap.", status=400)
    hasil = rakitan["hasil"]

    wb = Workbook()

    # Sheet 1: data scraping 5 komponen
    ws = wb.active
    ws.title = "Rakitan"
    ws.append([
        "Kategori", "Nama produk", "Harga (Rp)", "Harga asli (Rp)", "Rating", "Jumlah ulasan",
        "Toko", "Kota", "Socket", "DDR", "Cosine TF-IDF", "Skor akhir", "Link produk",
        "Link gambar", "Tanggal scraping", "ID produk",
    ])
    gaya_header(ws)
    for item in rakitan["komponen"]:
        p = item["produk"]
        ws.append([
            item["label"], p.get("name"), p.get("price"), p.get("original_price"), p.get("rating"),
            p.get("review_count"), p.get("shop_name"), p.get("shop_city"), p.get("socket", ""),
            p.get("ddr", ""), round(item["nilai_cosine"], 4), round(item["nilai_skor"], 4),
            p.get("url"), p.get("image_url"), p.get("last_updated"), p.get("id"),
        ])
    ws.append([])
    for label, nilai in (("Kebutuhan", usage), ("Budget (Rp)", budget_int),
                         ("Total (Rp)", hasil["total"]), ("Sisa budget (Rp)", hasil["sisa"])):
        ws.append([label, nilai])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    if hasil.get("catatan"):
        ws.append(["Catatan", hasil["catatan"]])
    for baris in ws.iter_rows(min_row=2, min_col=3, max_col=4):
        for sel in baris:
            sel.number_format = "#,##0"
    lebar_kolom(ws, [14, 60, 14, 14, 8, 13, 26, 20, 10, 8, 13, 11, 45, 45, 22, 14])

    # Sheet 2: perhitungan TF-IDF komponen terpilih
    ws2 = wb.create_sheet("Perhitungan TF-IDF")
    ws2.append(["Kategori", "Kata kunci", "TF produk", "DF", "IDF",
                "Bobot profil (wq)", "Bobot produk (wd)", "wq × wd"])
    gaya_header(ws2)
    for t in rakitan["tabel_tfidf"]:
        for b in t["baris"]:
            ws2.append([t["label"], b["kata"], b["tf"], b["df"], float(b["idf"]),
                        float(b["wq"]), float(b["wd"]), float(b["kontribusi"])])
        ws2.append([t["label"], "Cosine (jumlah wq × wd)", None, None, None, None, None, float(t["cosine"])])
        ws2.cell(row=ws2.max_row, column=2).font = Font(bold=True)
        ws2.cell(row=ws2.max_row, column=8).font = Font(bold=True)
        ws2.append([])
    lebar_kolom(ws2, [14, 26, 10, 8, 10, 17, 18, 12])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    nama_file = f"rakitan_{kebutuhan}_{budget_int}.xlsx"
    return FileResponse(buffer, as_attachment=True, filename=nama_file)


def download_lembar_label(request):
    """Lembar penilaian relevansi (pooling top-K sistem + baseline) untuk diisi penilai."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    with KUNCI_RAKITAN:
        baris = lembar_label(ambil_data_rakitan())

    wb = Workbook()
    ws = wb.active
    ws.title = "Label"
    ws.append(["kebutuhan", "kategori", "id", "nama", "harga", "url", "label"])
    gaya_header(ws)
    for b in baris:
        ws.append([b["kebutuhan"], b["kategori"], b["id"], b["nama"], b["harga"], b["url"], None])
    validasi = DataValidation(type="whole", operator="between", formula1="0", formula2="2", allow_blank=True)
    ws.add_data_validation(validasi)
    validasi.add(f"G2:G{ws.max_row}")
    lebar_kolom(ws, [20, 13, 14, 70, 13, 40, 8])

    petunjuk = wb.create_sheet("Petunjuk")
    for teks in [
        "Isi kolom 'label' di sheet Label untuk setiap produk:",
        "2 = sangat cocok untuk kebutuhan tersebut",
        "1 = cukup cocok",
        "0 = tidak cocok",
        "",
        "Nilai berdasarkan nama/spesifikasi produk, bukan harga.",
        "Urutan produk sudah diacak, jadi penilai tidak tahu produk mana pilihan sistem.",
        "Satu kelompok (kebutuhan × kategori) baru dihitung kalau semua produknya sudah diberi label.",
        "",
        "Simpan file ini dengan nama label_relevansi.xlsx di folder data/ (sejajar manage.py),",
        "lalu muat ulang halaman hasil rakitan. Angka Precision dan nDCG akan muncul otomatis.",
    ]:
        petunjuk.append([teks])
    petunjuk.column_dimensions["A"].width = 95

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename="lembar_label_relevansi.xlsx")

def rekomendasi_laptop_view(request):
    """
    View untuk rekomendasi Laptop
    """
    results = []
    json_recommendations = []
    budget = ""
    usage = ""
    custom_usage = ""
    komponen = []
    page_title = "Rekomendasi Laptop"
    product_type = "laptop"
    
    # Variabel untuk budget range
    budget_range_min = 0
    budget_range_max = 0
    high_level_products = []
    medium_level_products = []
    recommended_products = []
    low_level_products = []
    
    # Flag untuk show database results
    show_database = request.GET.get('show_database', 'false') == 'true'
    
    # Cek apakah ada data search di session (untuk GET request)
    session_data = request.session.get('laptop_search_data', {})
    
    if request.method == "POST":
        # Ambil data dari POST
        budget = request.POST.get("budget", "")
        usage = request.POST.get("usage", "")
        custom_usage = request.POST.get("custom_usage", "")
        komponen = request.POST.getlist("components", [])
        
        # Simpan ke session untuk GET request nanti
        request.session['laptop_search_data'] = {
            'budget': budget,
            'usage': usage,
            'custom_usage': custom_usage,
            'komponen': komponen,
        }
        
        print(f"🎯 Laptop Request: budget={budget}, usage={usage}, komponen={komponen}")
        
    elif request.method == "GET" and session_data:
        # Jika GET request dan ada data di session, gunakan data session
        budget = session_data.get('budget', '')
        usage = session_data.get('usage', '')
        custom_usage = session_data.get('custom_usage', '')
        komponen = session_data.get('komponen', [])
        
        print(f"🔄 Laptop Session Data: budget={budget}, usage={usage}, komponen={komponen}")
    
    # HANYA proses rekomendasi jika ada data budget
    if budget:
        try:
            budget_int = int(budget)
            budget_range_min = int(budget_int * 0.7)
            budget_range_max = int(budget_int * 1.3)
            
            # === Dapatkan rekomendasi dari data JSON (laptop) ===
            all_laptops = load_tokopedia_data("laptop")
            json_recommendations = filter_products_by_criteria(
                all_laptops,
                "laptop",
                budget_range_min,
                budget_range_max,
                usage,
                None
            )
            
            # Kelompokkan produk berdasarkan rating
            for product in json_recommendations:
                rating = product.get('rating', 0)
                review_count = product.get('review_count', 0)
                
                if rating == 0:
                    if review_count > 50:
                        rating = 4.5
                    elif review_count > 20:
                        rating = 4.0
                    elif review_count > 5:
                        rating = 3.5
                    elif review_count > 0:
                        rating = 3.0
                    else:
                        rating = 2.5
                    
                    price = product.get('price', 0)
                    if price > 20000000:
                        rating = max(rating, 4.0)
                    elif price > 10000000:
                        rating = max(rating, 3.5)
                    
                    product['estimated_rating'] = rating
                
                product['display_rating'] = rating
                
                if rating >= 4.5:
                    high_level_products.append(product)
                elif rating >= 4.0:
                    medium_level_products.append(product)
                elif rating >= 3.0:
                    recommended_products.append(product)
                else:
                    low_level_products.append(product)
            
            print(f"✅ Laptop JSON recommendations: {len(json_recommendations)} products")
            
        except (ValueError, TypeError) as e:
            print(f"❌ Error parsing budget: {e}")
    
    # === Sistem rekomendasi lokal (Produk Laptop di database) ===
    # HANYA jika ada data budget
    if budget:
        try:
            from django.db.models import Q
            
            budget_int = int(budget)
            min_budget = int(budget_int * 0.7)
            max_budget = int(budget_int * 1.3)
            
            # Cari laptop di database dengan berbagai keyword
            hardware_qs = Produk.objects.filter(
                harga__gte=min_budget,
                harga__lte=max_budget
            ).filter(
                Q(kategori__icontains="laptop") | 
                Q(nama__icontains="laptop") |
                Q(deskripsi__icontains="laptop") |
                Q(kategori__icontains="notebook") |
                Q(nama__icontains="notebook")
            )
            
            print(f"🔍 Laptop Database Query Debug:")
            print(f"  Budget: {min_budget} - {max_budget}")
            print(f"  Count: {hardware_qs.count()}")
            
            # Debug: tampilkan beberapa produk
            if hardware_qs.exists():
                print(f"📦 Sample laptops from database:")
                for prod in hardware_qs[:3]:
                    print(f"  - {prod.nama} (Rp {prod.harga}) - {prod.kategori}")
            
            if hardware_qs.exists():
                # Gabungkan untuk keyword pencarian
                query_text = (usage or "") + " " + custom_usage + " " + " ".join(komponen)
                
                documents = [h.deskripsi for h in hardware_qs]
                documents.append(query_text)
                
                vectorizer = TfidfVectorizer()
                tfidf_matrix = vectorizer.fit_transform(documents)
                cosine_sim = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1])
                scores = cosine_sim[0]
                
                THRESHOLD = 0.15
                ranked_idx = np.argsort(scores)[::-1]
                
                results = []
                for i in ranked_idx:
                    if scores[i] >= THRESHOLD:
                        try:
                            results.append(hardware_qs[int(i)])
                        except:
                            pass
                
                print(f"✅ Laptop Database recommendations: {len(results)} products (threshold: {THRESHOLD})")
                print(f"📊 Scores range: {scores.min():.3f} - {scores.max():.3f}")
                
                # Jika tidak ada hasil dengan threshold, ambil top 3
                if len(results) == 0 and len(hardware_qs) > 0:
                    print("⚠️ No results above threshold, taking top 3")
                    results = list(hardware_qs[:3])
                    
        except Exception as e:
            print(f"❌ Error in Laptop local recommendation: {e}")
            import traceback
            traceback.print_exc()
            results = []
    
    return render(request, 'hasil.html', {
        'results': results,
        'json_recommendations': json_recommendations,
        'budget': budget,
        'usage': usage,
        'custom_usage': custom_usage,
        'komponen': komponen,
        'product_type': product_type,
        'page_title': page_title,
        'budget_range_min': budget_range_min,
        'budget_range_max': budget_range_max,
        'high_level_products': high_level_products,
        'medium_level_products': medium_level_products,
        'recommended_products': recommended_products,
        'low_level_products': low_level_products,
        'show_database': show_database,
    })

def rekomendasi_view(request):
    """
    View universal yang menentukan ke mana mengarahkan berdasarkan parameter
    """
    # Cek apakah ada parameter type di URL atau POST
    product_type = request.GET.get('type', '')
    
    if request.method == "POST":
        # Cek berdasarkan form yang dikirim
        if 'min_budget' in request.POST and 'max_budget' in request.POST:
            # Ini dari form PC components
            return rekomendasi_pc_view(request)
        else:
            # Ini dari form Laptop
            return rekomendasi_laptop_view(request)
    else:
        # Jika GET request dengan parameter type
        if product_type == 'pc':
            return render(request, 'rekomendasi_pc.html')
        else:
            return render(request, 'rekomendasi_laptop.html')

def run_scraper(request):
    # Path root project (tempat manage.py berada)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Path ke file scrapper.py
    scraper_path = os.path.join(base_dir,'scrapper.py')

    # Gunakan Python dari venv
    python_path = sys.executable

    # Jalankan scraper
    subprocess.run([python_path, scraper_path])

    return HttpResponse("✅ Scraper Tokopedia berhasil dijalankan")

def download_excel(request):
    base_dir = settings.BASE_DIR  # root project
    file_path = os.path.join(base_dir, 'data', 'tokopedia_products_latest.xlsx')

    print("Real path:", file_path)

    if os.path.exists(file_path):
        return FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename="tokopedia_products_latest.xlsx"
        )
    else:
        return JsonResponse({
            "status": "error",
            "message": f"File tidak ditemukan di: {file_path}"
        })

def pelajarilebihlanjut(request):
    return render(request, "pelajarilebihlanjut.html")

def loginpage(request):
    return render(request, "loginpage.html")
    
def serve_local_image(request):
    """
    View untuk menyajikan gambar lokal dari direktori hardware/data/images/
    """
    filename = request.GET.get('filename')
    
    if not filename:
        raise Http404("Filename not provided")
    
    # Decode URL
    import urllib.parse
    filename = urllib.parse.unquote(filename)
    print(f"🔍 DEBUG: Filename diterima: {filename}")
    
    # Karena manage.py ada di Lib\hardware\manage.py
    # Maka BASE_DIR adalah G:\project laravel\Project-Joki-Web\Lib\hardware
    # Dan gambar ada di data\images (relatif terhadap BASE_DIR)
    
    # Normalize path
    filename = filename.replace('%5C', '\\').replace('%2F', '/')
    print(f"🔍 DEBUG: Filename setelah normalize: {filename}")
    
    # Hapus "Lib\hardware\" dari awal path jika ada
    # Karena BASE_DIR sudah di Lib\hardware
    if filename.startswith('Lib\\hardware\\'):
        filename = filename[len('Lib\\hardware\\'):]
    elif filename.startswith('Lib/hardware/'):
        filename = filename[len('Lib/hardware/'):]
    
    print(f"🔍 DEBUG: Filename setelah hapus prefix: {filename}")
    
    # Sekarang filename seharusnya: "data\images\0a0a76ede1a54d4999b7e037f2ef0f31.jpeg"
    # Atau mungkin langsung "0a0a76ede1a54d4999b7e037f2ef0f31.jpeg"
    
    # Cek apakah sudah mengandung "data\images"
    if 'data\\images\\' in filename or 'data/images/' in filename:
        # Sudah full path relatif
        relative_path = filename
    else:
        # Hanya nama file, tambahkan path
        relative_path = os.path.join('data', 'images', filename)
    
    print(f"🔍 DEBUG: Relative path: {relative_path}")
    
    # Build absolute path
    absolute_path = os.path.join(settings.BASE_DIR, relative_path)
    print(f"🔍 DEBUG: Absolute path: {absolute_path}")
    
    # Juga coba beberapa alternatif
    possible_paths = [
        # 1. Path yang kita hitung
        absolute_path,
        
        # 2. Langsung dari BASE_DIR + data/images + filename
        os.path.join(settings.BASE_DIR, 'data', 'images', os.path.basename(filename)),
        
        # 3. Coba sebagai path relatif dari project root
        os.path.join(settings.BASE_DIR, '..', '..', filename),  # Naik 2 level dari Lib/hardware
        
        # 4. Hanya nama file di data/images
        os.path.join(settings.BASE_DIR, 'data', 'images', os.path.basename(filename.replace('\\', '/').split('/')[-1])),
    ]
    
    print(f"🔍 DEBUG: BASE_DIR: {settings.BASE_DIR}")
    print(f"🔍 DEBUG: Current dir: {os.getcwd()}")
    
    print(f"🔍 DEBUG: Mencari di {len(possible_paths)} lokasi:")
    for i, path in enumerate(possible_paths):
        exists = os.path.exists(path)
        status = "✅ EXISTS" if exists else "❌ NOT FOUND"
        abs_path = os.path.abspath(path)
        print(f"  [{i}] {path}")
        print(f"       Abs: {abs_path}")
        print(f"       {status}")
        if exists:
            try:
                size = os.path.getsize(path)
                print(f"       Size: {size} bytes")
            except:
                pass
    
    # Coba setiap path
    for filepath in possible_paths:
        if os.path.exists(filepath):
            print(f"✅ FOUND: {filepath}")
            try:
                with open(filepath, 'rb') as f:
                    image_data = f.read()
                
                print(f"✅ SUCCESS: Membaca {len(image_data)} bytes")
                
                # Deteksi tipe MIME
                import mimetypes
                content_type, encoding = mimetypes.guess_type(filepath)
                if not content_type:
                    # Fallback berdasarkan extension
                    if filepath.lower().endswith('.png'):
                        content_type = 'image/png'
                    elif filepath.lower().endswith(('.jpg', '.jpeg')):
                        content_type = 'image/jpeg'
                    elif filepath.lower().endswith('.gif'):
                        content_type = 'image/gif'
                    elif filepath.lower().endswith('.webp'):
                        content_type = 'image/webp'
                    else:
                        content_type = 'image/jpeg'
                
                response = HttpResponse(image_data, content_type=content_type)
                response['Cache-Control'] = 'max-age=3600'
                return response
                
            except Exception as e:
                print(f"❌ ERROR membaca file {filepath}: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    # Jika tidak ditemukan, coba list directory
    print(f"❌ ERROR: Gambar tidak ditemukan")
    images_dir = os.path.join(settings.BASE_DIR, 'data', 'images')
    print(f"❌ Checking: {images_dir}")
    
    if os.path.exists(images_dir):
        try:
            files = os.listdir(images_dir)
            print(f"❌ Files in images directory ({len(files)}):")
            # Cari file yang mengandung nama yang dicari
            target_name = os.path.basename(filename)
            for f in files:
                if target_name in f:
                    print(f"    ❗ SIMILAR: {f}")
                    # Coba file ini
                    alt_path = os.path.join(images_dir, f)
                    if os.path.exists(alt_path):
                        try:
                            with open(alt_path, 'rb') as f:
                                image_data = f.read()
                            print(f"    ✅ FOUND SIMILAR! {len(image_data)} bytes")
                            return HttpResponse(image_data, content_type='image/jpeg')
                        except:
                            pass
                if len([f for f in files if f.endswith(('.jpg', '.jpeg', '.png'))]) > 10:
                    print(f"    Showing first 10 images only...")
                    break
        except Exception as e:
            print(f"❌ ERROR listing: {e}")
    
    raise Http404(f"Image not found")

def serve_local_image(request):
    """Sajikan thumbnail dari folder thumbs/, atau gambar asli kalau thumbnail belum ada."""
    import mimetypes
    from django.http import FileResponse

    raw = urllib.parse.unquote(request.GET.get("filename", ""))
    name = os.path.basename(raw.replace("\\", "/"))
    if not name:
        raise Http404("Filename not provided")

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    thumb = os.path.join(base, "thumbs", os.path.splitext(name)[0] + ".jpg")
    original = os.path.join(base, "data", "images", name)

    if os.path.isfile(thumb):
        path, ctype = thumb, "image/jpeg"
    elif os.path.isfile(original):
        path, ctype = original, mimetypes.guess_type(original)[0] or "image/jpeg"
    else:
        raise Http404("Gambar tidak ditemukan")

    response = FileResponse(open(path, "rb"), content_type=ctype)
    response["Cache-Control"] = "public, max-age=2592000"
    return response