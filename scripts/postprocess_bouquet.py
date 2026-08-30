"""Post-procesor bukietu Enigma2 sterowany lokalna konfiguracja.

Silnik jest generyczny i NIE zawiera zadnych nazw kanalow, kluczy ani adresow -
cala tresc modyfikacji (co i na co zamienic, jaki szablon sciezki, jakie wpisy
dodac) mieszka w lokalnym pliku konfiguracyjnym, trzymanym poza repozytorium.

Config (TOML lub JSON), domyslnie ./postprocess.local.toml / .json albo sciezka
ze zmiennej srodowiskowej LISTY_POSTPROC_CONFIG. Schemat - patrz postprocess.example.toml:
  url_template : szablon pola sciezki, {key} = klucz wpisu (wymagany do podmian/extend)
  suffix       : dopisek do nazwy wpisu ze strumieniem (opcjonalny)
  keywords     : filtr nazw bez wzgledu na wielkosc liter (opcjonalny)
  [channels.<key>] aliases=[...] : nazwy uslug (jak w lamedb) -> ustaw sciezke na <key>
  [[extend]] after/name/sref/display : dodatkowy wpis wstawiany po kanale-kotwicy

Uzycie: python3 scripts/postprocess_bouquet.py <katalog_settings> [config] [bukiet.tv ...]
Bez podania bukietow przetwarza wszystkie userbouquet.*.tv. lamedb bierze z katalogu.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib as _toml
except ModuleNotFoundError:
    try:
        import tomli as _toml
    except ModuleNotFoundError:
        _toml = None

from e2lib import ServiceKey, list_bouquets, load_lamedb

CONFIG_CANDIDATES = ["postprocess.local.toml", "postprocess.local.json"]


@dataclass
class Config:
    url_template: str
    suffix: str = ""
    keywords: list[str] = field(default_factory=list)
    name_to_key: dict[str, str] = field(default_factory=dict)
    extends: list[dict[str, str]] = field(default_factory=list)


def load_config(path: Path) -> Config:
    raw = path.read_bytes()
    if path.suffix == ".json":
        data = json.loads(raw.decode("utf-8"))
    elif _toml is not None:
        data = _toml.loads(raw.decode("utf-8"))
    else:
        raise SystemExit("brak modulu tomllib/tomli - uzyj configu .json")
    channels = data.get("channels", {})
    name_to_key = {
        alias.strip().upper(): key
        for key, info in channels.items()
        for alias in info.get("aliases", [])
    }
    if "url_template" not in data:
        raise SystemExit("config bez 'url_template'")
    return Config(
        url_template=str(data["url_template"]),
        suffix=str(data.get("suffix", "")),
        keywords=[k.lower() for k in data.get("keywords", [])],
        name_to_key=name_to_key,
        extends=list(data.get("extend", [])),
    )


def resolve_config_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("LISTY_POSTPROC_CONFIG")
    if env:
        return Path(env)
    for candidate in CONFIG_CANDIDATES:
        if Path(candidate).exists():
            return Path(candidate)
    raise SystemExit("nie znaleziono configu (postprocess.local.toml/.json lub LISTY_POSTPROC_CONFIG)")


def service_name(db_services: dict[ServiceKey, object], ref_parts: list[str]) -> str | None:
    try:
        key = ServiceKey(int(ref_parts[3], 16), int(ref_parts[4], 16), int(ref_parts[5], 16), int(ref_parts[6], 16))
    except ValueError:
        return None
    svc = db_services.get(key)
    return svc.name if svc else None


def has_stream(ref_parts: list[str]) -> bool:
    return len(ref_parts) > 10 and ref_parts[10].strip() not in ("", "0")


def process(bouquet_path: Path, db_services: dict[ServiceKey, object], cfg: Config) -> int:
    lines = bouquet_path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[tuple[str, str | None]] = []
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.startswith("#SERVICE "):
            out.append((line, None))
            continue
        ref_parts = line[len("#SERVICE "):].split(":")
        if len(ref_parts) < 7 or ref_parts[1] == "64" or has_stream(ref_parts):
            out.append((line, None))
            continue
        name = service_name(db_services, ref_parts)
        key = cfg.name_to_key.get(name.strip().upper()) if name else None
        if key is None or (cfg.keywords and not any(kw in name.lower() for kw in cfg.keywords)):
            out.append((line, None))
            continue
        while len(ref_parts) < 11:
            ref_parts.append("")
        ref_parts = ref_parts[:11]
        ref_parts[10] = cfg.url_template.format(key=key)
        display = name.replace(":", " ").strip()
        if cfg.suffix and not display.endswith(cfg.suffix.strip()):
            display += cfg.suffix
        out.append((f"#SERVICE {':'.join(ref_parts)}:{display}", key))
        changes += 1
        if i < len(lines) and lines[i].startswith("#DESCRIPTION"):
            i += 1

    present_srefs = {ln.split(":aqiptv", 1)[0] if ":aqiptv" in ln else ln for ln, _ in out}
    for ext in cfg.extends:
        sref_parts = ext["sref"].rstrip(":").split(":")
        while len(sref_parts) < 11:
            sref_parts.append("")
        sref_parts = sref_parts[:11]
        sref_parts[10] = cfg.url_template.format(key=ext["name"])
        display = str(ext.get("display", ext["name"])).replace(":", " ").strip()
        if cfg.suffix and not display.endswith(cfg.suffix.strip()):
            display += cfg.suffix
        ext_line = f"#SERVICE {':'.join(sref_parts)}:{display}"
        if any(ext_line == ln for ln, _ in out):
            continue
        anchor = next((idx for idx in range(len(out) - 1, -1, -1) if out[idx][1] == ext.get("after")), None)
        out.insert(anchor + 1 if anchor is not None else len(out), (ext_line, ext["name"]))
        changes += 1

    bouquet_path.write_text("\n".join(ln for ln, _ in out) + "\n", encoding="utf-8")
    return changes


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    settings_dir = Path(args[0])
    config_arg = args[1] if len(args) > 1 and (args[1].endswith(".toml") or args[1].endswith(".json")) else None
    bouquet_args = args[(2 if config_arg else 1):]
    cfg = load_config(resolve_config_path(config_arg))
    db = load_lamedb(settings_dir / "lamedb")
    targets = [settings_dir / b for b in bouquet_args] if bouquet_args else list_bouquets(settings_dir)
    total = 0
    for path in targets:
        n = process(path, db.services, cfg)
        if n:
            print(f"{path.name}: {n} zmian")
        total += n
    print(f"Razem zmian: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
