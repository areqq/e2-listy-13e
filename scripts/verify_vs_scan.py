"""Weryfikacja listy wzgledem sygnalu: martwe referencje i przejete SID-y.

check_list.py sprawdza tylko spojnosc wewnetrzna (czy referencja istnieje w lamedb).
Ten skrypt porownuje bukiety z tym, co realnie nadaje satelita - z unii skanow
satscan (linie T/S). Rozroznia:

  MARTWE        TP jest w skanie i dobrze odczytany, a SID-u na nim nie ma,
  NIEPEWNE      TP w skanie, ale odczytany szczatkowo - werdykt niewiarygodny,
  INNA NAZWA    referencja zyje, ale pelny skan podaje zupelnie inna nazwe
                (przejety SID albo rebranding) - tylko wg pelnego skanu,
  BEZ WERDYKTU  TP w ogole poza skanami.

Nazwy ocenia WYLACZNIE wg pelnego skanu (`satscan --scan-all`), bo ten czyta SDT
wprost z transpondera. Skany `--provider` niosa nazwy z tablic operatora, ktore
bywaja nieaktualne albo opisuja cudze uslugi - daja falszywe alarmy.

Wpisy strumieniowe (z URL) sa pomijane - graja z sieci, nie z anteny.
Bukiety dzieli na polskie i obce; obce pokazuje skrotowo, chyba ze --wszystko.

Uzycie:
  python3 scripts/verify_vs_scan.py <katalog_settings> <skan|katalog>... [--wszystko]
  python3 scripts/verify_vs_scan.py work/<lista> work/satscan-out/<DDMMRR>/
"""
from __future__ import annotations

import difflib
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from e2lib import POLARIZATION, Lamedb, Service, ServiceKey, Transponder, list_bouquets, load_bouquet, load_lamedb

ENCODING = "iso-8859-2"
NS_13E = 0x820000
# TP z mniejsza liczba uslug w skanach uznajemy za odczytany szczatkowo.
MIN_SERVICES_FOR_VERDICT = 10
# Prog podobienstwa nazw po normalizacji; ponizej = "zupelnie inna nazwa".
NAME_SIMILARITY = 0.62

T_LINE = re.compile(r"^T ([0-9A-F]+):([0-9A-F]+) freq=(\d+) pol=(\w)")
S_LINE = re.compile(r'^S ([0-9A-F]+):([0-9A-F]+):([0-9A-F]+) type=(\d+) ca=\d "([^"]*)"')
NAME_NOISE = ("hd", "uhd", "4k", "tv", "pl", "polska", "poland", "canal+", "canalplus", "+")


@dataclass
class Signal:
    """Unia skanow: co nadaje satelita."""
    services: dict[tuple[int, int, int], str] = field(default_factory=dict)  # (sid,tsid,onid) -> nazwa
    sdt_names: dict[tuple[int, int, int], str] = field(default_factory=dict)  # tylko z pelnego skanu
    tp_freq: dict[tuple[int, int], str] = field(default_factory=dict)  # (tsid,onid) -> "10719V"
    tp_param: dict[tuple[int, int], tuple[int, str]] = field(default_factory=dict)  # (tsid,onid) -> (kHz, "V")
    tp_count: dict[tuple[int, int], int] = field(default_factory=dict)  # uslug widzianych na TP
    full_tp_count: dict[tuple[int, int], int] = field(default_factory=dict)  # jw., tylko pelny skan (SDT z TP)
    files: int = 0
    full_files: int = 0


@dataclass
class Finding:
    kind: str
    bouquet: str
    position: int
    ref: str
    name: str
    detail: str


def scan_files(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        out.extend(sorted(p.glob("*.txt")) if p.is_dir() else [p])
    return out


def load_signal(paths: list[Path]) -> Signal:
    sig = Signal()
    for path in paths:
        text = path.read_text(encoding=ENCODING, errors="replace")
        is_full = any(ln.startswith("# scan-all") for ln in text.splitlines()[:5])
        sig.files += 1
        sig.full_files += int(is_full)
        per_tp: Counter[tuple[int, int]] = Counter()
        for ln in text.splitlines():
            m = T_LINE.match(ln)
            if m:
                tp = (int(m[1], 16), int(m[2], 16))
                sig.tp_freq[tp] = f"{int(m[3]) // 1000}{m[4]}"
                sig.tp_param[tp] = (int(m[3]), m[4])
                continue
            m = S_LINE.match(ln)
            if not m:
                continue
            key = (int(m[1], 16), int(m[2], 16), int(m[3], 16))
            sig.services.setdefault(key, m[5])
            if is_full:
                sig.sdt_names[key] = m[5]
            per_tp[key[1:]] += 1
        # wiarygodnosc TP = najlepszy pojedynczy odczyt, nie suma (skany sie dubluja)
        for tp, n in per_tp.items():
            sig.tp_count[tp] = max(sig.tp_count.get(tp, 0), n)
            if is_full:
                sig.full_tp_count[tp] = max(sig.full_tp_count.get(tp, 0), n)
    return sig


def is_polish(bouquet: str) -> bool:
    """Obce: platformy "(13E)", "FTA <kraj>" poza FTA Polska i "INNE ...". Reszta to czesc polska."""
    if "(13E)" in bouquet or bouquet.startswith("INNE "):
        return False
    return not (bouquet.startswith("FTA ") and bouquet != "FTA Polska")


def tokens(name: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return frozenset(w for w in words if w not in NAME_NOISE)


def norm(name: str) -> str:
    s = name.lower()
    for w in NAME_NOISE:
        s = s.replace(w, "")
    return re.sub(r"[^a-z0-9]", "", s)


def names_differ(ours: str, theirs: str) -> bool:
    a, b = norm(ours), norm(theirs)
    if not a or not b or a in b or b in a:
        return False
    if tokens(ours) == tokens(theirs):  # ta sama nazwa w innej kolejnosci: "Club-RTL" / "RTL Club"
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() < NAME_SIMILARITY


FREQ_TOLERANCE_KHZ = 3000


def tsid_now(tp: Transponder | None, key: ServiceKey, sig: Signal) -> tuple[int, int] | None:
    """Ta sama czestotliwosc i polaryzacja nadaje dzis pod innym TSID/ONID (np. 1645 -> 1644)."""
    if tp is None:
        return None
    pol = POLARIZATION[tp.pol]
    for other, (freq, p) in sig.tp_param.items():
        if p == pol and abs(freq - tp.freq_khz) <= FREQ_TOLERANCE_KHZ and other != (key.tsid, key.onid):
            return other
    return None


def where_now(key: ServiceKey, name: str, tp: Transponder | None, sig: Signal) -> str:
    """Podpowiedz dla wpisu bez zywej referencji, od najpewniejszej."""
    for (sid, tsid, onid) in sig.services:
        if sid == key.sid and tsid == key.tsid and onid != key.onid:
            return f" -> zyje pod innym ONID: {sid:04X}:{tsid:04X}:{onid:04X}"
    moved_tp = tsid_now(tp, key, sig)
    if moved_tp and (key.sid, *moved_tp) in sig.services:
        return f" -> TP zmienil TSID, zyje jako {key.sid:04X}:{moved_tp[0]:04X}:{moved_tp[1]:04X}"
    want = norm(name)
    if len(want) >= 3:
        # tylko uslugi na TP znanych z linii T - odsiewa widma z innych satelitow w tablicach operatora
        hits = [k for k, n in sig.services.items()
                if norm(n) == want and k != (key.sid, key.tsid, key.onid) and k[1:] in sig.tp_freq]
        if hits:
            shown = ", ".join(f"{s:04X}:{t:04X}:{o:04X}@{sig.tp_freq[(t, o)]}" for s, t, o in hits[:2])
            return f" -> kandydat: {shown}"
    if moved_tp:
        return f" -> na tej czestotliwosci nadaje dzis TSID {moved_tp[0]:04X}:{moved_tp[1]:04X}"
    return ""


def channel_positions(path: Path) -> dict[int, int]:
    """Numer linii -> pozycja kanalu w bukiecie (jak na pilocie, ze strumieniami)."""
    pos: dict[int, int] = {}
    n = 0
    for line_no, raw in enumerate(path.read_text(encoding=ENCODING, errors="replace").splitlines(), start=1):
        if raw.startswith("#SERVICE ") and not raw.startswith("#SERVICE 1:64:"):
            n += 1
            pos[line_no] = n
    return pos


def check(settings: Path, sig: Signal) -> tuple[list[Finding], int, int]:
    lamedb = load_lamedb(settings / "lamedb")
    findings: list[Finding] = []
    checked = 0
    streams = 0
    for path in list_bouquets(settings):
        bouquet, entries = load_bouquet(path)
        positions = channel_positions(path)
        raw_lines = path.read_text(encoding=ENCODING, errors="replace").splitlines()
        streams += sum(1 for ln in raw_lines if ln.startswith("#SERVICE ") and "%3a//" in ln)
        for e in entries:
            if e.is_marker or e.key is None or e.key.ns != NS_13E:
                continue
            checked += 1
            findings.extend(judge(e.key, bouquet, positions.get(e.line_no, e.position), lamedb, sig))
    return findings, checked, streams


def judge(key: ServiceKey, bouquet: str, position: int, lamedb: Lamedb, sig: Signal) -> list[Finding]:
    svc: Service | None = lamedb.services.get(key)
    name = svc.name if svc else "?"
    ref = f"{key.sid:04X}:{key.tsid:04X}:{key.onid:04X}"
    k = (key.sid, key.tsid, key.onid)
    tp = (key.tsid, key.onid)
    where = sig.tp_freq.get(tp, "?")
    if k in sig.services:
        full_name = sig.sdt_names.get(k)
        if full_name is not None and names_differ(name, full_name):
            return [Finding("INNA NAZWA", bouquet, position, ref, name, f'pelny skan: "{full_name}" @{where}')]
        # Tylko w tablicy operatora, a pelny skan odczytal ten TP i uslugi tam nie ma. Zwykle to
        # kanal wylaczony (tablice operatora sa nieaktualne), ale pelny skan czyta TP kilka sekund
        # i moze zgubic sekcje SDT - dlatego NIEPEWNE, do potwierdzenia w KingOfSat.
        full_count = sig.full_tp_count.get(tp, 0)
        if full_name is None and full_count >= MIN_SERVICES_FOR_VERDICT:
            return [Finding("NIEPEWNE", bouquet, position, ref, name,
                            f'TP {where}: brak w SDT pelnego skanu ({full_count} uslug), '
                            f'jest tylko w tablicy operatora jako "{sig.services[k]}"')]
        return []
    count = sig.tp_count.get(tp, 0)
    hint = where_now(key, name, lamedb.transponder_for(key), sig)
    if count == 0:
        return [Finding("BEZ WERDYKTU", bouquet, position, ref, name, "TP poza skanami" + hint)]
    kind = "MARTWE" if count >= MIN_SERVICES_FOR_VERDICT else "NIEPEWNE"
    return [Finding(kind, bouquet, position, ref, name, f"TP {where}, {count} uslug w skanie{hint}")]


KINDS = ("MARTWE", "INNA NAZWA", "NIEPEWNE", "BEZ WERDYKTU")


def report(findings: list[Finding], show_foreign: bool) -> None:
    for polish in (True, False):
        part = [f for f in findings if is_polish(f.bouquet) == polish]
        label = "BUKIETY POLSKIE" if polish else "BUKIETY OBCE"
        counts = ", ".join(f"{k.lower()} {sum(1 for f in part if f.kind == k)}" for k in KINDS)
        print(f"\n{label}: {counts}")
        if not polish and not show_foreign:
            if part:
                print("  (szczegoly: --wszystko)")
            continue
        for kind in KINDS:
            for f in (x for x in part if x.kind == kind):
                print(f"  {kind:12s} {f.bouquet[:22]:22s} poz{f.position:4d}  {f.ref}  {f.name[:26]:26s} {f.detail}")


def main(argv: list[str]) -> int:
    show_foreign = "--wszystko" in argv
    args = [a for a in argv if a != "--wszystko"]
    if len(args) < 2 or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args and args[0] in ("-h", "--help") else 2
    settings = Path(args[0])
    paths = scan_files(args[1:])
    if not paths:
        print("brak plikow skanu")
        return 2
    sig = load_signal(paths)
    print(f"skany: {sig.files} plikow ({sig.full_files} pelnych), {len(sig.tp_freq)} TP, {len(sig.services)} uslug")
    if sig.full_files == 0:
        print("UWAGA: brak pelnego skanu (--scan-all) - nazwy nie sa oceniane, martwe tylko na TP z referencji")
    findings, checked, streams = check(settings, sig)
    print(f"sprawdzono {checked} referencji 13E (wpisy strumieniowe pominiete: {streams})")
    report(findings, show_foreign)
    polish_bad = sum(1 for f in findings if is_polish(f.bouquet) and f.kind in ("MARTWE", "INNA NAZWA"))
    return 1 if polish_bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
