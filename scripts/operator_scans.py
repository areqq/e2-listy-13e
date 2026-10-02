"""Skany satscan na zywym dekoderze: referencje operatorow, pelny skan satelity, porownania.

Trzyma w operator-scans/<provider>.txt aktualny stan ramowki kazdego operatora
(wiersze T/S/L z satscan, sortowane = stabilny diff). Sluzy jako punkt odniesienia
do wykrywania przenosin transponderowych: `refresh` odswieza pliki (diff w git
pokazuje co doszlo/zniklo), `moved` porownuje dwa stany i wypisuje uslugi, ktore
zmienily transponder - dokladnie sygnal do napisania moves/*.json.

`fullscan` robi pelny skan satelity (`satscan --scan-all`). Tylko on czyta SDT
wprost z kazdego transpondera, wiec tylko on rozstrzyga o nazwach i martwych
referencjach (scripts/verify_vs_scan.py). Trwa ~10 min, dlatego idzie w tle na
dekoderze i jest odpytywany - zerwany tunel nie przerywa skanu.

Kopie kazdego skanu laduja w work/satscan-out/<DDMMRR>/ (wejscie dla verify_vs_scan).

Dekodery i sposob dostepu sa w LOKALNYM scan.local.toml (poza repo, wzor:
scan.example.toml). Pierwszy odpowiadajacy wygrywa.

DANE SA W ISO-8859-2 (nie UTF-8) - dekodujemy jawnie; patrz komentarz przy decode().

Tylko biblioteka standardowa (tomllib: Python 3.11+). Wymaga zbudowanego satscana
(../satscan/zig-out/bin/satscan-<arch>).

Uzycie:
  python3 scripts/operator_scans.py refresh            # odswiez wszystkie referencje
  python3 scripts/operator_scans.py refresh polsat     # tylko wybrane
  python3 scripts/operator_scans.py fullscan           # pelny skan 13E -> work/satscan-out/<DDMMRR>/
  python3 scripts/operator_scans.py changes [p ...]    # referencje vs HEAD: nowe/znikniete/nazwy/przenosiny
  python3 scripts/operator_scans.py sweep [--kazdy]    # test satscana: wszystkie platformy, nic nie zapisuje
  python3 scripts/operator_scans.py moved OLD NEW      # co zmienilo transponder miedzy dwoma plikami

Opcja --box <fragment opisu> (przed komenda) zaweza wybor do dekoderow, ktorych `opis`
w scan.local.toml zawiera fragment - np. gdy pierwszy box jest zajety.
"""
from __future__ import annotations

import base64
import datetime
import re
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROVIDERS = ["canalplus", "polsat", "nova", "skyitalia", "tivusat", "vivacom", "bistv"]

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "operator-scans"
SCANS = ROOT / "work" / "satscan-out"
CONFIG = ROOT / "scan.local.toml"
SATSCAN_DIR = ROOT.parent / "satscan" / "zig-out" / "bin"

SSH_COMMON = [
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "ConnectTimeout=15",
    "-o", "BatchMode=yes",
    "-o", "LogLevel=ERROR",
]
JOB = "/tmp/satscan_job"
FULLSCAN_TIMEOUT_S = 1800
POLL_S = 30

# satscan emituje nazwy uslug w ISO-8859-2 (Latin-2); dekodowanie UTF-8 by sie
# wywalilo na polskich znakach, a bajtowe grep/sort psuja plik. Dekodujemy jawnie.
ENCODING = "iso-8859-2"


@dataclass
class Box:
    opis: str
    ssh: list[str]
    arch: str = "armhf"
    args: list[str] = field(default_factory=list)  # np. ["--frontend", "1"] na boxie z martwym fe0

    @property
    def binary(self) -> Path:
        return SATSCAN_DIR / f"satscan-{self.arch}"

    def satscan(self, what: str) -> str:
        return " ".join(["/tmp/satscan", what, *self.args])


@dataclass
class ScanResult:
    rc: int
    stdout: bytes
    stderr: bytes


def decode(raw: bytes) -> str:
    return raw.decode(ENCODING, errors="replace")


def load_boxes(only: str | None) -> list[Box]:
    if not CONFIG.is_file():
        print(f"brak {CONFIG.name} - skopiuj scan.example.toml i wpisz swoje dekodery")
        return []
    data = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    boxes = [Box(opis=b["opis"], ssh=list(b["ssh"]), arch=b.get("arch", "armhf"), args=list(b.get("args", [])))
             for b in data.get("box", [])]
    return [b for b in boxes if only is None or only in b.opis]


def ssh(box: Box, command: str, stdin: bytes | None = None, timeout: int = 180) -> ScanResult | None:
    try:
        r = subprocess.run(["ssh", *SSH_COMMON, *box.ssh, command],
                           input=stdin, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return ScanResult(r.returncode, r.stdout, r.stderr)


def alive(box: Box) -> bool:
    res = ssh(box, "test -e /dev/dvb/adapter0/frontend0 && echo OK")
    return res is not None and res.stdout.strip() == b"OK"


def find_box(boxes: list[Box]) -> Box | None:
    for box in boxes:
        if alive(box):
            print(f"box: {box.opis}")
            return box
    return None


def deploy(box: Box) -> bool:
    if not box.binary.is_file():
        print(f"brak binarki: {box.binary}\n  zbuduj: (cd ../satscan && zig build)")
        return False
    b64 = base64.b64encode(box.binary.read_bytes())
    # przez stdin, zeby nie przekroczyc limitu dlugosci komendy
    res = ssh(box, "base64 -d > /tmp/satscan && chmod +x /tmp/satscan", stdin=b64, timeout=120)
    return res is not None and res.rc == 0


def ready_box(only: str | None) -> Box | None:
    box = find_box(load_boxes(only))
    if box is None:
        print("zaden dekoder z scan.local.toml nie odpowiada")
        return None
    if not deploy(box):
        print("nie udalo sie wgrac satscana")
        return None
    return box


DATA_LINE = re.compile(r"^[TSL] ")


def normalize(raw: bytes) -> str:
    """Zostaw wiersze danych T/S/L, posortowane (kolejnosc sekcji jest losowa)."""
    lines = [ln for ln in decode(raw).splitlines() if DATA_LINE.match(ln)]
    lines.sort()
    return "\n".join(lines) + ("\n" if lines else "")


def dated_dir() -> Path:
    d = SCANS / datetime.date.today().strftime("%d%m%y")
    d.mkdir(parents=True, exist_ok=True)
    return d


def show_problems(res: ScanResult) -> None:
    for ln in decode(res.stderr).splitlines():
        if "warning" in ln or "error" in ln.lower():
            print(f"      {ln}")


# Skan o mniej niz polowie linii zapisanej referencji to w praktyce zawsze niepelny
# odczyt (zly TP domowy, urwana tabela), a nie prawdziwa zmiana ramowki. Taki wynik
# nadpisalby referencje i zatarl punkt odniesienia do wykrywania przenosin.
MIN_SHARE_OF_REFERENCE = 0.5


def rejection_reason(res: ScanResult, text: str, ref: Path) -> str | None:
    """Powod odrzucenia skanu albo None, gdy wynik wyglada na pelny."""
    if res.rc != 0:
        return f"satscan zakonczyl sie kodem {res.rc}"
    count = text.count("\n")
    if count == 0:
        return "brak danych (NoLock?)"
    if ref.is_file():
        stored = ref.read_text(encoding=ENCODING, errors="replace").count("\n")
        if count < stored * MIN_SHARE_OF_REFERENCE:
            return f"{count} linii przy {stored} w referencji - niepelny odczyt, nie zmiana ramowki"
    return None


def refresh(which: list[str], only: str | None) -> int:
    box = ready_box(only)
    if box is None:
        return 1
    OUT.mkdir(exist_ok=True)
    copies = dated_dir()
    rc = 0
    for p in which:
        res = ssh(box, box.satscan(f"--provider {p}"))
        if res is None:
            print(f"  {p}: brak odpowiedzi (tunel/timeout) - pomijam, plik nietkniety")
            rc = 1
            continue
        text = normalize(res.stdout)
        ref = OUT / f"{p}.txt"
        reason = rejection_reason(res, text, ref)
        if reason:
            print(f"  {p}: ODRZUCONY - {reason}; plik nietkniety")
            show_problems(res)
            rc = 1
            continue
        ref.write_text(text, encoding=ENCODING)
        (copies / f"{p}.txt").write_text(text, encoding=ENCODING)
        n = text.count("\n")
        print(f"  {p}.txt: {n} linii")
    ssh(box, "rm -f /tmp/satscan")
    print("gotowe - porownaj: git diff operator-scans/")
    return rc


def run_detached(box: Box, command: str, timeout_s: int) -> ScanResult | None:
    """Uruchom komende w tle na dekoderze i odpytuj o koniec; kazde odpytanie to nowe ssh."""
    script = f"#!/bin/sh\n{command} > {JOB}.out 2> {JOB}.err\necho $? > {JOB}.rc\n".encode("ascii")
    start = ssh(box, f"rm -f {JOB}.*; cat > {JOB}.sh && chmod +x {JOB}.sh && "
                     f"(setsid {JOB}.sh >/dev/null 2>&1 </dev/null &) && echo started", stdin=script)
    if start is None or b"started" not in start.stdout:
        return None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(POLL_S)
        done = ssh(box, f"cat {JOB}.rc 2>/dev/null")
        if done and done.stdout.strip():
            out = ssh(box, f"cat {JOB}.out", timeout=300)
            err = ssh(box, f"cat {JOB}.err")
            ssh(box, f"rm -f {JOB}.*")
            if out is None:
                return None
            return ScanResult(int(done.stdout.strip() or b"1"), out.stdout, err.stdout if err else b"")
    print(f"  przekroczony limit {timeout_s // 60} min - skan zostal na dekoderze ({JOB}.*)")
    return None


SUMMARY = re.compile(rb"services=(\d+) transponders=(\d+) lcn=(\d+)")
LOCKED = re.compile(rb"frontend(\d+): (\d+[HV]) fec=(\S+): LOCK")


def sweep_box(box: Box) -> int:
    """Wszystkie platformy na jednym boxie: lock/uslugi/TP/LCN/kod. Nic nie zapisuje."""
    if not deploy(box):
        print("  nie udalo sie wgrac satscana")
        return 1
    bad = 0
    for p in PROVIDERS:
        res = ssh(box, box.satscan(f"--provider {p}"), timeout=300)
        if res is None:
            print(f"  {p:10s} brak odpowiedzi (tunel/timeout)")
            bad += 1
            continue
        lock = LOCKED.search(res.stderr)
        summ = SUMMARY.search(res.stderr)
        where = f"fe{lock[1].decode()} {lock[2].decode()} {lock[3].decode()}" if lock else "bez locka"
        nums = "svc={} tp={} lcn={}".format(*(g.decode() for g in summ.groups())) if summ else "-"
        flag = "" if res.rc == 0 else "   <-- BLAD"
        print(f"  {p:10s} {where:22s} {nums:28s} rc={res.rc}{flag}")
        if res.rc != 0:
            show_problems(res)
            bad += 1
    ssh(box, "rm -f /tmp/satscan")
    return bad


def sweep(each: bool, only: str | None) -> int:
    """Test satscana: domyslnie pierwszy odpowiadajacy box, z --kazdy wszystkie odpowiadajace."""
    boxes = load_boxes(only)
    if each:
        targets = [b for b in boxes if alive(b)]
    else:
        first = find_box(boxes)
        targets = [first] if first else []
    if not targets:
        print("zaden dekoder z scan.local.toml nie odpowiada")
        return 1
    bad = 0
    for box in targets:
        print(f"== {box.opis}")
        bad += sweep_box(box)
    print("wszystko OK" if bad == 0 else f"problemow: {bad}")
    return 1 if bad else 0


def fullscan(only: str | None) -> int:
    box = ready_box(only)
    if box is None:
        return 1
    print(f"  pelny skan 13E w tle (~10 min, odpytanie co {POLL_S} s)...")
    res = run_detached(box, box.satscan("--scan-all --pos 130"), FULLSCAN_TIMEOUT_S)
    ssh(box, "rm -f /tmp/satscan")
    if res is None:
        print("  brak wyniku")
        return 1
    services = sum(1 for ln in decode(res.stdout).splitlines() if ln.startswith("S "))
    if res.rc != 0 or services == 0:
        print(f"  ODRZUCONY - kod {res.rc}, uslug {services}")
        show_problems(res)
        return 1
    target = dated_dir() / "full13e.txt"
    # z naglowkiem "# scan-all": po nim verify_vs_scan poznaje pelny skan
    target.write_bytes(res.stdout)
    tps = sum(1 for ln in decode(res.stdout).splitlines() if ln.startswith("T "))
    print(f"  {target.relative_to(ROOT)}: {tps} TP, {services} uslug")
    return 0


# --- wykrywanie przenosin ----------------------------------------------------
SVC = re.compile(r'^S ([0-9A-F]+):([0-9A-F]+):([0-9A-F]+) .*?"([^"]*)"')


def services(path: Path) -> dict[str, tuple[str, str, str]]:
    """sid -> (tsid, onid, name) z pliku skanu (klucz po samym SID)."""
    return parse_services(path.read_text(encoding=ENCODING, errors="replace"))


def moved(old: Path, new: Path) -> int:
    """Uslugi obecne w obu, ale na innym transponderze (tsid) = przenosiny."""
    a, b = services(old), services(new)
    hits = []
    for sid, (tsid, onid, name) in a.items():
        if sid in b and b[sid][0] != tsid:
            hits.append((name, sid, tsid, b[sid][0]))
    if not hits:
        print("brak przenosin (te same transpondery)")
        return 0
    print(f"PRZENIESIONE ({len(hits)}):  nazwa  SID  {old.name}->{new.name} (TSID)")
    for name, sid, t0, t1 in sorted(hits):
        print(f"  {name:32s} {sid}  {t0} -> {t1}")
    return 0


def parse_services(text: str) -> dict[str, tuple[str, str, str]]:
    out: dict[str, tuple[str, str, str]] = {}
    for ln in text.splitlines():
        m = SVC.match(ln)
        if m:
            sid, tsid, onid, name = m.groups()
            out[sid] = (tsid, onid, name)
    return out


def changes(which: list[str]) -> int:
    """Referencje w katalogu roboczym vs ostatni commit: nowe, znikniete, nazwy, przenosiny."""
    total = 0
    for p in which:
        path = OUT / f"{p}.txt"
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:operator-scans/{p}.txt"],
                                   capture_output=True)
        if committed.returncode != 0 or not path.is_file():
            print(f"== {p}: brak wersji w HEAD albo w katalogu roboczym")
            continue
        old, new = parse_services(decode(committed.stdout)), parse_services(path.read_text(encoding=ENCODING, errors="replace"))
        added = sorted(set(new) - set(old))
        gone = sorted(set(old) - set(new))
        common = set(old) & set(new)
        renamed = sorted(s for s in common if old[s][2] != new[s][2])
        shifted = sorted(s for s in common if old[s][0] != new[s][0])
        n = len(added) + len(gone) + len(renamed) + len(shifted)
        total += n
        if n == 0:
            print(f"== {p}: bez zmian ({len(new)} uslug)")
            continue
        print(f"== {p}: +{len(added)} -{len(gone)} nazwy {len(renamed)} przenosiny {len(shifted)}")
        for s in shifted:
            print(f"   TP     {s}  {old[s][0]} -> {new[s][0]}  \"{new[s][2]}\"")
        for s in added:
            print(f"   NOWY   {s}:{new[s][0]}  \"{new[s][2]}\"")
        for s in gone:
            print(f"   ZNIKL  {s}:{old[s][0]}  \"{old[s][2]}\"")
        for s in renamed:
            print(f"   NAZWA  {s}  \"{old[s][2]}\" -> \"{new[s][2]}\"")
    return 0 if total == 0 else 1


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    only: str | None = None
    if argv[0] == "--box":
        if len(argv) < 3:
            print(__doc__)
            return 2
        only, argv = argv[1], argv[2:]
    cmd = argv[0]
    if cmd == "refresh":
        which = argv[1:] or PROVIDERS
        bad = [p for p in which if p not in PROVIDERS]
        if bad:
            print(f"nieznani operatorzy: {', '.join(bad)}  (znani: {', '.join(PROVIDERS)})")
            return 2
        return refresh(which, only)
    if cmd == "fullscan":
        return fullscan(only)
    if cmd == "sweep":
        return sweep(each="--kazdy" in argv[1:], only=only)
    if cmd == "changes":
        return changes(argv[1:] or PROVIDERS)
    if cmd == "moved":
        if len(argv) != 3:
            print("uzycie: moved <stary.txt> <nowy.txt>")
            return 2
        return moved(Path(argv[1]), Path(argv[2]))
    print(f"nieznana komenda '{cmd}' (refresh | fullscan | changes | sweep | moved)")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
