"""Publikacja plikow wynikowych: transfer.whalebone.io (linki) + opcjonalny mirror
do celow z lokalnej konfiguracji (poza repo).

Silnik nie zawiera zadnych adresow ani hasel - cele mirrora (np. FTP z danymi
logowania) mieszkaja w upload.local.toml / .json (gitignore *.local.*) albo w
sciezce ze zmiennej LISTY_UPLOAD_CONFIG. Schemat: patrz upload.example.toml.

Uzycie: python3 scripts/upload_release.py <plik> [plik ...]
"""
from __future__ import annotations

import ftplib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import tomllib as _toml   # stdlib, Python 3.11+
except ModuleNotFoundError:
    _toml = None              # starszy Python: uzyj configu .json

CONFIG_CANDIDATES = ["upload.local.toml", "upload.local.json"]
DEFAULT_TRANSFER = "https://transfer.whalebone.io"


def load_config() -> dict[str, object]:
    env = os.environ.get("LISTY_UPLOAD_CONFIG")
    candidates = [env] if env else CONFIG_CANDIDATES
    for name in candidates:
        if name and Path(name).exists():
            raw = Path(name).read_bytes()
            if name.endswith(".json"):
                return json.loads(raw.decode("utf-8"))
            if _toml is None:
                raise SystemExit("brak tomllib/tomli - uzyj upload.local.json")
            return _toml.loads(raw.decode("utf-8"))
    return {}


def mask(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.password:
        netloc = parts.netloc.replace(f":{parts.password}@", ":***@")
        return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    return url


def upload_transfer(path: Path, base: str) -> str:
    data = path.read_bytes()
    req = urllib.request.Request(f"{base.rstrip('/')}/{path.name}", data=data, method="PUT")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read().decode("utf-8").strip()


def verify_url(url: str) -> int:
    req = urllib.request.Request(url, headers={"Range": "bytes=0-99"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def upload_ftp(path: Path, dest: str) -> None:
    parts = urllib.parse.urlsplit(dest)
    ftp = ftplib.FTP()
    ftp.connect(parts.hostname, parts.port or 21, timeout=60)
    ftp.login(urllib.parse.unquote(parts.username or ""), urllib.parse.unquote(parts.password or ""))
    ftp.set_pasv(True)
    remote_dir = parts.path.strip("/")
    if remote_dir:
        for segment in remote_dir.split("/"):
            try:
                ftp.cwd(segment)
            except ftplib.error_perm:
                ftp.mkd(segment)
                ftp.cwd(segment)
    with path.open("rb") as f:
        ftp.storbinary(f"STOR {path.name}", f)
    ftp.quit()


def main() -> int:
    files = [Path(a) for a in sys.argv[1:]]
    if not files:
        print(__doc__)
        return 2
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        raise SystemExit(f"brak plikow: {', '.join(missing)}")

    cfg = load_config()
    base = str(cfg.get("transfer_base", DEFAULT_TRANSFER))

    print("== transfer.whalebone.io ==")
    for path in files:
        url = upload_transfer(path, base)
        code = verify_url(url)
        flag = "OK" if code in (200, 206) else f"!! HTTP {code}"
        print(f"  {path.name:16s} {url}  [{flag}]")

    destinations = list(cfg.get("destinations", []))
    extra = [Path(p) for p in cfg.get("include_files", []) if Path(p).is_file()]
    if not destinations:
        print("(brak upload.local.* - mirror pominiety)")
        return 0
    print("== mirror ==")
    for dest in destinations:
        for path in files + extra:
            try:
                if dest.startswith("ftp://"):
                    upload_ftp(path, dest)
                    print(f"  {mask(dest)}  <- {path.name}  [OK]")
                else:
                    print(f"  {mask(dest)}  <- {path.name}  [POMINIETO: nieobslugiwany schemat]")
            except OSError as e:
                print(f"  {mask(dest)}  <- {path.name}  [BLAD: {e}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
