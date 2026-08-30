"""Zastosowanie przenosin kanalow do listy Enigma2 wg pliku JSON.

Format pliku (hex bez 0x; onid/ns opcjonalne, domyslnie 013E/00820000):
{
  "add_services": [
    {"sid": "3ACE", "tsid": "0514", "type": 25, "name": "Canal+ Sport 2 HD", "provider": "Canal+"}
  ],
  "rename_services": [
    {"sid": "106C", "tsid": "2260", "new_name": "BarLume Collection HD"}
  ],
  "targets": [
    {"bouquet": "userbouquet.dbe00.tv",
     "moves": [
       {"name": "TVP Kultura HD", "old_sid": "3D59", "old_tsid": "2C88", "new_sid": "32D7", "new_tsid": "0190"}
     ]}
  ]
}

Dzialanie: dopisuje brakujace uslugi do lamedb, podmienia stare referencje
w bukiecie na nowe (kanal zostaje na swojej pozycji; typ uslugi brany z lamedb),
a potem usuwa z bukietu pozniejsze duplikaty tych samych referencji.

Uzycie: python3 scripts/apply_moves.py <katalog_settings> <moves.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from e2lib import Lamedb, ServiceKey, load_lamedb

DEFAULT_ONID = "013E"
DEFAULT_NS = "00820000"


def add_services(lamedb_path: Path, additions: list[dict[str, object]]) -> int:
    text = lamedb_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    end_idx = max(i for i, l in enumerate(lines) if l.strip() == "end")
    added = 0
    for svc in additions:
        sid = str(svc["sid"]).lower()
        tsid = str(svc["tsid"]).lower().zfill(4)
        onid = str(svc.get("onid", DEFAULT_ONID)).lower().zfill(4)
        ns = str(svc.get("ns", DEFAULT_NS)).lower().zfill(8)
        ref_line = f"{sid.zfill(4)}:{ns}:{tsid}:{onid}:{int(str(svc['type']))}:0"
        if f"{sid.zfill(4)}:{ns}:{tsid}:{onid}:" in text:
            print(f"  lamedb: {svc['name']} juz istnieje - pomijam")
            continue
        lines.insert(end_idx, f"{ref_line}\n{svc['name']}\np:{svc['provider']},f:01\n")
        end_idx += 1
        added += 1
        print(f"  lamedb: dopisano {svc['name']} ({ref_line})")
    lamedb_path.write_text("".join(lines), encoding="utf-8")
    return added


def rename_services(lamedb_path: Path, renames: list[dict[str, object]]) -> None:
    lines = lamedb_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for ren in renames:
        prefix = f"{str(ren['sid']).lower().zfill(4)}:"
        tsid = str(ren["tsid"]).lower().zfill(4)
        for i, line in enumerate(lines):
            if line.startswith(prefix) and line.split(":")[2] == tsid:
                print(f"  lamedb: zmiana nazwy '{lines[i + 1]}' -> '{ren['new_name']}'")
                lines[i + 1] = str(ren["new_name"])
                break
        else:
            print(f"  UWAGA: uslugi {ren['sid']}:{ren['tsid']} nie ma w lamedb - nazwa bez zmian")
    lamedb_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ref_of(line: str) -> tuple[int, int] | None:
    if not line.startswith("#SERVICE 1:0:"):
        return None
    parts = line[len("#SERVICE "):].split(":")
    return int(parts[3], 16), int(parts[4], 16)


def apply_to_bouquet(bouquet_path: Path, moves: list[dict[str, object]], db: Lamedb) -> None:
    lines = bouquet_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for move in moves:
        old = (int(str(move["old_sid"]), 16), int(str(move["old_tsid"]), 16))
        new = (int(str(move["new_sid"]), 16), int(str(move["new_tsid"]), 16))
        key = ServiceKey(new[0], new[1], int(DEFAULT_ONID, 16), int(DEFAULT_NS, 16))
        svc = db.services.get(key)
        if svc is None:
            print(f"  BLAD: {move['name']}: nowej uslugi {move['new_sid']}:{move['new_tsid']} nie ma w lamedb")
            continue
        new_line = f"#SERVICE 1:0:{svc.stype:X}:{new[0]:X}:{new[1]:X}:{int(DEFAULT_ONID, 16):X}:{int(DEFAULT_NS, 16):X}:0:0:0:"
        hit = False
        for i, line in enumerate(lines):
            if ref_of(line) == old:
                lines[i] = new_line
                hit = True
                print(f"  {move['name']}: linia {i + 1} -> {new_line[9:]}")
                break
        if not hit:
            print(f"  UWAGA: {move['name']}: starej referencji {move['old_sid']}:{move['old_tsid']} nie ma w bukiecie")

    seen: set[tuple[int, int]] = set()
    deduped: list[str] = []
    for line in lines:
        ref = ref_of(line)
        if ref is not None and ref in seen:
            print(f"  usunieto duplikat: {line[9:]}")
            continue
        if ref is not None:
            seen.add(ref)
        deduped.append(line)
    bouquet_path.write_text("\n".join(deduped) + "\n", encoding="utf-8")
    print(f"Zapisano {bouquet_path.name}: {len(deduped)} linii")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    settings_dir = Path(sys.argv[1])
    config = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    add_services(settings_dir / "lamedb", list(config.get("add_services", [])))
    rename_services(settings_dir / "lamedb", list(config.get("rename_services", [])))
    db = load_lamedb(settings_dir / "lamedb")
    for target in list(config.get("targets", [])):
        print(f"-- {target['bouquet']}")
        apply_to_bouquet(settings_dir / str(target["bouquet"]), list(target["moves"]), db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
