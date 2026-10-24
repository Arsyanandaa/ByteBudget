"""
utils.py
Helper utilities untuk tokopedia-scraper:
- user agent rotation
- random delays & backoff
- simple retry decorator
- penyimpanan (CSV/JSON/SQLite)
- helpers parsing harga
- logger sederhana
"""

import random
import time
import csv
import json
import sqlite3
import logging
import functools
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import pandas as pd

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


# --------------------------
# Logger
# --------------------------
def init_logger(name: str = "tokopedia_scraper", level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        ch = logging.StreamHandler()
        ch.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S")
        )
        logger.addHandler(ch)
    return logger


logger = init_logger()

# --------------------------
# User agents (perlu ditambah kalau produksi)
# --------------------------
USER_AGENTS = [
    # Desktop Chrome / Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/117.0.0.0 Safari/537.36",
    # Safari macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)"
    " Version/16.1 Safari/605.1.15",
    # Mobile Chrome
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/116.0.5845.96 Mobile Safari/537.36",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:116.0) Gecko/20100101 Firefox/116.0",
]


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


# --------------------------
# Delay & rate-limit helpers
# --------------------------
def random_delay(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
    """Jeda acak antara request untuk mengurangi risiko terdeteksi."""
    sec = random.uniform(min_sec, max_sec)
    logger.debug(f"Sleeping for {sec:.2f}s")
    time.sleep(sec)


# --------------------------
# Retry decorator with backoff
# --------------------------
def retry(
    tries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    allowed_exceptions: tuple = (Exception,),
    logger: Optional[logging.Logger] = None,
):
    """
    Dekorator retry sederhana.
    contoh:
      @retry(tries=4, delay=1)
      def fn(...): ...
    """

    def deco(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or logging.getLogger(func.__module__)
            mdelay = delay
            for attempt in range(1, tries + 1):
                try:
                    return func(*args, **kwargs)
                except allowed_exceptions as e:
                    if attempt == tries:
                        _logger.error(
                            f"Function {func.__name__} failed after {tries} attempts: {e}"
                        )
                        raise
                    _logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{tries}): {e}. Retrying in {mdelay:.1f}s"
                    )
                    time.sleep(mdelay)
                    mdelay *= backoff

        return wrapper

    return deco


# --------------------------
# Parsing helpers
# --------------------------
PRICE_RE = re.compile(r"(Rp[\s\.0-9]+)")


def extract_price(text: str) -> Optional[str]:
    """Cari pola harga 'Rp...'. Kembalikan string mentahnya atau None."""
    if not text:
        return None
    m = PRICE_RE.search(text)
    return m.group(1) if m else None


def normalize_price_to_int(price_str: str) -> Optional[int]:
    """
    Convert 'Rp 1.234.000' or 'Rp1.234.000' -> 1234000 (int).
    Jika gagal, kembalikan None.
    """
    if not price_str:
        return None
    try:
        cleaned = re.sub(r"[^\d]", "", price_str)
        return int(cleaned) if cleaned else None
    except Exception:
        return None


# --------------------------
# Penyimpanan: CSV / JSON / SQLite
# --------------------------
def save_csv(
    items: Iterable[Dict[str, Any]],
    out_path: Optional[Path] = None,
    encoding: str = "utf-8",
) -> Path:
    df = pd.DataFrame(items)
    if out_path is None:
        out_path = OUTPUT_DIR / f"tokopedia_{int(time.time())}.csv"
    df.to_csv(out_path, index=False, encoding=encoding)
    logger.info(f"Saved CSV -> {out_path}")
    return out_path


def save_json(
    items: Iterable[Dict[str, Any]],
    out_path: Optional[Path] = None,
    ensure_ascii: bool = False,
) -> Path:
    if out_path is None:
        out_path = OUTPUT_DIR / f"tokopedia_{int(time.time())}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(list(items), f, ensure_ascii=ensure_ascii, indent=2)
    logger.info(f"Saved JSON -> {out_path}")
    return out_path


def save_sqlite(
    items: Iterable[Dict[str, Any]],
    db_path: Optional[Path] = None,
    table_name: str = "products",
) -> Path:
    if db_path is None:
        db_path = OUTPUT_DIR / "tokopedia.sqlite"
    df = pd.DataFrame(items)
    conn = sqlite3.connect(str(db_path))
    df.to_sql(table_name, conn, if_exists="append", index=False)
    conn.close()
    logger.info(f"Saved to SQLite -> {db_path} (table: {table_name})")
    return db_path


# --------------------------
# Playwright context options helper
# --------------------------
def build_playwright_context_options(
    proxy: Optional[Dict[str, str]] = None, user_agent: Optional[str] = None
) -> Dict:
    """
    Kembalikan opsi untuk browser.new_context(...) di Playwright.
    Contoh proxy: {"server": "http://host:port", "username": "...", "password": "..."}
    """
    opts: Dict[str, Any] = {
        # bisa ditambah: viewport, locale, timezone_id, etc.
        "java_script_enabled": True,
    }
    if user_agent:
        opts["user_agent"] = user_agent
    if proxy:
        opts["proxy"] = proxy
    return opts


# --------------------------
# Small utilities
# --------------------------
def ensure_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]

