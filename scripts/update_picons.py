"""Aktualizacja repozytorium pikon (store picons/) z paczek zet71 j00zka.

Nasze repo trzyma pikony na stale - to zrodlo budowy tarow (make_picons dziala
offline). Ten skrypt tylko odswieza/dokłada do store pikony dla kanalow z naszych
bukietow, biorac je z najnowszych paczek zet71. Dzieki temu jesteśmy odporni na
zniknięcie zrodla: raz pobrane pikony zostaja w repo. Czego zet71 nie ma - dobiera
scripts/fetch_missing_picons.py (github.com/picons/picons).

Zapisuje/aktualizuje pliki tylko gdy nowe lub zmienione (czytelne diffy w git).

Uzycie: python3 scripts/update_picons.py <katalog_settings> <store> [names_db.json] [bukiet.tv ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from make_picons import (DEFAULT_BOUQUETS, RAW_BASE, SUBDIR, collect_streams,
                         collect_wanted, http_get, ipk_pngs, newest_packages, pick_png)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    settings_dir = Path(sys.argv[1])
    store_dir = Path(sys.argv[2])
    rest = sys.argv[3:]
    names_db: dict[str, dict[str, object]] = {}
    if rest and rest[0].endswith(".json"):
        names_db = json.loads(Path(rest[0]).read_text(encoding="utf-8"))
        rest = rest[1:]
    bouquets = rest or DEFAULT_BOUQUETS
    wanted = collect_wanted(settings_dir, bouquets, names_db) + collect_streams(settings_dir, bouquets)
    print(f"kanalow do pokrycia: {len(wanted)}")

    for size, pkg_name in sorted(newest_packages().items()):
        sub = SUBDIR[size]
        print(f"zet71 {pkg_name} -> {sub}/")
        pngs = ipk_pngs(http_get(RAW_BASE + pkg_name))
        target = store_dir / sub
        target.mkdir(parents=True, exist_ok=True)
        added = updated = 0
        for w in wanted:
            found = pick_png(pngs, w.picon_name, w.aliases)
            if found is None:
                continue
            dest = target / f"{found}.png"
            data = pngs[found]
            if not dest.exists():
                dest.write_bytes(data)
                added += 1
            elif dest.read_bytes() != data:
                dest.write_bytes(data)
                updated += 1
        print(f"  dodane: {added}, zaktualizowane: {updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
