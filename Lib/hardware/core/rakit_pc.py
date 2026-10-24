import json
import os
import re
import math
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Lokasi file JSON hasil scraping (folder data/ sejajar dengan folder core/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE_DIR, "data", "tokopedia_products_latest.json")

# Label dari scraper → kategori rakitan
KATEGORI_RAKITAN = {
    "cpu": "CPU",
    "motherboard": "Motherboard",
    "ram": "RAM",
    "gpu": "GPU",
    "ssd": "Storage",
    "hdd": "Storage",
}

# Kata yang bikin produk dibuang di SEMUA kategori
KATA_DIBUANG_UMUM = ["rakitan", "paket", "bundling", "bundle", "upgrade", "trade in", "tradein", "pc build"]

# Kata yang bikin produk dibuang, khusus per kategori
KATA_DIBUANG_PER_KATEGORI = {
    "CPU": [
        "laptop", "notebook", "cooler", "heatsink", "aio", "liquid", "thermal", "pasta",
        # kata milik kategori lain → ini PC utuh, bukan prosesor
        "rtx", "gtx", "ssd",
    ],
    "Motherboard": ["laptop", "notebook"],
    "RAM": [
        "laptop", "notebook", "sodimm", "so-dimm", "so dimm", "soddim", "sodim",
        "water block", "waterblock",
        # kata milik kategori lain → ini laptop/PC utuh, bukan keping RAM
        "rtx", "gtx", "core i", "core ultra", "ssd", "fhd",
    ],
    "GPU": [
        "laptop", "notebook", "bracket", "holder", "riser", "monitor",
        # kata milik kategori lain → ini motherboard/laptop/PC, bukan kartu grafis
        "motherboard", "mainboard", "mobo",
        "probook", "elitebook", "thinkpad", "touchsmart",
    ],
    "Storage": [
        "enclosure", "external", "eksternal", "portable", "usb", "sekrup", "baut", "caddy",
        # kata milik kategori lain → ini laptop/PC/server utuh, bukan storage
        "celeron", "core i", "ryzen", "windows", "xeon",
    ],
}
# Kata yang "menyelamatkan" produk dari saringan kata per kategori
KATA_PENGECUALIAN = {
    "CPU": [
        "wraith", "with cooler", "stock cooler",
        "without cooler", "tanpa cooler", "tanpa fan", "no cooler",
    ],
}

# Harga minimum per kategori (di bawah ini dianggap aksesoris)
HARGA_MINIMUM = {
    "CPU": 400000,
    "Motherboard": 500000,
    "RAM": 150000,
    "GPU": 600000,
    "Storage": 150000,
}

# Chipset motherboard → socket
CHIPSET_SOCKET = {
    "AM4": ["a320", "a520", "b350", "b450", "b550", "x370", "x470", "x570"],
    "AM5": ["a620", "b650", "b840", "b850", "x670", "x870"],
    "LGA1200": ["h410", "h510", "b460", "b560", "h470", "h570", "z490", "z590"],
    "LGA1700": ["h610", "b660", "b760", "h670", "h770", "z690", "z790"],
    "LGA1851": ["h810", "b860", "z890"],
}

# Tipe DDR yang mungkin untuk tiap socket
DDR_PER_SOCKET = {
    "AM4": ["DDR4"],
    "AM5": ["DDR5"],
    "LGA1200": ["DDR4"],
    "LGA1700": ["DDR4", "DDR5"],
    "LGA1851": ["DDR5"],
}

# Profil kata kunci per kebutuhan per kategori (bahan TF-IDF)
# Profil kata kunci per kebutuhan per kategori (bahan TF-IDF)
# Profil kata kunci per kebutuhan per kategori (bahan TF-IDF)
PROFIL_KEBUTUHAN = {
    "gaming": {
        "CPU": "ryzen5 ryzen7 x3d i5 i7 ultra5 ultra7 gaming 6core 8core 12thread 16thread",
        "Motherboard": "gaming wifi ddr5 b650 b850 b760 tuf rog aorus mag",
        "RAM": "ddr5 16gb 32gb dual kit 6000mhz 5600mhz 3200mhz gaming rgb",
        "GPU": "rtx geforce radeon rx gaming gddr6 gddr7 8gb 12gb 16gb oc",
        "Storage": "ssd nvme gen4 pcie 1tb 2tb gaming",
    },
    "office": {
        "CPU": "i3 i5 ryzen3 ryzen5 5600g 8600g 5700g 8500g radeon graphics uhd apu 4core 6core",
        "Motherboard": "h610 a520 b450 b550 prime pro micro matx",
        "RAM": "ddr4 8gb 16gb 3200mhz",
        "GPU": "gt 710 730 1030 r7 240 low profile lp 2gb 4gb",
        "Storage": "ssd sata 512gb 1tb",
    },
    "programming": {
        "CPU": "i5 i7 ryzen5 ryzen7 ultra5 ultra7 8core 12core 16thread 20thread",
        "Motherboard": "b550 b650 b760 wifi pro",
        "RAM": "32gb 16gb ddr5 ddr4 kit dual",
        "GPU": "gtx 1650 rtx 3050 4060 rx 6600 8gb",
        "Storage": "nvme ssd gen4 1tb 2tb",
    },
    "editing": {
        "CPU": "ryzen7 ryzen9 i7 i9 ultra7 ultra9 12core 16core 24thread 32thread",
        "Motherboard": "b650 b760 x670 z790 ddr5 wifi creator proart",
        "RAM": "32gb 64gb ddr5 kit dual 6000mhz",
        "GPU": "rtx geforce 12gb 16gb gddr6 gddr7",
        "Storage": "nvme gen4 2tb 4tb ssd",
    },
    "rendering": {
        "CPU": "ryzen9 i9 ultra9 16core 24core 32thread x3d",
        "Motherboard": "x670 x870 z790 z890 ddr5 wifi",
        "RAM": "64gb 32gb ddr5 kit dual",
        "GPU": "rtx 16gb 24gb 32gb 4080 4090 5080 5090 gddr7 gddr6x",
        "Storage": "nvme gen4 gen5 2tb 4tb ssd",
    },
}

# Nilai "usage" dari form index.html → key PROFIL_KEBUTUHAN
KEBUTUHAN_DARI_FORM = {
    "Gaming": "gaming",
    "Office/Kerja": "office",
    "Programming": "programming",
    "Design/Video Editing": "editing",
    "Rendering 3D": "rendering",
}
# Bobot skor akhir (total = 1.0)
BOBOT_SKOR = {
    "tfidf": 0.5,    # kecocokan dengan kebutuhan
    "harga": 0.3,    # patokan kelas performa
    "ulasan": 0.2,   # jumlah ulasan = seberapa banyak dibeli & dipercaya orang
}

# Kelompok kompatibilitas per kategori (tangga kandidat dibikin per kelompok)
KUNCI_GRUP = {
    "CPU": lambda p: p["socket"],
    "Motherboard": lambda p: (p["socket"], p["ddr"]),
    "RAM": lambda p: p["ddr"],
    "GPU": lambda p: "semua",
    "Storage": lambda p: "semua",
}
# Seberapa penting tiap kategori untuk tiap kebutuhan (total per baris = 1.0)
BOBOT_KATEGORI = {
    "gaming":      {"CPU": 0.25, "Motherboard": 0.10, "RAM": 0.15, "GPU": 0.40, "Storage": 0.10},
    "office":      {"CPU": 0.35, "Motherboard": 0.15, "RAM": 0.20, "GPU": 0.10, "Storage": 0.20},
    "programming": {"CPU": 0.35, "Motherboard": 0.10, "RAM": 0.25, "GPU": 0.15, "Storage": 0.15},
    "editing":     {"CPU": 0.30, "Motherboard": 0.10, "RAM": 0.20, "GPU": 0.30, "Storage": 0.10},
    "rendering":   {"CPU": 0.30, "Motherboard": 0.10, "RAM": 0.15, "GPU": 0.35, "Storage": 0.10},
}

# Syarat wajib per kebutuhan (constraint), diambil dari panduan umum rakit PC
ATURAN_WAJIB = {
    "gaming":      {"ram_min_gb": 16, "ssd_min_gb": 480, "porsi_gpu_min": 0.35},
    "office":      {"ram_min_gb": 8,  "ssd_min_gb": 240, "porsi_gpu_min": 0.00},
    "programming": {"ram_min_gb": 16, "ssd_min_gb": 480, "porsi_gpu_min": 0.10},
    "editing":     {"ram_min_gb": 32, "ssd_min_gb": 960, "porsi_gpu_min": 0.25},
    "rendering":   {"ram_min_gb": 32, "ssd_min_gb": 960, "porsi_gpu_min": 0.30},
}

# ===================== LANGKAH 1: BACA & KELOMPOKKAN =====================

def load_komponen():
    """Baca JSON, ambil produk komponen PC saja (laptop dibuang)."""
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    produk = data["products"] if isinstance(data, dict) else data
    return [p for p in produk if p.get("product_type") == "pc_component"]


def kelompokkan(produk_list):
    """Masukkan tiap produk ke salah satu dari 5 kategori rakitan."""
    kelompok = {"CPU": [], "Motherboard": [], "RAM": [], "GPU": [], "Storage": []}
    for p in produk_list:
        kategori = KATEGORI_RAKITAN.get(p.get("component_type"))
        if kategori:
            kelompok[kategori].append(p)
    return kelompok


# ===================== LANGKAH 2: PEMBERSIHAN =====================

def bersihkan(kategori, produk_list):
    """Buang produk yang nyasar berdasarkan kata di nama dan harga minimum."""
    kata_kategori = KATA_DIBUANG_PER_KATEGORI[kategori]
    pengecualian = KATA_PENGECUALIAN.get(kategori, [])
    hasil = []
    for p in produk_list:
        nama = (p.get("name") or "").lower()
        harga = p.get("price") or 0

        if harga < HARGA_MINIMUM[kategori]:
            continue

        # Kata umum (paket, rakitan, bundle) selalu dibuang, tanpa pengecualian
        if any(kata in nama for kata in KATA_DIBUANG_UMUM):
            continue

        # Kata per kategori dibuang, KECUALI ada kata pengecualian
        kena_saringan = any(kata in nama for kata in kata_kategori)
        selamat = any(kata in nama for kata in pengecualian)
        if kena_saringan and not selamat:
            continue

        hasil.append(p)
    return hasil


# ===================== LANGKAH 3a: SOCKET CPU =====================

def socket_eksplisit(nama):
    """Socket yang disebut langsung di nama, misal 'socket am5' atau 'lga 1700'."""
    hasil = set()
    for angka in re.findall(r"\bam([45])\b", nama):
        hasil.add("AM" + angka)
    for angka in re.findall(r"(?:lga|socket|soket)\s*(1200|1700|1851)", nama):
        hasil.add("LGA" + angka)
    return hasil


def socket_dari_model_cpu(nama):
    """Tebak socket dari nomor model prosesor."""
    hasil = set()

    # AMD Ryzen desktop: ryzen 5 7600x, ryzen 7 9800x3d, ryzen 5 pro 4650g, ryzen 5600
    for gen in re.findall(r"ryzen[\w\s-]{0,12}?\b(\d)\d{3}(?:x3d|xt|x|gt|ge|g|f)?\b", nama):
        hasil.add("AM5" if int(gen) >= 7 else "AM4")

    # Intel Core desktop 5 digit: i5-14400f, i3 10100f, i7 10700k
    for model in re.findall(r"i[3579][\s-]*(\d{5})(?:ks|kf|k|f|t)?\b", nama):
        gen = int(model[:2])
        if gen in (10, 11):
            hasil.add("LGA1200")
        elif gen in (12, 13, 14):
            hasil.add("LGA1700")

    # Intel Core Ultra desktop seri 200: ultra 5 245k, ultra 7 265kf, ultra 9-285k
    if re.search(r"ultra[\w\s-]{0,15}?\b2\d\d(?:kf|k|f|t)?\b", nama):
        hasil.add("LGA1851")

    return hasil


def socket_cpu(nama):
    """Gabungkan dua sumber. Valid hanya kalau hasilnya tepat satu socket."""
    kandidat = socket_eksplisit(nama) | socket_dari_model_cpu(nama)
    if len(kandidat) == 1:
        return kandidat.pop()
    return None


# ===================== LANGKAH 3b: SOCKET & DDR MOTHERBOARD =====================

def socket_dari_chipset(nama):
    """Tebak socket dari chipset motherboard, misal b650 → AM5."""
    hasil = set()
    for socket, daftar_chipset in CHIPSET_SOCKET.items():
        for chipset in daftar_chipset:
            if re.search(r"\b" + chipset, nama):
                hasil.add(socket)
    return hasil


def socket_motherboard(nama):
    """Gabungkan socket eksplisit + chipset. Valid hanya kalau tepat satu."""
    kandidat = socket_eksplisit(nama) | socket_dari_chipset(nama)
    if len(kandidat) == 1:
        return kandidat.pop()
    return None


def ddr_disebut(nama):
    """DDR yang disebut di nama: 'ddr5', 'ddr 4', atau singkatan 'd4' / 'd5'."""
    hasil = set()
    for angka in re.findall(r"ddr\s*([45])", nama):
        hasil.add("DDR" + angka)
    for angka in re.findall(r"\bd([45])\b", nama):
        hasil.add("DDR" + angka)
    return hasil


def ddr_motherboard(nama, socket):
    """Tentukan DDR motherboard. None kalau gak jelas atau bertentangan."""
    boleh = DDR_PER_SOCKET[socket]
    disebut = ddr_disebut(nama)

    if len(disebut) == 1:
        ddr = disebut.pop()
        return ddr if ddr in boleh else None   # misal "AM4 DDR5" → mustahil → None

    if len(disebut) == 0 and len(boleh) == 1:
        return boleh[0]                        # socket yang DDR-nya pasti → isi otomatis

    return None                                # LGA1700 gak nyebut DDR, atau nyebut dua-duanya


# ===================== LANGKAH 3c: DDR RAM + MULTI-VARIAN =====================

def ddr_ram(nama):
    """DDR keping RAM. Valid hanya kalau nyebut tepat satu (DDR4 atau DDR5)."""
    disebut = ddr_disebut(nama)
    if len(disebut) == 1:
        return disebut.pop()
    return None


def kapasitas_gb(nama):
    """Semua kapasitas yang disebut di nama, dalam GB."""
    nama = re.sub(r"\b(bkn|bukan)\b.*", " ", nama)                       # buang teks setelah "bkn"/"bukan"
    nama = re.sub(r"\d+(?:[.,]\d+)?\s*gb\s*/\s*s|\d+\s*gbps", " ", nama)  # "6gb/s", "6 gbps" = kecepatan
    nama = re.sub(r"sata[\w\s]{0,10}?\b6(?:\.0)?\s*gb", " ", nama)       # "sata 6gb", "sata iii 3d 6gb" = kecepatan
    nama = re.sub(r"\d+\s*x\s*\d+\s*gb", " ", nama)                      # kit "2x16gb", "2 x 16gb"
    nama = re.sub(r"\d+\s*gb\s*x\s*\d+", " ", nama)                      # kit "16gb x 2", "32gb x2"
    hasil = set()
    for angka, satuan in re.findall(r"(\d+(?:[.,]\d+)?)\s*(gb|tb)\b", nama):
        nilai = float(angka.replace(",", "."))
        hasil.add(nilai * 1000 if satuan == "tb" else nilai)
    return hasil


def frekuensi_mhz(nama):
    """Semua kecepatan RAM yang disebut, misal 3200mhz, 5600 mhz."""
    return set(re.findall(r"(\d{4})\s*mhz", nama))


def jumlah_varian(kapasitas):
    """Hitung kapasitas yang beda jauh. Selisih di bawah 5% dianggap sama (1TB = 1024GB)."""
    varian = 0
    terakhir = None
    for nilai in sorted(kapasitas):
        if terakhir is None or nilai > terakhir * 1.05:
            varian += 1
            terakhir = nilai
    return varian


# ===================== LANGKAH 3d: MULTI-VARIAN CPU =====================

def nomor_model_cpu(nama):
    """Semua nomor model prosesor di nama (angkanya saja, akhiran huruf diabaikan)."""
    hasil = set()

    # Ryzen: 4 digit, misal 5600, 7600x, 4650g
        # Ryzen: 4 digit, misal 5600, 7600x, 4650g
    if "ryzen" in nama:
        for angka in re.findall(r"\b([1-9]\d{3})(?:x3d|xt|x|gt|ge|g|f)?\b", nama):
            if angka.endswith("000"):          # "7000 series" = nama seri, bukan model
                continue
            if 2010 <= int(angka) <= 2030:     # kemungkinan tahun, bukan model
                continue
            hasil.add(angka)

    # Intel Core gen 10-14: 5 digit, misal 12400, 14600k
    hasil.update(re.findall(r"\b(1[0-4]\d{3})(?:ks|kf|k|f|t)?\b", nama))

    # Intel Core Ultra seri 200: 3 digit, misal 245k, 265kf
    if "ultra" in nama:
        hasil.update(re.findall(r"\b(2\d\d)(?:kf|k|f|t)?\b", nama))

    return hasil


def multi_varian(kategori, nama):
    """True kalau listing ini jual beberapa varian sekaligus."""
    if kategori == "CPU":
        return len(nomor_model_cpu(nama)) > 1
    if kategori == "RAM":
        return jumlah_varian(kapasitas_gb(nama)) > 1 or len(frekuensi_mhz(nama)) > 1
    if kategori == "Storage":
        return jumlah_varian(kapasitas_gb(nama)) > 1
    return False

# ===================== SIAPKAN DATA (gabungan Langkah 1–3) =====================

def siapkan_data(tampilkan_laporan=False):
    """Jalankan semua preprocessing. Hasil: dict kategori → daftar produk siap pakai."""
    kelompok = kelompokkan(load_komponen())
    hasil = {}
    laporan = []

    for kategori, daftar in kelompok.items():
        awal = len(daftar)
        bersih = bersihkan(kategori, daftar)
        tunggal = [p for p in bersih if not multi_varian(kategori, p["name"].lower())]

        siap = []
        for p in tunggal:
            nama = p["name"].lower()
            if kategori == "CPU":
                p["socket"] = socket_cpu(nama)
                if not p["socket"]:
                    continue
            elif kategori == "Motherboard":
                p["socket"] = socket_motherboard(nama)
                if not p["socket"]:
                    continue
                p["ddr"] = ddr_motherboard(nama, p["socket"])
                if not p["ddr"]:
                    continue
            elif kategori == "RAM":
                p["ddr"] = ddr_ram(nama)
                if not p["ddr"]:
                    continue
            siap.append(p)

        hasil[kategori] = siap
        laporan.append((kategori, awal, len(bersih), len(tunggal), len(siap)))

    if tampilkan_laporan:
        print(f"{'Kategori':<12}{'Awal':>7}{'Bersih':>9}{'Tunggal':>10}{'Siap':>7}")
        for kategori, awal, n_bersih, n_tunggal, n_siap in laporan:
            print(f"{kategori:<12}{awal:>7}{n_bersih:>9}{n_tunggal:>10}{n_siap:>7}")

    return hasil

# ===================== LANGKAH 4: TF-IDF + COSINE SIMILARITY =====================

def normalisasi_teks(teks):
    """Huruf kecil + satukan angka penting dengan katanya, biar gak dibuang TF-IDF."""
    teks = teks.lower()
    teks = re.sub(r"(\d+)\s*(gb|tb|mhz)\b", r"\1\2", teks)           # "16 gb"   → "16gb"
    teks = re.sub(r"\b(ryzen|ultra)[\s-]*([3579])\b", r"\1\2", teks)  # "ryzen 9" → "ryzen9"
    teks = re.sub(r"\b(rtx|gtx|rx|arc)(\d)", r"\1 \2", teks)          # "rtx5060" → "rtx 5060"
    teks = re.sub(r"(\d+)[\s-]*cores?\b", r"\1core", teks)            # "8 cores" → "8core"
    teks = re.sub(r"(\d+)[\s-]*threads?\b", r"\1thread", teks)        # "16 threads" → "16thread"
    return teks


def skor_tfidf(produk_list, profil):
    """
    Hitung kemiripan nama tiap produk dengan profil kebutuhan (0 sampai 1).
    Skor disimpan ke p["skor_tfidf"]. Return: kata profil yang gak dikenal.
    """
    dokumen = [normalisasi_teks(p["name"]) for p in produk_list]

    vectorizer = TfidfVectorizer()
    matriks = vectorizer.fit_transform(dokumen)                  # belajar kosakata dari nama produk
    vektor_profil = vectorizer.transform([normalisasi_teks(profil)])

    skor = cosine_similarity(vektor_profil, matriks)[0]
    for p, s in zip(produk_list, skor):
        p["skor_tfidf"] = float(s)

    kata_profil = normalisasi_teks(profil).split()
    return [k for k in kata_profil if k not in vectorizer.vocabulary_]

# ===================== LANGKAH 5: SKOR AKHIR (MIN-MAX NORMALIZATION) =====================

def min_max(nilai_list):
    """Ubah daftar angka jadi skala 0–1: (x - min) / (max - min)."""
    terkecil, terbesar = min(nilai_list), max(nilai_list)
    if terbesar == terkecil:
        return [0.5] * len(nilai_list)          # semua nilainya sama → anggap netral
    return [(n - terkecil) / (terbesar - terkecil) for n in nilai_list]

def ambil_ulasan(p):
    """Jumlah ulasan sebagai angka. Kalau kosong/aneh → 0."""
    try:
        return int(p.get("review_count") or 0)
    except (TypeError, ValueError):
        return 0


def hitung_skor_akhir(produk_list, profil):
    """Gabungkan TF-IDF, harga (skala log), dan jumlah ulasan (skala log) jadi p["skor"]."""
    skor_tfidf(produk_list, profil)

    tfidf_n = min_max([p["skor_tfidf"] for p in produk_list])
    harga_n = min_max([math.log(p["price"]) for p in produk_list])
    ulasan_n = min_max([math.log1p(ambil_ulasan(p)) for p in produk_list])

    for p, t, h, u in zip(produk_list, tfidf_n, harga_n, ulasan_n):
        p["tfidf_n"], p["harga_n"], p["ulasan_n"] = t, h, u   # disimpan buat ditampilkan & evaluasi
        p["skor"] = (
            BOBOT_SKOR["tfidf"] * t
            + BOBOT_SKOR["harga"] * h
            + BOBOT_SKOR["ulasan"] * u
        )

# ===================== LANGKAH 6a: KANDIDAT EFISIEN (PARETO FRONTIER) =====================

def kandidat_efisien(produk_list, budget):
    """Buang produk yang kalah telak (ada yang lebih murah DAN skornya lebih tinggi)."""
    terjangkau = [p for p in produk_list if p["price"] <= budget]
    urut = sorted(terjangkau, key=lambda p: (p["price"], -p["skor"]))

    hasil = []
    skor_terbaik = -1
    for p in urut:                      # dari yang termurah ke termahal
        if p["skor"] > skor_terbaik:    # cuma disimpan kalau skornya ngalahin semua yang lebih murah
            hasil.append(p)
            skor_terbaik = p["skor"]
    return hasil


def kandidat_per_grup(kategori, produk_list, budget):
    """Bikin tangga kandidat terpisah untuk tiap kelompok kompatibilitas."""
    grup = {}
    for p in produk_list:
        grup.setdefault(KUNCI_GRUP[kategori](p), []).append(p)

    hasil = []
    for daftar in grup.values():
        hasil.extend(kandidat_efisien(daftar, budget))
    return hasil

# ===================== LANGKAH 6b: RAKIT KOMBINASI TERBAIK =====================

# ===================== LANGKAH 6b: RAKIT KOMBINASI TERBAIK =====================

def kapasitas_produk(p):
    """Total kapasitas dalam GB (RAM atau SSD). Kit '16GB (2x8GB)' dihitung 16."""
    kap = kapasitas_gb(p["name"].lower())
    return max(kap) if kap else 0


def terapkan_aturan(data, budget, kebutuhan):
    """Saring produk sesuai syarat wajib kebutuhan. Data asli gak diubah."""
    aturan = ATURAN_WAJIB[kebutuhan]
    gpu_min = aturan["porsi_gpu_min"] * budget

    hasil = dict(data)
    hasil["Storage"] = [
        p for p in data["Storage"]
        if p.get("component_type") == "ssd" and kapasitas_produk(p) >= aturan["ssd_min_gb"]
    ]
    hasil["RAM"] = [p for p in data["RAM"] if kapasitas_produk(p) >= aturan["ram_min_gb"]]
    hasil["GPU"] = [p for p in data["GPU"] if p["price"] >= gpu_min]
    return hasil

def rakit_pc(data, budget, kebutuhan, pakai_aturan=True):
    """
    Cari 1 rakitan (CPU, Motherboard, RAM, GPU, Storage) yang kompatibel,
    total harga <= budget, dan skor rakitannya paling tinggi.
    """
    profil = PROFIL_KEBUTUHAN[kebutuhan]
    bobot = BOBOT_KATEGORI[kebutuhan]

    # 1. Hitung skor semua produk
    for kategori, daftar in data.items():
        hitung_skor_akhir(daftar, profil[kategori])

    # 2. Terapkan syarat wajib (kalau diminta)
    pilihan = terapkan_aturan(data, budget, kebutuhan) if pakai_aturan else data

    # 3. Ambil kandidat efisien per kategori
    kandidat = {}
    for kategori, daftar in pilihan.items():
        kandidat[kategori] = kandidat_per_grup(kategori, daftar, budget)
        if not kandidat[kategori]:
            return None

    termurah_gpu = min(p["price"] for p in kandidat["GPU"])
    termurah_storage = min(p["price"] for p in kandidat["Storage"])

    # 4. Coba semua kombinasi yang kompatibel dan muat di budget
    terbaik = None
    skor_terbaik = -1

    for cpu in kandidat["CPU"]:
        for mobo in kandidat["Motherboard"]:
            if mobo["socket"] != cpu["socket"]:
                continue
            for ram in kandidat["RAM"]:
                if ram["ddr"] != mobo["ddr"]:
                    continue

                subtotal = cpu["price"] + mobo["price"] + ram["price"]
                if subtotal + termurah_gpu + termurah_storage > budget:
                    continue

                skor_sub = (bobot["CPU"] * cpu["skor"]
                            + bobot["Motherboard"] * mobo["skor"]
                            + bobot["RAM"] * ram["skor"])

                for gpu in kandidat["GPU"]:
                    if subtotal + gpu["price"] + termurah_storage > budget:
                        continue
                    for ssd in kandidat["Storage"]:
                        total = subtotal + gpu["price"] + ssd["price"]
                        if total > budget:
                            continue
                        skor = skor_sub + bobot["GPU"] * gpu["skor"] + bobot["Storage"] * ssd["skor"]
                        if skor > skor_terbaik:
                            skor_terbaik = skor
                            terbaik = {"CPU": cpu, "Motherboard": mobo, "RAM": ram,
                                       "GPU": gpu, "Storage": ssd}

    if not terbaik:
        return None

    total = sum(p["price"] for p in terbaik.values())
    return {
        "kebutuhan": kebutuhan,
        "budget": budget,
        "komponen": terbaik,
        "total": total,
        "sisa": budget - total,
        "skor": skor_terbaik,
    }

def rekomendasi_rakitan(data, budget, kebutuhan):
    """Coba dengan syarat wajib dulu. Kalau gak ada yang muat, longgarkan syaratnya."""
    hasil = rakit_pc(data, budget, kebutuhan, pakai_aturan=True)
    if hasil:
        hasil["catatan"] = ""
        return hasil

    hasil = rakit_pc(data, budget, kebutuhan, pakai_aturan=False)
    if hasil:
        hasil["catatan"] = "Budget belum cukup untuk spesifikasi ideal, beberapa syarat dilonggarkan."
    return hasil

# ===================== LANGKAH 7: RINCIAN TF-IDF (TABEL PERHITUNGAN & HEATMAP) =====================

def rincian_tfidf(daftar_kategori, profil, produk_dipilih):
    """
    Bongkar perhitungan TF-IDF beberapa produk terhadap profil kebutuhan.
    Vectorizer di-fit ke SEMUA produk kategori itu, sama persis dengan skor_tfidf(),
    jadi angka di sini = angka yang dipakai sistem untuk memilih.
    """
    dokumen = [normalisasi_teks(p["name"]) for p in daftar_kategori]

    vectorizer = TfidfVectorizer()
    matriks = vectorizer.fit_transform(dokumen)
    analyzer = vectorizer.build_analyzer()          # pemecah kata yang sama dengan sklearn
    vocab = vectorizer.vocabulary_
    df = (matriks > 0).sum(axis=0).A1               # document frequency tiap kata

    teks_profil = normalisasi_teks(profil)
    v_profil = vectorizer.transform([teks_profil])
    kata_profil = list(dict.fromkeys(t for t in analyzer(teks_profil) if t in vocab))

    def hitung_tf(teks):
        tf = {}
        for kata in analyzer(teks):
            tf[kata] = tf.get(kata, 0) + 1
        return tf

    tf_profil = hitung_tf(teks_profil)
    bobot_profil = {k: float(v_profil[0, vocab[k]]) for k in kata_profil}

    baris = []
    for p in produk_dipilih:
        teks = normalisasi_teks(p["name"])
        v_produk = vectorizer.transform([teks])
        tf = hitung_tf(teks)
        bobot = {k: float(v_produk[0, vocab[k]]) for k in kata_profil}
        baris.append({
            "produk": p,
            "teks": teks,
            "tf": {k: tf.get(k, 0) for k in kata_profil},
            "bobot": bobot,                                         # TF-IDF ternormalisasi L2
            "kontribusi": {k: bobot_profil[k] * bobot[k] for k in kata_profil},
            "cosine": float(cosine_similarity(v_profil, v_produk)[0, 0]),
        })

    return {
        "n_dokumen": len(dokumen),
        "teks_profil": teks_profil,
        "kata": [{
            "kata": k,
            "df": int(df[vocab[k]]),
            "idf": float(vectorizer.idf_[vocab[k]]),
            "tf_profil": tf_profil.get(k, 0),
            "bobot_profil": bobot_profil[k],
        } for k in kata_profil],
        "kata_tak_dikenal": [k for k in teks_profil.split() if k not in vocab],
        "baris": baris,
    }


def pembanding_heatmap(kategori, daftar_kategori, terpilih, batas_harga, jumlah=5):
    """
    Produk terpilih + pesaing yang sebenarnya BISA menggantikannya:
    satu kelompok kompatibilitas (socket/DDR sama) dan harganya tidak bikin total lewat budget.
    Diurutkan dari skor akhir tertinggi.
    """
    grup = KUNCI_GRUP[kategori](terpilih)
    pesaing = sorted(
        (p for p in daftar_kategori
         if p is not terpilih and p["price"] <= batas_harga and KUNCI_GRUP[kategori](p) == grup),
        key=lambda p: -p["skor"],
    )
    return [terpilih] + pesaing[:jumlah - 1]


if __name__ == "__main__":
    import time

    data = siapkan_data()
    skenario = [
        ("Gaming", 10_000_000),                 # contoh dari dosen
        ("Gaming", 6_000_000),
        ("Gaming", 15_000_000),
        ("Office/Kerja", 5_000_000),
        ("Design/Video Editing", 20_000_000),
    ]

    for usage_form, budget in skenario:
        mulai = time.perf_counter()
        hasil = rakit_pc(data, budget, KEBUTUHAN_DARI_FORM[usage_form])
        durasi = time.perf_counter() - mulai

        print(f"\n===== {usage_form}, budget Rp {budget:,} ({durasi:.1f} detik) =====")
        if not hasil:
            print("  Tidak ada kombinasi yang muat di budget ini.")
            continue

        for kategori, p in hasil["komponen"].items():
            info = " ".join(str(p[k]) for k in ("socket", "ddr") if k in p)
            print(f"  {kategori:<12} {p['price']:>11,} | {info:<13} | {p['name'][:55]}")
        print(f"  {'TOTAL':<12} {hasil['total']:>11,} | sisa Rp {hasil['sisa']:,}")