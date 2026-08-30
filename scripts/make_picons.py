"""Budowa picon.tar i zzpicon.tar z najnowszych paczek zet71 (eeRepo j00zeka)
dla kanalow z wybranych bukietow naszej listy.

Pliki nazywane sa znormalizowana nazwa kanalu (algorytm renderera j00zekPicons),
a obok powstaja symlinki po referencji uslugi (1_0_19_32D7_190_13E_820000_0_0_0.png),
wiec pikony znajduja sie i po nazwie, i po referencji.

Uzycie: python3 scripts/make_picons.py <katalog_settings> <katalog_wyjsciowy> [names_db.json] [baza_lokalna] [bukiet.tv ...]
Podanie names_db.json (ze scripts/build_names_db.py) wlacza dopasowywanie takze
po rownowaznych nazwach kanalu z innych list i KingOfSat. Baza lokalna (katalog
z podkatalogami picon/ i zzpicon/, np. z fetch_missing_picons.py) sluzy jako
ostatni fallback, gdy pikony nie ma w zadnej paczce zet71.
Wynik:  <katalog_wyjsciowy>/picon.tar   (220x132, rozpakowac w /usr/share/enigma2/)
        <katalog_wyjsciowy>/zzpicon.tar (400x170, jw.)
"""
from __future__ import annotations

import difflib
import io
import json
import re
import sys
import tarfile
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from e2lib import load_bouquet, load_lamedb

REPO_API = "https://api.github.com/repos/j00zek/eeRepo/contents/"
RAW_BASE = "https://raw.githubusercontent.com/j00zek/eeRepo/main/"
PKG_RE = re.compile(r"enigma2-plugin-picons--j00zeks-transparent-(220x132|400x170)-zet71_(.+)_all\.ipk")
SUBDIR = {"220x132": "picon", "400x170": "zzpicon"}
DEFAULT_BOUQUETS = [
    "userbouquet.dbe00.tv",  # POLSKA FULL
    "userbouquet.dbe25.tv",  # FTA Polska
    "userbouquet.dbe64.tv",  # *Film
    "userbouquet.dbe03.tv",  # *Sport
    "userbouquet.dbe06.tv",  # *XXX_All
    "userbouquet.dbe0e.tv",  # FTA English
    "userbouquet.dbe24.tv",  # *Info
]
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
ALIASES = {
    "canalplus1premiumhd": "canalpluspremiumhd",
    "travelhd": "travelchannelhd",
    "inultratvuhd": "ultratv4k",
    "cgtnnewshd": "cgtnhd",
    "cgtndocumhd": "cgtndocumentary",
    "dubairacingchannel": "dubairacing",
    "euronewsitalian": "euronews",
    "ewtnenglish": "ewtn",
    "noursatkids": "noursat",
    "mta2hdeuropa": "mta2",
    "ln24inter": "ln24international",
    "solocalciohd": "sportitaliasolocalcio",
    "mvmtmovementofculture": "mvmtculture",
    "greaterlovehd": "greaterlove2",
}


@dataclass
class Wanted:
    ref: str
    picon_name: str
    channel: str
    bouquet: str
    aliases: list[str]


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


def newest_packages() -> dict[str, str]:
    files = json.loads(http_get(REPO_API))
    newest: dict[str, tuple[str, str]] = {}
    for f in files:
        m = PKG_RE.fullmatch(f["name"])
        if m and (m.group(1) not in newest or m.group(2) > newest[m.group(1)][0]):
            newest[m.group(1)] = (m.group(2), f["name"])
    if set(newest) != set(SUBDIR):
        raise SystemExit(f"nie znaleziono obu paczek zet71 w repo, jest: {sorted(newest)}")
    return {size: name for size, (_, name) in newest.items()}


def ipk_pngs(ipk: bytes) -> dict[str, bytes]:
    off = 8
    while off < len(ipk) - 60:
        name = ipk[off:off + 16].decode().strip().rstrip("/")
        size = int(ipk[off + 48:off + 58].decode().strip())
        if name == "data.tar.gz":
            tf = tarfile.open(fileobj=io.BytesIO(ipk[off + 60:off + 60 + size]))
            return {Path(m.name).stem: tf.extractfile(m).read()
                    for m in tf.getmembers() if m.isfile() and m.name.endswith(".png")}
        off += 60 + size + (size % 2)
    raise SystemExit("brak data.tar.gz w ipk")


def normalize_name(channel: str) -> str:
    lowered = channel.lower().replace("&", "and").replace("+", "plus").replace("*", "star").replace(" hevc", "")
    ascii_name = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode()
    return re.sub("[^a-z0-9]", "", ascii_name)


def collect_wanted(settings_dir: Path, bouquets: list[str], names_db: dict[str, dict[str, object]]) -> list[Wanted]:
    db = load_lamedb(settings_dir / "lamedb")
    wanted: dict[str, Wanted] = {}
    for bq in bouquets:
        name, entries = load_bouquet(settings_dir / bq)
        for e in entries:
            if e.key is None:
                continue
            svc = db.services.get(e.key)
            if svc is None:
                continue
            ref = "_".join(e.raw[len("#SERVICE "):].rstrip(":").split(":")[:10])
            db_key = f"{e.key.sid:04x}:{e.key.tsid:04x}:{e.key.onid:04x}"
            alias_names = names_db.get(db_key, {}).get("names", [])
            aliases: list[str] = []
            for alias in alias_names:
                normalized = normalize_name(str(alias))
                if normalized and normalized != normalize_name(svc.name) and normalized not in aliases:
                    aliases.append(normalized)
            wanted.setdefault(ref, Wanted(ref, normalize_name(svc.name), svc.name, name, aliases))
    return list(wanted.values())


def candidate_names(picon_name: str) -> list[str]:
    names = [picon_name]
    if picon_name in ALIASES:
        names.append(ALIASES[picon_name])
    base = re.sub(r"(uhd|fhd|hd)$", "", picon_name)
    names += [base + suffix for suffix in ("", "hd", "uhd", "fhd", "ultrahd", "4k")]
    derived: list[str] = []
    for name in list(names):
        if name.endswith("pl"):
            derived += [name[:-2] + "polska", name[:-2] + "poland", name[:-2]]
        if "pl" in name[:-2]:
            derived.append(name.replace("pl", "polska", 1))
        if "docu" in name:
            derived.append(name.replace("docu", "doku"))
        if name.startswith("viasat"):
            derived.append("polsat" + name)
        if "nationalgeo" in name:
            derived += [name.replace("nationalgeo", "nationalgeographic"), name.replace("nationalgeo", "natgeo")]
        if "sport" in name and "sports" not in name:
            derived.append(name.replace("sport", "sports", 1))
        if name.endswith("tv"):
            derived.append(name[:-2])
        if name.endswith("channel"):
            derived.append(name[: -len("channel")])
        if "tv" in name:
            derived.append(name.replace("tv", "", 1))
    unique: list[str] = []
    for name in names + derived:
        if name and name not in unique:
            unique.append(name)
    return unique


def digits_of(name: str) -> str:
    return re.sub(r"[^0-9]", "", name)


def pick_png(pngs: dict[str, bytes], picon_name: str, aliases: list[str]) -> str | None:
    for name in [picon_name] + aliases:
        for candidate in candidate_names(name):
            if candidate in pngs:
                return candidate
    close = difflib.get_close_matches(picon_name, list(pngs), n=1, cutoff=0.87)
    if close and close[0][:2] == picon_name[:2] and digits_of(close[0]) == digits_of(picon_name):
        return close[0]
    return None


def build_tar(out_path: Path, subdir: str, pngs: dict[str, bytes],
              fallbacks: list[tuple[str, dict[str, bytes]]], wanted: list[Wanted]) -> list[Wanted]:
    missing: list[Wanted] = []
    substituted: dict[str, list[str]] = {}
    with tarfile.open(out_path, "w") as tar:

        def pack(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(f"{subdir}/{name}.png")
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))

        packed: set[str] = set()
        for w in sorted(wanted, key=lambda x: x.picon_name):
            found = pick_png(pngs, w.picon_name, w.aliases)
            source = pngs
            if found is None:
                for label, fb_pngs in fallbacks:
                    found = pick_png(fb_pngs, w.picon_name, w.aliases)
                    if found is not None:
                        source = fb_pngs
                        substituted.setdefault(label, []).append(w.channel)
                        break
            if found is None:
                missing.append(w)
                continue
            if found not in packed:
                pack(found, source[found])
                packed.add(found)
            link = tarfile.TarInfo(f"{subdir}/{w.ref}.png")
            link.type = tarfile.SYMTYPE
            link.linkname = f"{found}.png"
            tar.addfile(link)
    print(f"{out_path.name}: {len(packed)} pikon, {len(wanted) - len(missing)} symlinkow, brakuje {len(missing)}")
    for label, channels in substituted.items():
        print(f"   zastepczo z {label}: {', '.join(sorted(channels))}")
    return missing


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    settings_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    rest = sys.argv[3:]
    names_db: dict[str, dict[str, object]] = {}
    if rest and rest[0].endswith(".json"):
        names_db = json.loads(Path(rest[0]).read_text(encoding="utf-8"))
        print(f"baza nazw: {rest[0]} ({len(names_db)} uslug)")
        rest = rest[1:]
    local_base: dict[str, dict[str, bytes]] = {}
    if rest and Path(rest[0]).is_dir() and any((Path(rest[0]) / sub).is_dir() for sub in SUBDIR.values()):
        for sub in SUBDIR.values():
            local_base[sub] = {f.stem: f.read_bytes() for f in (Path(rest[0]) / sub).glob("*.png")}
        print(f"baza lokalna: {rest[0]} ({sum(len(v) for v in local_base.values())} plikow)")
        rest = rest[1:]
    bouquets = rest or DEFAULT_BOUQUETS
    wanted = collect_wanted(settings_dir, bouquets, names_db)
    print(f"kanalow (unikalne referencje) z {len(bouquets)} bukietow: {len(wanted)}")
    packages = newest_packages()
    pngs_by_size: dict[str, dict[str, bytes]] = {}
    for size, pkg_name in sorted(packages.items()):
        print(f"pobieram {pkg_name} ...")
        pngs_by_size[size] = ipk_pngs(http_get(RAW_BASE + pkg_name))
    for size in sorted(packages):
        other = next(s for s in SUBDIR if s != size)
        fallbacks: list[tuple[str, dict[str, bytes]]] = [(other, pngs_by_size[other])]
        if local_base:
            fallbacks.append(("baza lokalna", local_base.get(SUBDIR[size], {})))
            fallbacks.append(("baza lokalna (inny rozmiar)", local_base.get(other, {})))
        missing = build_tar(out_dir / f"{SUBDIR[size]}.tar", SUBDIR[size],
                            pngs_by_size[size], fallbacks, wanted)
        for w in missing:
            print(f"   BRAK: {w.channel} ({w.picon_name}) [{w.bouquet}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
