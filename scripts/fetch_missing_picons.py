"""Lokalna baza pikon-zastepczych budowana z repo github.com/picons/picons.

Dla kanalow z naszych bukietow, ktorych nie ma w paczkach zet71, dobiera logo
z build-source/logos (prawdziwe logotypy z przezroczystoscia; warianty .light
sa czytelniejsze na ciemnej skorce), w razie potrzeby renderuje SVG przez
qlmanage (macOS), wpasowuje w kanwy 220x132 i 400x170 i zapisuje do bazy:
  <baza>/picon/<nazwa>.png     (220x132)
  <baza>/zzpicon/<nazwa>.png   (400x170)
make_picons.py uzywa tej bazy jako ostatniego fallbacku.

UWAGA: linki /jpg/ na stronach KingOfSat to zrzuty z anteny (zap), NIE logotypy
- nie nadaja sie na pikony.

Wymaga Pillow (pip install pillow).

Uzycie: python3 scripts/fetch_missing_picons.py <katalog_settings> <names_db.json> <katalog_bazy> [bukiet.tv ...]
"""
from __future__ import annotations

import difflib
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from make_picons import (DEFAULT_BOUQUETS, RAW_BASE, SUBDIR, Wanted, candidate_names,
                         collect_wanted, digits_of, http_get, ipk_pngs, newest_packages)
from make_picons import pick_png as pick_from_pngs

TREE_URL = "https://api.github.com/repos/picons/picons/git/trees/master?recursive=1"
LOGOS_RAW = "https://raw.githubusercontent.com/picons/picons/master/"
LOGO_PATH_RE = re.compile(r"build-source/logos/([a-z0-9]+)\.(default|light)\.(png|svg)$")
VARIANT_ORDER = ["light.png", "default.png", "light.svg", "default.svg"]
CANVAS = {"picon": (220, 132), "zzpicon": (400, 170)}
MARGIN = 0.06
WHITE_THRESHOLD = 244


def logo_index() -> dict[str, dict[str, str]]:
    tree = json.loads(http_get(TREE_URL))
    index: dict[str, dict[str, str]] = {}
    for item in tree["tree"]:
        m = LOGO_PATH_RE.fullmatch(item["path"])
        if m:
            stem, variant, ext = m.groups()
            index.setdefault(stem, {})[f"{variant}.{ext}"] = item["path"]
    return index


def pick_stem(index: dict[str, dict[str, str]], picon_name: str, aliases: list[str]) -> str | None:
    for name in [picon_name] + aliases:
        for candidate in candidate_names(name):
            if candidate in index:
                return candidate
    close = difflib.get_close_matches(picon_name, list(index), n=1, cutoff=0.87)
    if close and close[0][:2] == picon_name[:2] and digits_of(close[0]) == digits_of(picon_name):
        return close[0]
    return None


def svg_to_png(svg: bytes) -> bytes | None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "logo.svg"
        src.write_bytes(svg)
        subprocess.run(["qlmanage", "-t", "-s", "800", str(src), "-o", tmp],
                       capture_output=True, timeout=60, check=False)
        rendered = Path(tmp) / "logo.svg.png"
        return rendered.read_bytes() if rendered.exists() else None


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


def fetch_logo(variants: dict[str, str]) -> bytes | None:
    for variant in VARIANT_ORDER:
        if variant not in variants:
            continue
        raw = http_get(LOGOS_RAW + variants[variant])
        if variant.endswith(".svg"):
            raw = svg_to_png(raw)
            if raw is None:
                continue
        return raw
    return None


def missing_channels(settings_dir: Path, names_db_path: Path, bouquets: list[str]) -> list[Wanted]:
    names_db = json.loads(names_db_path.read_text(encoding="utf-8"))
    wanted = collect_wanted(settings_dir, bouquets, names_db)
    pngs_union: dict[str, bytes] = {}
    for size, pkg_name in sorted(newest_packages().items()):
        print(f"pobieram {pkg_name} (do ustalenia brakow) ...")
        pngs_union.update(ipk_pngs(http_get(RAW_BASE + pkg_name)))
    return [w for w in wanted if pick_from_pngs(pngs_union, w.picon_name, w.aliases) is None]


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    settings_dir, names_db_path, base_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    bouquets = sys.argv[4:] or DEFAULT_BOUQUETS
    missing = missing_channels(settings_dir, names_db_path, bouquets)
    print(f"brakujacych kanalow: {len(missing)}")
    index = logo_index()
    print(f"logotypow w picons/picons: {len(index)}")
    for sub in SUBDIR.values():
        (base_dir / sub).mkdir(parents=True, exist_ok=True)
    got = still = 0
    for w in missing:
        stem = pick_stem(index, w.picon_name, w.aliases)
        logo = fetch_logo(index[stem]) if stem else None
        if logo is None:
            still += 1
            print(f"  BRAK LOGA: {w.channel} ({w.picon_name}) [{w.bouquet}]")
            continue
        for sub, size in CANVAS.items():
            (base_dir / sub / f"{w.picon_name}.png").write_bytes(to_picon(logo, size))
        got += 1
        print(f"  OK: {w.channel} <- {stem} ({next(v for v in VARIANT_ORDER if v in index[stem])})")
    print(f"zapisano {got} pikon w {base_dir}, bez loga pozostalo {still}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
