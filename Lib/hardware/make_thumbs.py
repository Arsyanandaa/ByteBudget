import os
import re
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "data", "images")
DST = os.path.join(BASE, "thumbs")
JSON_PATH = os.path.join(BASE, "data", "tokopedia_products_latest.json")
MAX_SIZE = 160
QUALITY = 60

os.makedirs(DST, exist_ok=True)

with open(JSON_PATH, encoding="utf-8") as f:
    raw = f.read()

names = set()
for value in re.findall(r'"local_image"\s*:\s*"([^"]*)"', raw):
    name = os.path.basename(value.replace("\\\\", "/").replace("\\", "/"))
    if name:
        names.add(name)

print(f"Gambar yang dipakai di JSON: {len(names)}")

ok = missing = failed = 0
for i, name in enumerate(sorted(names), 1):
    src = os.path.join(SRC, name)
    dst = os.path.join(DST, os.path.splitext(name)[0] + ".jpg")

    if os.path.exists(dst):
        ok += 1
    elif not os.path.isfile(src):
        missing += 1
    else:
        try:
            with Image.open(src) as im:
                im.thumbnail((MAX_SIZE, MAX_SIZE))
                if im.mode in ("RGBA", "LA", "P"):
                    im = im.convert("RGBA")
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.split()[-1])
                    im = bg
                elif im.mode != "RGB":
                    im = im.convert("RGB")
                im.save(dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)
            ok += 1
        except Exception as e:
            failed += 1
            print(f"Gagal: {name} ({e})")

    if i % 1000 == 0:
        print(f"{i}/{len(names)} diproses")

total = sum(os.path.getsize(os.path.join(DST, f)) for f in os.listdir(DST))
print(f"Selesai: {ok} berhasil, {missing} file asli tidak ditemukan, {failed} gagal")
print(f"Total ukuran folder thumbs: {total / 1024 / 1024:.1f} MB")