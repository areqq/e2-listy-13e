"""Aktualizacja repozytorium pikon (store picons/) z paczek zet71.

Nasze repo trzyma pikony na stale - to zrodlo budowy tarow (make_picons dziala
offline). Ten skrypt tylko odswieza/dokłada do store pikony dla kanalow z naszych
bukietow, biorac je z najnowszych paczek zet71. Dzieki temu jesteśmy odporni na
zniknięcie zrodla: raz pobrane pikony zostaja w repo. Czego zet71 nie ma - dobiera
scripts/fetch_missing_picons.py (github.com/picons/picons).

Zrodla:
  domyslnie        - paczki ipk z eeRepo j00zeka (aktualizowane rzadziej),
  --dir <katalog>  - wypakowana paczka „Nazwy - 8bit" z forum (podkatalogi 220x132/, 400x170/).

Zapisuje/aktualizuje pliki tylko gdy nowe lub zmienione (czytelne diffy w git).
Gdy paczka dopasuje kanalowi inny plik niz dotychczasowy (np. zet71 zmienil nazwe
z axnhd na axn), stary plik ze store jest usuwany - o ile nie uzywa go inny kanal.

Uzycie: python3 scripts/update_picons.py <katalog_settings> <store> [names_db.json] [--dir <katalog>] [bukiet.tv ...]
"""
from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from make_picons import (DEFAULT_BOUQUETS, RAW_BASE, SUBDIR, Wanted, collect_streams,
                         collect_wanted, http_get, ipk_pngs, newest_packages, pick_png)


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    removed: int = 0


def eerepo_packages() -> Iterator[tuple[str, str, dict[str, bytes]]]:
    for size, pkg_name in sorted(newest_packages().items()):
        yield size, pkg_name, ipk_pngs(http_get(RAW_BASE + pkg_name))


def dir_packages(pack_dir: Path) -> Iterator[tuple[str, str, dict[str, bytes]]]:
    for size in sorted(SUBDIR):
        size_dir = next((d for d in pack_dir.rglob(size) if d.is_dir()), None)
        if size_dir is None:
            raise SystemExit(f"brak podkatalogu {size} w {pack_dir}")
        yield size, str(size_dir), {f.stem: f.read_bytes() for f in size_dir.glob("*.png")}


def sync_store(target: Path, pngs: dict[str, bytes], wanted: list[Wanted]) -> SyncResult:
    store = {f.stem for f in target.glob("*.png")}
    result = SyncResult()
    superseded: set[str] = set()
    kept: set[str] = set()
    for w in wanted:
        current = pick_png(dict.fromkeys(store, b""), w.picon_name, w.aliases)
        found = pick_png(pngs, w.picon_name, w.aliases)
        if found is None:
            if current is not None:
                kept.add(current)
            continue
        kept.add(found)
        if current is not None and current != found:
            superseded.add(current)
        dest = target / f"{found}.png"
        if not dest.exists():
            dest.write_bytes(pngs[found])
            print(f"  nowy: {found}")
            result.added += 1
        elif dest.read_bytes() != pngs[found]:
            dest.write_bytes(pngs[found])
            print(f"  zmieniony: {found}")
            result.updated += 1
    for name in sorted(superseded - kept):
        (target / f"{name}.png").unlink()
        print(f"  usuniety (zastapiony): {name}")
        result.removed += 1
    return result


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
    pack_dir: Path | None = None
    if rest[:1] == ["--dir"]:
        if len(rest) < 2:
            print(__doc__)
            return 2
        pack_dir = Path(rest[1])
        rest = rest[2:]
    bouquets = rest or DEFAULT_BOUQUETS
    wanted = collect_wanted(settings_dir, bouquets, names_db) + collect_streams(settings_dir, bouquets)
    print(f"kanalow do pokrycia: {len(wanted)}")

    packages = dir_packages(pack_dir) if pack_dir else eerepo_packages()
    for size, label, pngs in packages:
        sub = SUBDIR[size]
        print(f"zet71 {label} -> {sub}/")
        target = store_dir / sub
        target.mkdir(parents=True, exist_ok=True)
        r = sync_store(target, pngs, wanted)
        print(f"  dodane: {r.added}, zaktualizowane: {r.updated}, usuniete: {r.removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
