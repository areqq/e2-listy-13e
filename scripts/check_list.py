"""Walidacja spojnosci listy Enigma2: martwe referencje, brakujace transpondery,
niezgodne typy uslug i duplikaty w bukietach.

Uzycie: python3 scripts/check_list.py <katalog_settings> [nazwa_bukietu.tv ...]
Kod wyjscia: 0 = czysto, 1 = znaleziono problemy.
"""
from __future__ import annotations

import sys
from pathlib import Path

from e2lib import Lamedb, ServiceKey, list_bouquets, load_bouquet, load_lamedb


def check_bouquet(path: Path, db: Lamedb) -> list[str]:
    name, entries = load_bouquet(path)
    problems: list[str] = []
    seen: dict[ServiceKey, int] = {}
    for e in entries:
        if e.is_marker or e.key is None:
            continue
        svc = db.services.get(e.key)
        where = f"poz {e.position:3d} (linia {e.line_no})"
        if svc is None:
            problems.append(f"{where}  MARTWY WPIS: {e.raw[9:]} - brak uslugi w lamedb")
            continue
        if db.transponder_for(e.key) is None:
            problems.append(f"{where}  {svc.name}: brak transpondera {e.key.ns:08X}:{e.key.tsid:04X}:{e.key.onid:04X}")
        if svc.stype != e.stype:
            problems.append(f"{where}  {svc.name}: typ w bukiecie {e.stype} != lamedb {svc.stype}")
        if e.key in seen:
            problems.append(f"{where}  DUPLIKAT {svc.name} (pierwszy raz na poz {seen[e.key]})")
        else:
            seen[e.key] = e.position
    header = f"=== {name} ({path.name}): {len(seen)} kanalow"
    print(header + (f", PROBLEMY: {len(problems)}" if problems else ", OK"))
    for p in problems:
        print("   " + p)
    return problems


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    settings_dir = Path(sys.argv[1])
    db = load_lamedb(settings_dir / "lamedb")
    print(f"lamedb: {len(db.transponders)} transponderow, {len(db.services)} uslug")
    targets = [settings_dir / b for b in sys.argv[2:]] if len(sys.argv) > 2 else list_bouquets(settings_dir)
    total = sum(len(check_bouquet(p, db)) for p in targets)
    print(f"\nRazem problemow: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
