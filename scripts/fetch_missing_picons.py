"""Lokalna baza pikon-zastepczych budowana z logotypow KingOfSat.

Dla kanalow z naszych bukietow, ktorych nie ma w paczkach zet71, pobiera logo
ze stron KingOfSat (przypisane po SID:TSID:ONID, bez zgadywania nazw), zdejmuje
biale tlo, wpasowuje w kanwy 220x132 i 400x170 i zapisuje do lokalnej bazy:
  <baza>/picon/<nazwa>.png     (220x132)
  <baza>/zzpicon/<nazwa>.png   (400x170)
make_picons.py uzywa tej bazy jako ostatniego fallbacku.

Wymaga Pillow (pip install pillow).

Uzycie: python3 scripts/fetch_missing_picons.py <katalog_settings> <names_db.json> <katalog_bazy> [bukiet.tv ...]
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image

from build_names_db import FREQ_HEADER_RE, KOS_PAGES, USER_AGENT
from make_picons import DEFAULT_BOUQUETS, SUBDIR, Wanted, collect_wanted, http_get, ipk_pngs, newest_packages, pick_png, RAW_BASE

KOS_BASE = "https://pl.kingofsat.net"
ROW_RE = re.compile(r'<tr data-channel-id.*?</tr>', re.S)
LOGO_RE = re.compile(r'href="(/jpg/[^"]+)" class="image-link"')
SID_RE = re.compile(r'<td class="s">(\d{1,5})</td>')
CANVAS = {"picon": (220, 132), "zzpicon": (400, 170)}
MARGIN = 0.06
WHITE_THRESHOLD = 244


def kingofsat_logo_map() -> dict[str, str]:
    logos: dict[str, str] = {}
    for url in KOS_PAGES:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        for block in page.split("data-frequency-id")[1:]:
            header = FREQ_HEADER_RE.search(block)
            if header is None:
                continue
            nid, tid = int(header.group(3)), int(header.group(4))
            for row in ROW_RE.findall("<tr data-channel-id" + block):
                sid_m, logo_m = SID_RE.search(row), LOGO_RE.search(row)
                if sid_m and logo_m:
                    logos[f"{int(sid_m.group(1)):04x}:{tid:04x}:{nid:04x}"] = KOS_BASE + logo_m.group(1)
    return logos


def to_picon(raw: bytes, size: tuple[int, int]) -> bytes:
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    has_alpha = img.getextrema()[3][0] < 255
    pixels = img.load()
    if not has_alpha:
        for y in range(img.height):
            for x in range(img.width):
                r, g, b, _ = pixels[x, y]
                if r >= WHITE_THRESHOLD and g >= WHITE_THRESHOLD and b >= WHITE_THRESHOLD:
                    pixels[x, y] = (r, g, b, 0)
    box = img.getbbox()
    if box:
        img = img.crop(box)
    max_w = int(size[0] * (1 - 2 * MARGIN))
    max_h = int(size[1] * (1 - 2 * MARGIN))
    scale = min(max_w / img.width, max_h / img.height)
    img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2), img)
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue()


def missing_channels(settings_dir: Path, names_db_path: Path, bouquets: list[str]) -> list[Wanted]:
    names_db = json.loads(names_db_path.read_text(encoding="utf-8"))
    wanted = collect_wanted(settings_dir, bouquets, names_db)
    pngs_union: dict[str, bytes] = {}
    for size, pkg_name in sorted(newest_packages().items()):
        print(f"pobieram {pkg_name} (do ustalenia brakow) ...")
        pngs_union.update(ipk_pngs(http_get(RAW_BASE + pkg_name)))
    return [w for w in wanted if pick_png(pngs_union, w.picon_name, w.aliases) is None]


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    settings_dir, names_db_path, base_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    bouquets = sys.argv[4:] or DEFAULT_BOUQUETS
    missing = missing_channels(settings_dir, names_db_path, bouquets)
    print(f"brakujacych kanalow: {len(missing)}")
    logos = kingofsat_logo_map()
    print(f"logotypow na KingOfSat: {len(logos)}")
    for sub in SUBDIR.values():
        (base_dir / sub).mkdir(parents=True, exist_ok=True)
    got = still = 0
    for w in missing:
        sid, tsid, onid = w.ref.split("_")[3:6]
        key = f"{int(sid, 16):04x}:{int(tsid, 16):04x}:{int(onid, 16):04x}"
        url = logos.get(key)
        if url is None:
            still += 1
            print(f"  BRAK LOGA: {w.channel} [{w.bouquet}]")
            continue
        try:
            jpeg = http_get(url)
        except OSError as e:
            still += 1
            print(f"  BLAD POBIERANIA: {w.channel} {url} ({e})")
            continue
        for sub, size in CANVAS.items():
            (base_dir / sub / f"{w.picon_name}.png").write_bytes(to_picon(jpeg, size))
        got += 1
        print(f"  OK: {w.channel} <- {url}")
    print(f"zapisano {got} pikon w {base_dir}, bez loga pozostalo {still}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
