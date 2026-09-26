"""Wspolne parsowanie plikow Enigma2: lamedb v4 i userbouquet.*.tv."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

POLARIZATION = "HVLR"
SERVICE_TYPES = {1: "TV SD", 2: "Radio", 10: "Radio", 17: "TV HD (MPEG4)", 22: "TV SD (H264)", 25: "TV HD", 31: "TV UHD"}


@dataclass(frozen=True)
class ServiceKey:
    sid: int
    tsid: int
    onid: int
    ns: int

    def bouquet_ref(self, stype: int) -> str:
        return f"1:0:{stype:X}:{self.sid:X}:{self.tsid:X}:{self.onid:X}:{self.ns:X}:0:0:0:"


@dataclass
class Transponder:
    ns: int
    tsid: int
    onid: int
    freq_khz: int
    sr: int
    pol: int
    fec: int
    orbital_pos: int

    def human(self) -> str:
        return f"{self.freq_khz // 1000} {POLARIZATION[self.pol]} SR{self.sr // 1000}"


@dataclass
class Service:
    key: ServiceKey
    stype: int
    name: str
    provider_line: str


@dataclass
class Lamedb:
    transponders: dict[tuple[int, int, int], Transponder]
    services: dict[ServiceKey, Service]

    def transponder_for(self, key: ServiceKey) -> Transponder | None:
        return self.transponders.get((key.ns, key.tsid, key.onid))

    def find_transponder(self, freq_khz: int, pol: int, tolerance_khz: int = 3000) -> Transponder | None:
        best: Transponder | None = None
        for tp in self.transponders.values():
            if tp.pol == pol and abs(tp.freq_khz - freq_khz) <= tolerance_khz:
                if best is None or abs(tp.freq_khz - freq_khz) < abs(best.freq_khz - freq_khz):
                    best = tp
        return best


@dataclass
class BouquetEntry:
    line_no: int
    position: int
    raw: str
    key: ServiceKey | None
    stype: int
    is_marker: bool
    marker_text: str


def load_lamedb(path: Path) -> Lamedb:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    transponders: dict[tuple[int, int, int], Transponder] = {}
    services: dict[ServiceKey, Service] = {}
    i = lines.index("transponders") + 1
    while lines[i] != "end":
        ns_s, tsid_s, onid_s = lines[i].split(":")
        vals = lines[i + 1].strip().split()[1].split(":")
        tp = Transponder(
            ns=int(ns_s, 16), tsid=int(tsid_s, 16), onid=int(onid_s, 16),
            freq_khz=int(vals[0]), sr=int(vals[1]), pol=int(vals[2]),
            fec=int(vals[3]), orbital_pos=int(vals[4]),
        )
        transponders[(tp.ns, tp.tsid, tp.onid)] = tp
        i += 3
    i = lines.index("services") + 1
    while i < len(lines) and lines[i] != "end":
        parts = lines[i].lower().split(":")
        key = ServiceKey(sid=int(parts[0], 16), tsid=int(parts[2], 16), onid=int(parts[3], 16), ns=int(parts[1], 16))
        services[key] = Service(key=key, stype=int(parts[4]), name=lines[i + 1], provider_line=lines[i + 2])
        i += 3
    return Lamedb(transponders=transponders, services=services)


def load_bouquet(path: Path) -> tuple[str, list[BouquetEntry]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    name = lines[0][6:] if lines and lines[0].startswith("#NAME ") else path.name
    entries: list[BouquetEntry] = []
    position = 0
    for line_no, raw in enumerate(lines, start=1):
        if not raw.startswith("#SERVICE "):
            continue
        parts = raw[len("#SERVICE "):].split(":")
        if parts[1] == "64":
            entries.append(BouquetEntry(line_no, 0, raw, None, 0, True, parts[-1]))
            continue
        if parts[0] != "1" or (len(parts) > 10 and parts[10]):
            continue
        position += 1
        key = ServiceKey(sid=int(parts[3], 16), tsid=int(parts[4], 16), onid=int(parts[5], 16), ns=int(parts[6], 16))
        entries.append(BouquetEntry(line_no, position, raw, key, int(parts[2], 16), False, ""))
    return name, entries


def list_bouquets(settings_dir: Path) -> list[Path]:
    return sorted(settings_dir.glob("userbouquet.*.tv"))
