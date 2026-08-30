"""Monitor zmian na 13E: pobiera dziennik KingOfSat i zestawia go z lokalna lista.

Raportuje:
  - MARTWE:   kanaly z bukietow, ktorych emisja zostala zgloszona jako "Opuscil",
  - PRZENIESIONE: kanaly z nowa czestotliwoscia (emisja rownolegla - stary wpis
    zgasnie zwykle po ok. 2 tygodniach; sprawdz czy nowy SID jest juz w lamedb).

Uzycie: python3 scripts/watch_13e.py <katalog_settings>
"""
from __future__ import annotations

import html
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from e2lib import Lamedb, ServiceKey, list_bouquets, load_bouquet, load_lamedb

NEWS_URL = "https://pl.kingofsat.net/news.php?pos=13E"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
DATE_RE = re.compile(r"(Poniedziałek|Wtorek|Środa|Czwartek|Piątek|Sobota|Niedziela)\s+(\d{1,2}\s+\w+\s+\d{4})")
LEFT_RE = re.compile(r"\|([^|]{2,60})\|\s*Opuścił\s*(\d{4,5}\.\d{2})MHz, pol\.(H|V)[^)]*?SID:(\d+)")
MOVED_RE = re.compile(r"Nowa częstotliwość dla\s*\|([^|]{2,60})\|:\s*(\d{4,5}\.\d{2})MHz, pol\.(H|V).{0,120}?SID:(\d+)")


@dataclass
class Event:
    date: str
    channel: str
    freq_khz: int
    pol: int
    sid: int


def fetch_news_text() -> str:
    req = urllib.request.Request(NEWS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", "", raw, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "|", raw))
    return re.sub(r"\|\s*\|+", "|", text)


def parse_events(text: str, pattern: re.Pattern[str]) -> list[Event]:
    events: list[Event] = []
    current_date = "?"
    tokens = sorted(
        [(m.start(), "date", m) for m in DATE_RE.finditer(text)] + [(m.start(), "evt", m) for m in pattern.finditer(text)]
    )
    for _, kind, m in tokens:
        if kind == "date":
            current_date = m.group(2)
        else:
            events.append(Event(current_date, m.group(1).strip(), round(float(m.group(2)) * 1000), "HV".index(m.group(3)), int(m.group(4))))
    return events


def bouquet_index(settings_dir: Path) -> dict[ServiceKey, list[str]]:
    index: dict[ServiceKey, list[str]] = {}
    for path in list_bouquets(settings_dir):
        name, entries = load_bouquet(path)
        for e in entries:
            if e.key is not None:
                index.setdefault(e.key, []).append(f"{name} poz {e.position}")
    return index


def resolve_key(db: Lamedb, ev: Event) -> ServiceKey | None:
    tp = db.find_transponder(ev.freq_khz, ev.pol)
    return ServiceKey(ev.sid, tp.tsid, tp.onid, tp.ns) if tp else None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    settings_dir = Path(sys.argv[1])
    db = load_lamedb(settings_dir / "lamedb")
    index = bouquet_index(settings_dir)
    text = fetch_news_text()

    print("== MARTWE (Opuscil, wpis nadal w bukietach) ==")
    hits = 0
    for ev in parse_events(text, LEFT_RE):
        key = resolve_key(db, ev)
        if key and key in index:
            hits += 1
            print(f"  {ev.date}  {ev.channel}  {ev.freq_khz // 1000} {'HV'[ev.pol]} SID {ev.sid}  ->  {'; '.join(index[key])}")
    print("  (brak)" if not hits else f"  razem: {hits}")

    print("\n== PRZENIESIONE (nowa czestotliwosc = emisja rownolegla) ==")
    for ev in parse_events(text, MOVED_RE):
        key = resolve_key(db, ev)
        status = "NOWY SID JUZ W LAMEDB" if key and key in db.services else "nowego SID brak w lamedb - dopisz lub przeskanuj"
        print(f"  {ev.date}  {ev.channel}  -> {ev.freq_khz // 1000} {'HV'[ev.pol]} SID {ev.sid}  [{status}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
