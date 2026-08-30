"""Synchronizacja typow uslug w bukietach z lamedb (naprawia zla ikonke SD/HD).

Uzycie: python3 scripts/fix_types.py <katalog_settings>
"""
from __future__ import annotations

import sys
from pathlib import Path

from e2lib import ServiceKey, list_bouquets, load_lamedb


def fix_bouquet(path: Path, services: dict[ServiceKey, object]) -> int:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    fixed = 0
    for i, line in enumerate(lines):
        if not line.startswith("#SERVICE 1:0:"):
            continue
        parts = line[len("#SERVICE "):].split(":")
        key = ServiceKey(sid=int(parts[3], 16), tsid=int(parts[4], 16), onid=int(parts[5], 16), ns=int(parts[6], 16))
        svc = services.get(key)
        if svc is None or int(parts[2], 16) == svc.stype:
            continue
        parts[2] = f"{svc.stype:X}"
        lines[i] = "#SERVICE " + ":".join(parts)
        fixed += 1
        print(f"  {path.name} linia {i + 1}: {svc.name} typ -> {svc.stype}")
    if fixed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fixed


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    settings_dir = Path(sys.argv[1])
    db = load_lamedb(settings_dir / "lamedb")
    total = sum(fix_bouquet(p, db.services) for p in list_bouquets(settings_dir))
    print(f"Poprawiono typow: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
