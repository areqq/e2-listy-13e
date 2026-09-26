"""Baza rownowaznych nazw kanalow: ta sama usluga (SID:TSID:ONID) w roznych
listach (robocza, Vhannibal, bzyk83...) i na KingOfSat nosi rozne pisownie nazwy.
Suma tych pisowni sluzy potem make_picons.py jako aliasy przy dopasowywaniu pikon.

Baza jest trzymana w git i odswiezana przyrostowo: istniejacy plik wyjsciowy jest
wczytywany, dochodza tylko nowe pisownie, a zapis nastepuje wylacznie przy zmianach
(stabilny, posortowany JSON = czytelne diffy).

Uzycie: python3 scripts/build_names_db.py <wyjscie.json> <zrodlo[=etykieta]> [kolejne...] [--bez-kos] [--bez-vh]
Zrodlem moze byc katalog settings (lamedb) albo PLIK wyjsciowy satscan
(linie `S SID:TSID:ONID type=.. ca=.. "nazwa" ...` — swiezy skan z anteny).
Etykieta (domyslnie nazwa zrodla) laduje w polu sources.
Zrodla: kazdy podany katalog settings (nazwa zrodla = nazwa katalogu)
        + najnowsza paczka Vhannibal Hot Bird 13E z vhannibal.net (chyba ze --bez-vh)
        + strony KingOfSat dla 13E (Hot Bird 13F i 13G), chyba ze podano --bez-kos.

Wynik: JSON { "sid:tsid:onid" (hex): {"names": [...], "sources": {nazwa: zrodlo}} }
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from e2lib import load_lamedb

KOS_PAGES = ["https://pl.kingofsat.net/sat-hb13f", "https://pl.kingofsat.net/sat-hb13g"]
VHANNIBAL_URL = "https://www.vhannibal.net/download_setting.php?id=2&action=download"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
FREQ_HEADER_RE = re.compile(
    r'class="bld">(\d{4,5})\.\d{2}</td><td[^>]*class="bld">([VHLR])</td>.*?'
    r'width="4%">(\d{1,5})</td><td[^>]*width="4%">(\d{1,5})</td>', re.S)
CHANNEL_RE = re.compile(r'title="Id: ([^"]+)"[^>]*class="A3".*?<td class="s">(\d{1,5})</td>', re.S)


def add(db: dict[str, dict[str, object]], key: str, name: str, source: str) -> None:
    entry = db.setdefault(key, {"names": [], "sources": {}})
    clean = name.strip()
    if clean and clean not in entry["names"]:
        entry["names"].append(clean)
        entry["sources"][clean] = source


def from_settings(db: dict[str, dict[str, object]], settings_dir: Path, label: str) -> int:
    lamedb = load_lamedb(settings_dir / "lamedb")
    for key, svc in lamedb.services.items():
        add(db, f"{key.sid:04x}:{key.tsid:04x}:{key.onid:04x}", svc.name, label)
    return len(lamedb.services)


def from_vhannibal(db: dict[str, dict[str, object]]) -> int:
    req = urllib.request.Request(VHANNIBAL_URL, headers={"User-Agent": USER_AGENT, "Referer": "https://www.vhannibal.net/"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        archive = zipfile.ZipFile(io.BytesIO(resp.read()))
    lamedb_members = [n for n in archive.namelist() if n.endswith("lamedb")]
    if not lamedb_members:
        raise SystemExit("paczka Vhannibala nie zawiera lamedb")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "lamedb"
        target.write_bytes(archive.read(lamedb_members[0]))
        lamedb = load_lamedb(target)
    for key, svc in lamedb.services.items():
        add(db, f"{key.sid:04x}:{key.tsid:04x}:{key.onid:04x}", svc.name, "vhannibal")
    return len(lamedb.services)


SATSCAN_S_RE = re.compile(r'S ([0-9A-Fa-f]+):([0-9A-Fa-f]+):([0-9A-Fa-f]+) type=\d+ (?:ca=\d+ )?"([^"]*)"')


def from_satscan(db: dict[str, dict[str, object]], path: Path, label: str) -> int:
    count = 0
    # nazwy DVB po polsku najczesciej w Latin-2
    for line in path.read_text(encoding="iso-8859-2", errors="replace").splitlines():
        m = SATSCAN_S_RE.match(line)
        if m is None:
            continue
        key = f"{int(m.group(1), 16):04x}:{int(m.group(2), 16):04x}:{int(m.group(3), 16):04x}"
        add(db, key, m.group(4), label)
        count += 1
    return count


def from_kingofsat(db: dict[str, dict[str, object]]) -> int:
    count = 0
    for url in KOS_PAGES:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        blocks = page.split("data-frequency-id")[1:]
        for block in blocks:
            header = FREQ_HEADER_RE.search(block)
            if header is None:
                continue
            nid, tid = int(header.group(3)), int(header.group(4))
            for name, sid in CHANNEL_RE.findall(block):
                add(db, f"{int(sid):04x}:{tid:04x}:{nid:04x}", name, "kingofsat")
                count += 1
    return count


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_kos = "--bez-kos" not in sys.argv
    use_vh = "--bez-vh" not in sys.argv
    if len(args) < 2:
        print(__doc__)
        return 2
    out_path = Path(args[0])
    db: dict[str, dict[str, object]] = {}
    if out_path.exists():
        db = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"istniejaca baza: {len(db)} uslug")
    before = json.dumps(db, ensure_ascii=False, sort_keys=True)
    for spec in args[1:]:
        source, _, label = spec.partition("=")
        src_path = Path(source)
        if src_path.is_file():
            n = from_satscan(db, src_path, label or src_path.stem)
        else:
            n = from_settings(db, src_path, label or src_path.name)
        print(f"{source}: {n} uslug")
    if use_vh:
        print(f"vhannibal (najnowsza z vhannibal.net): {from_vhannibal(db)} uslug")
    if use_kos:
        print(f"kingofsat: {from_kingofsat(db)} wpisow")
    multi = sum(1 for e in db.values() if len(e["names"]) > 1)
    after = json.dumps(db, ensure_ascii=False, sort_keys=True)
    if after == before:
        print(f"bez zmian: {len(db)} uslug, w tym {multi} z >1 pisownia nazwy")
        return 0
    out_path.write_text(json.dumps(db, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"zapisano {out_path}: {len(db)} uslug, w tym {multi} z >1 pisownia nazwy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
