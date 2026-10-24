# save_tokopedia_data.py
import requests
import json
import math
import uuid
from datetime import datetime
import os
import time 
from openpyxl import Workbook

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(BASE_DIR, "data", "images")

os.makedirs(IMAGE_DIR, exist_ok=True)

def safe_filename(name):
    return "".join(c if c.isalnum() else "_" for c in name)

def download_image(url):
    if not url:
        return None

    try:
        # Tentukan ekstensi
        ext = ".jpg"
        u = url.lower()
        if ".png" in u:
            ext = ".png"
        elif ".webp" in u:
            ext = ".webp"
        elif ".jpeg" in u:
            ext = ".jpeg"

        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(IMAGE_DIR, filename)

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.tokopedia.com/"
        }

        r = requests.get(url, headers=headers, timeout=15)

        if r.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(r.content)

            relative = os.path.join("Lib", "hardware", "data", "images", filename)
            return relative

    except Exception as e:
        print(f"Gagal download image: {e}")

    return None

TOKOPEDIA_API_URL = "https://gql.tokopedia.com/graphql/SearchProductQueryV4"

def parse_price(value):
    """
    Konversi harga dari Tokopedia ke integer.
    Contoh: "Rp1.234.000" → 1234000
    """
    if not value:
        return 0

    try:
        value = str(value)
        digits = ''.join(filter(str.isdigit, value))
        return int(digits) if digits else 0
    except:
        return 0

def search_tokopedia(query: str, price_min: int = None, price_max: int = None, 
                     rows: int = 100, max_pages: int = 10):
    """
    Cari produk di Tokopedia menggunakan multiple pages.
    """
    import time
    
    all_products = []
    seen_ids = set()
    
    for page in range(1, max_pages + 1):
        print(f"  📄 Mengambil halaman {page}...")
        
        # Variabel untuk GraphQL
        params = {
            "device": "desktop",
            "navsource": "home",
            "ob": 23,
            "page": page,
            "q": query,
            "related": True,
            "rows": rows,
            "safe_search": False,
            "scheme": "https",
            "shipping": "",
            "source": "universe",
            "srp_component_id": "01.02.01.01",
            "st": "product",
            "start": (page - 1) * rows,
            "topads_bucket": True,
            "unique_id": "some-unique-id",
            "user_addressId": "",
            "user_cityId": "",
            "user_districtId": "",
            "user_id": "",
            "user_lat": "",
            "user_long": "",
            "user_postCode": "",
            "user_warehouseId": "",
            "variants": ""
        }
        
        # Tambahkan filter harga
        if price_min is not None or price_max is not None:
            filt = []
            if price_min is not None:
                filt.append(f"price_min={price_min}")
            if price_max is not None:
                filt.append(f"price_max={price_max}")
            param_str = "&".join([f"{k}={v}" for k, v in params.items()] + filt)
        else:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])

        # Body GraphQL
        graphql_query = {
            "operationName": "SearchProductQueryV4",
            "variables": {"params": param_str},
            "query": """
            query SearchProductQueryV4($params: String!) {
              ace_search_product_v4(params: $params) {
                header {
                  totalData
                  totalDataText
                  processTime
                  responseCode
                  errorMessage
                  additionalParams
                  keywordProcess
                  componentId
                }
                data {
                  products {
                    id
                    name
                    originalPrice
                    price
                    priceRange
                    imageUrl
                    rating
                    countReview
                    url
                    shop {
                      name
                      city
                    }
                    __typename
                  }
                }
              }
            }
            """
        }

        headers = {
            "authority": "gql.tokopedia.com",
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://www.tokopedia.com",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "sec-fetch-site": "same-site",
        }

        try:
            response = requests.post(TOKOPEDIA_API_URL, headers=headers, json=graphql_query, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            products = data.get("data", {}).get("ace_search_product_v4", {}).get("data", {}).get("products", [])
            
            if not products:
                print(f"  ⚠️ Tidak ada produk lagi di halaman {page}, berhenti.")
                break
            
            new_count = 0
            for p in products:
                product_id = p.get("id")
                if product_id in seen_ids:
                    continue
                    
                seen_ids.add(product_id)
                
                price = parse_price(p.get("price"))
                original_price = parse_price(p.get("originalPrice"))
                if original_price == 0:
                    original_price = None
                    
                image_url = p.get("imageUrl")
                local_image = download_image(image_url)
                
                rating = p.get("rating", 0)
                if rating is None:
                    rating = 0
                    
                review_count = p.get("countReview", 0)
                if review_count is None:
                    review_count = 0
                
                product_data = {
                    "id": product_id,
                    "name": p.get("name"),
                    "price": price,
                    "original_price": original_price,
                    "image_url": image_url,
                    "local_image": local_image,
                    "rating": rating,
                    "review_count": review_count,
                    "url": p.get("url"),
                    "shop_name": p.get("shop", {}).get("name"),
                    "shop_city": p.get("shop", {}).get("city"),
                    "category": query.lower(),
                    "last_updated": datetime.now().isoformat()
                }
                
                all_products.append(product_data)
                new_count += 1
            
            print(f"  ✅ Halaman {page}: {len(products)} produk ({new_count} baru)")
            
            if page < max_pages:
                time.sleep(1)  # Delay antar halaman
            
        except Exception as e:
            print(f"  ❌ Error di halaman {page}: {e}")
            break
    
    print(f"  📊 Total produk untuk '{query}': {len(all_products)}")
    return all_products

def save_products_to_json(products, filename=None):
    """
    Simpan produk ke file JSON
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tokopedia_products_latest.json"
    
    os.makedirs("data", exist_ok=True)
    filepath = os.path.join("data", filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    
    print(f"Data berhasil disimpan ke: {filepath}")
    return filepath

def save_products_to_excel(products, filename="tokopedia_products_latest.xlsx"):
    """
    Simpan produk ke file Excel
    """
    os.makedirs("data", exist_ok=True)
    filepath = os.path.join("data", filename)

    wb = Workbook()
    ws = wb.active
    ws.title = "Hardware Products"

    # Header
    headers = [
        "ID", "Nama Produk", "Kategori", "Harga (Rp)", "Harga Asli (Rp)", 
        "Rating (Bintang)", "Jumlah Review", "Toko", "Kota", 
        "URL Gambar", "Gambar Lokal", "URL Produk", "Terakhir Update"
    ]
    ws.append(headers)

    # Data rows
    for p in products:
        original_price = p.get("original_price")
        if original_price and original_price > 0:
            original_price_str = f"Rp {original_price:,}"
        else:
            original_price_str = "-"
            
        ws.append([
            p.get("id", "-"),
            p.get("name", "-"),
            p.get("category", "-").upper(),
            f"Rp {p.get('price', 0):,}",
            original_price_str,
            p.get("rating", 0),
            p.get("review_count", 0),
            p.get("shop_name", "-"),
            p.get("shop_city", "-"),
            p.get("image_url", "-"),
            p.get("local_image", "-"),
            p.get("url", "-"),
            p.get("last_updated", "-")
        ])

    wb.save(filepath)
    print(f"✅ Excel disimpan ke: {filepath}")
    return filepath

def load_products_from_json(filename):
    """
    Load produk dari file JSON
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            products = json.load(f)
            return products
    except FileNotFoundError:
        print(f"File {filename} tidak ditemukan")
        return []
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return []

def get_pc_components():
    print("\n" + "="*60)
    print("MENGAMBIL DATA KOMPONEN PC")
    print("="*60)
    
    pc_queries = [
        ("ram ddr4", "ram"),
        ("ram ddr5", "ram"),
        ("ssd m.2 nvme", "ssd"),
        ("ssd sata", "ssd"),
        ("hdd internal", "hdd"),
        ("processor intel", "cpu"),
        ("processor amd", "cpu"),
        ("vga nvidia", "gpu"),
        ("vga amd", "gpu"),
        ("motherboard intel", "motherboard"),
        ("motherboard amd", "motherboard"),
        ("cpu cooler", "cpu cooler"),
        ("power supply", "psu"),
        ("casing pc", "casing")
    ]
    
    all_components = []
    
    for query, category in pc_queries:
        print(f"\n🔄 Mengambil {category.upper()}: {query}")
        products = search_tokopedia(query, rows=100, max_pages=10)  # 100 × 10 = 1000 produk
        
        for product in products:
            product["component_type"] = category
            product["product_type"] = "pc_component"
        
        all_components.extend(products)
        print(f"✅ Berhasil: {len(products)} produk ({category})")
        
        # Delay antar kategori
        time.sleep(2)
    
    return all_components

def get_laptops():
    print("\n" + "="*60)
    print("MENGAMBIL DATA LAPTOP")
    print("="*60)
    
    laptop_queries = [
        ("laptop editing video", "editing"),
        ("laptop adobe premiere", "editing"),
        ("laptop programming", "programming"),
        ("laptop developer", "programming"),
        ("laptop gaming", "gaming"),
        ("laptop rtx", "gaming"),
        ("laptop office", "office"),
        ("laptop bisnis", "office"),
        ("laptop ultrabook", "office"),
        ("laptop thinkpad", "office")
    ]
    
    all_laptops = []
    
    for query, function in laptop_queries:
        print(f"\n🔄 Mengambil laptop {function.upper()}: {query}")
        products = search_tokopedia(query, rows=100, max_pages=10)  # 100 × 10 = 1000 produk
        
        for product in products:
            product["function"] = function
            product["product_type"] = "laptop"
        
        all_laptops.extend(products)
        print(f"✅ Berhasil: {len(products)} produk (fungsi: {function})")
        
        # Delay antar kategori
        time.sleep(2)
    
    return all_laptops

def filter_and_clean_products(products):
    """
    Filter dan bersihkan data produk
    """
    filtered = []
    seen_ids = set()
    
    for product in products:
        # Skip jika tidak ada harga atau harga 0
        if not product.get("price") or product["price"] == 0:
            continue
            
        # Skip jika sudah ada (based on ID)
        product_id = product.get("id")
        if product_id in seen_ids:
            continue
            
        seen_ids.add(product_id)
        
        # Pastikan rating ada
        if product.get("rating") is None:
            product["rating"] = 0
            
        # Pastikan review count ada
        if product.get("review_count") is None:
            product["review_count"] = 0
            
        filtered.append(product)
    
    return filtered

def analyze_products(products):
    """
    Analisis statistik produk
    """
    if not products:
        print("Tidak ada data untuk dianalisis")
        return
    
    print("\n" + "="*60)
    print("ANALISIS DATA PRODUK")
    print("="*60)
    
    # Kelompokkan berdasarkan tipe produk
    pc_components = [p for p in products if p.get("product_type") == "pc_component"]
    laptops = [p for p in products if p.get("product_type") == "laptop"]
    
    print(f"\n📊 TOTAL PRODUK: {len(products)}")
    print(f"• Komponen PC: {len(pc_components)}")
    print(f"• Laptop: {len(laptops)}")
    
    if pc_components:
        print(f"\n📦 KOMPONEN PC:")
        components_by_type = {}
        for p in pc_components:
            comp_type = p.get("component_type", "unknown")
            components_by_type[comp_type] = components_by_type.get(comp_type, 0) + 1
        
        for comp_type, count in sorted(components_by_type.items()):
            print(f"  • {comp_type.upper()}: {count} produk")
    
    if laptops:
        print(f"\n💻 LAPTOP:")
        laptops_by_function = {}
        for p in laptops:
            function = p.get("function", "unknown")
            laptops_by_function[function] = laptops_by_function.get(function, 0) + 1
        
        for function, count in sorted(laptops_by_function.items()):
            print(f"  • {function.upper()}: {count} produk")
    
    # Statistik harga
    if products:
        prices = [p.get("price", 0) for p in products if p.get("price")]
        if prices:
            avg_price = sum(prices) / len(prices)
            min_price = min(prices)
            max_price = max(prices)
            
            print(f"\n💰 STATISTIK HARGA:")
            print(f"  • Harga Rata-rata: Rp {avg_price:,.0f}")
            print(f"  • Harga Terendah: Rp {min_price:,.0f}")
            print(f"  • Harga Tertinggi: Rp {max_price:,.0f}")
    
    # Statistik rating
    if products:
        ratings = [p.get("rating", 0) for p in products if p.get("rating")]
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
            
            print(f"\n⭐ STATISTIK RATING:")
            print(f"  • Rating Rata-rata: {avg_rating:.2f}/5")
            
            # Hitung distribusi rating
            rating_dist = {1:0, 2:0, 3:0, 4:0, 5:0}
            for r in ratings:
                if r >= 4.5:
                    rating_dist[5] += 1
                elif r >= 3.5:
                    rating_dist[4] += 1
                elif r >= 2.5:
                    rating_dist[3] += 1
                elif r >= 1.5:
                    rating_dist[2] += 1
                else:
                    rating_dist[1] += 1
            
            print(f"  • Distribusi Rating:")
            for stars, count in sorted(rating_dist.items(), reverse=True):
                if count > 0:
                    percentage = (count / len(ratings)) * 100
                    print(f"    {stars} bintang: {count} produk ({percentage:.1f}%)")

def update_hardware_data():
    """
    Fungsi utama untuk update data hardware
    """
    print("="*60)
    print("MEMULAI UPDATE DATA HARDWARE")
    print("="*60)
    
    # Ambil data komponen PC
    pc_components = get_pc_components()
    
    # Ambil data laptop
    laptops = get_laptops()
    
    # Gabungkan semua data
    all_products = pc_components + laptops
    
    # Filter dan bersihkan data
    filtered_products = filter_and_clean_products(all_products)
    
    # Analisis data
    analyze_products(filtered_products)
    
    # Simpan data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Simpan ke JSON
    json_filename = f"tokopedia_products_latest.json"
    json_filepath = save_products_to_json(filtered_products, json_filename)
    
    # Simpan ke Excel
    excel_filename = f"tokopedia_products_latest.xlsx"
    excel_filepath = save_products_to_excel(filtered_products, excel_filename)
    
    print("\n" + "="*60)
    print("UPDATE SELESAI!")
    print("="*60)
    print(f"Total produk yang berhasil diambil: {len(filtered_products)}")
    print(f"JSON tersimpan di: {json_filepath}")
    print(f"Excel tersimpan di: {excel_filepath}")
    
    return filtered_products

def get_recommendations(budget, usage_type, product_type="all"):
    """
    Dapatkan rekomendasi berdasarkan budget dan tipe penggunaan
    
    Parameters:
    - budget: budget dalam Rupiah
    - usage_type: 'gaming', 'editing', 'programming', 'office', 'all'
    - product_type: 'pc_component', 'laptop', 'all'
    """
    # Load data terbaru
    data_files = [f for f in os.listdir("data") if f.startswith("tokopedia_products_latest") and f.endswith(".json")]
    if not data_files:
        print("Tidak ada data hardware yang ditemukan")
        return []
    
    latest_file = sorted(data_files)[-1]
    products = load_products_from_json(os.path.join("data", latest_file))
    
    if not products:
        print("Tidak ada produk yang dapat dimuat")
        return []
    
    # Filter berdasarkan tipe produk
    if product_type != "all":
        products = [p for p in products if p.get("product_type") == product_type]
    
    # Filter berdasarkan budget (range 70% - 130% dari budget)
    budget_min = budget * 0.7
    budget_max = budget * 1.3
    
    print(f"🔍 Mencari rekomendasi dengan:")
    print(f"   • Budget: Rp {budget:,}")
    print(f"   • Range: Rp {budget_min:,.0f} - Rp {budget_max:,.0f}")
    print(f"   • Tipe Produk: {product_type}")
    print(f"   • Penggunaan: {usage_type}")
    
    filtered_products = []
    for p in products:
        price = p.get('price', 0)
        if budget_min <= price <= budget_max:
            filtered_products.append(p)
    
    print(f"   • Ditemukan: {len(filtered_products)} produk dalam range budget")
    
    # Filter berdasarkan penggunaan jika bukan 'all'
    if usage_type != "all":
        usage_filtered = []
        
        if product_type == "laptop":
            # Untuk laptop, filter berdasarkan fungsi
            for p in filtered_products:
                if p.get("function") == usage_type:
                    usage_filtered.append(p)
        elif product_type == "pc_component":
            # Untuk komponen PC, prioritaskan berdasarkan usage
            usage_priority = {
                'gaming': ['gpu', 'cpu', 'ram', 'motherboard'],
                'editing': ['cpu', 'ram', 'gpu', 'ssd'],
                'programming': ['cpu', 'ram', 'ssd'],
                'office': ['cpu', 'ram', 'ssd']
            }
            
            priority_components = usage_priority.get(usage_type, [])
            for p in filtered_products:
                comp_type = p.get("component_type")
                if comp_type in priority_components:
                    usage_filtered.append(p)
        
        filtered_products = usage_filtered
        print(f"   • Setelah filter penggunaan '{usage_type}': {len(filtered_products)} produk")
    
    # Urutkan berdasarkan rating dan jumlah review
    filtered_products.sort(key=lambda x: (
        x.get('rating', 0) or 0, 
        x.get('review_count', 0) or 0,
        -x.get('price', 0)  # Harga lebih rendah lebih baik
    ), reverse=True)
    
    # Return top 15 recommendations
    recommendations = filtered_products[:15]
    
    print(f"\n🎯 REKOMENDASI FINAL: {len(recommendations)} produk")
    for i, rec in enumerate(recommendations[:5], 1):
        print(f"{i}. {rec.get('name', 'N/A')[:50]}...")
        print(f"   💰 Rp {rec.get('price', 0):,} | ⭐ {rec.get('rating', 0)}/5 | 📝 {rec.get('review_count', 0)} review")
    
    return recommendations

if __name__ == "__main__":
    # Update data hardware
    all_products = update_hardware_data()
    
    # Contoh penggunaan untuk rekomendasi
    print("\n" + "="*60)
    print("CONTOH REKOMENDASI:")
    print("="*60)
    
    # Contoh 1: Rekomendasi laptop gaming dengan budget 15 juta
    print("\n1. Rekomendasi Laptop Gaming (Rp 15.000.000):")
    gaming_laptops = get_recommendations(15000000, "gaming", "laptop")
    
    # Contoh 2: Rekomendasi komponen PC untuk editing dengan budget 10 juta
    print("\n2. Rekomendasi Komponen PC untuk Editing (Rp 10.000.000):")
    editing_components = get_recommendations(10000000, "editing", "pc_component")