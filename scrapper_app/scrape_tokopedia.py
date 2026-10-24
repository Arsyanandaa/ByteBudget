import os
os.environ['PLAYWRIGHT_EXPERIMENTAL_NO_ASYNCIO'] = '1'

import argparse
import json # Pastikan ini di-import
import time
from urllib.parse import quote_plus
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
# Hapus save_csv dan save_json dari utils
from utils import (
    logger,
    random_delay,
    retry,
    get_random_user_agent,
    build_playwright_context_options,
)

BASE_SEARCH_URL = "https://www.tokopedia.com/search?st=product&q={q}"
# Baris ini tidak lagi terpakai, bisa dihapus atau diabaikan
# OUTPUT_DIR = Path("output")
# OUTPUT_DIR.mkdir(exist_ok=True)


def fallback_parse_cards(soup):
    products = []
    cards = soup.select("div.css-5wh65g")

    for c in cards:
        a_tag = c.find("a", href=True)
        link = a_tag["href"] if a_tag else None
        name_tag = c.select_one(".SzILjt4fxHUFNVT48ZPhHA\\=\\= span")
        name = name_tag.get_text(strip=True) if name_tag else None
        price_tag = c.select_one(".urMOIDHH7I0Iy1Dv2oFaNw\\=\\=")
        price = price_tag.get_text(strip=True) if price_tag else None
        shop_block = c.select_one(".ljZNQLe6R-7wAWexijt7lA\\=\\=")
        shop, location = None, None
        if shop_block:
            spans = shop_block.find_all("span")
            if len(spans) >= 2:
                shop = spans[0].get_text(strip=True)
                location = spans[1].get_text(strip=True)
        rating_tag = c.select_one(".c7W9YYbRQuC29\\+GfsfRTEA\\=\\= span")
        rating = rating_tag.get_text(strip=True) if rating_tag else None
        sold_tag = c.select_one(".u6SfjDD2WiBlNW7zHmzRhQ\\=\\=")
        sold = sold_tag.get_text(strip=True) if sold_tag else None
        if name and price:
            products.append({
                "name": name,
                "price": price,
                "shop": shop,
                "location": location,
                "rating": rating,
                "sold": sold,
                "link": link,
            })
    return products


@retry(tries=3, delay=2, backoff=1.8, logger=logger)
def scrape_query(query, headless=True, max_clicks=25, delay_range=(2.0, 4.0)):
    query_enc = quote_plus(query)
    results = []
    seen_links = set()

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=headless)
    context = browser.new_context(**build_playwright_context_options(user_agent=get_random_user_agent()))
    page = context.new_page()

    url = BASE_SEARCH_URL.format(q=query_enc)
    logger.info(f"Memuat: {url}")
    page.goto(url, timeout=60000)
    page.wait_for_load_state("networkidle")

    prev_count = 0
    for i in range(max_clicks):
        # Scroll pakai JS agar trigger event scroll Tokopedia
        page.evaluate("""
            window.scrollTo(0, document.body.scrollHeight);
            window.dispatchEvent(new Event('scroll'));
        """)
        time.sleep(3)

        # Selector dinamis untuk tombol “Muat Lebih Banyak”
        button = None
        for selector in [
            'button:has-text("Muat Lebih Banyak")',
            'button:has-text("Tampilkan lebih banyak")',
            'button:has-text("Lihat lebih banyak")',
            'button.css-1turmok-unf-btn',
            'button[data-unify="Button"] >> text=Muat Lebih Banyak'
        ]:
            try:
                btn = page.locator(selector)
                if btn and btn.is_visible():
                    button = btn
                    break
            except Exception:
                continue

        if button:
            try:
                button.click(timeout=5000)
                logger.info(f"[{i+1}/{max_clicks}] Klik tombol 'Muat Lebih Banyak'")
                time.sleep(5)
                page.wait_for_load_state("networkidle")
            except Exception as e:
                logger.warning(f"Gagal klik tombol: {e}")
                break
        else:
            logger.info(f"Tidak menemukan tombol di iterasi {i+1}. Mungkin semua produk sudah tampil.")
            break

        # Parse halaman
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        cards = fallback_parse_cards(soup)

        new_count = 0
        for card in cards:
            link = card.get("link")
            if link and link not in seen_links:
                seen_links.add(link)
                results.append(card)
                new_count += 1

        logger.info(f"Iterasi ke-{i+1} → total {len(results)} produk unik (baru: {new_count})")

        if len(results) == prev_count:
            logger.info("Tidak ada tambahan produk baru, berhenti.")
            break

        prev_count = len(results)
        random_delay(*delay_range)

    browser.close()
    p.stop()
    return results


# FUNGSI save_results YANG LAMA DIHAPUS DI SINI

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Tokopedia (auto scroll + klik 'Muat Lebih Banyak').")
    parser.add_argument("--query", "-q", required=True, help="Kata kunci pencarian (misal: 'ram 8gb')")
    parser.add_argument("--clicks", "-c", type=int, default=25, help="Jumlah klik maksimal (default: 25)")
    parser.add_argument("--headless", action="store_true", help="Jalankan dalam mode headless")

    args = parser.parse_args()

    logger.info("Memulai scraping Tokopedia...")
    data = scrape_query(
        args.query,
        headless=args.headless,
        max_clicks=args.clicks,
    )
    logger.info(f"Jumlah item ditemukan: {len(data)}")

    # ==========================================================
    # KODE BARU UNTUK MENYIMPAN KE JSON STATIS DI ROOT PROJECT
    # ==========================================================
    
    # Path("..") menunjuk ke folder Project-Joki-Web, sejajar dengan index.html
    # Karena scrapper_app ada di dalam Project-Joki-Web, kita naik 1 level ke atas
    OUTPUT_FILE = Path("..") / "data_tokped.json" 
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        # Menyimpan data hasil scraping ke file JSON
        json.dump(data, f, indent=4, ensure_ascii=False)
        
    logger.info(f"Hasil berhasil disimpan ke: {OUTPUT_FILE}")
    
    # ==========================================================
    
    logger.info("Selesai ✅")