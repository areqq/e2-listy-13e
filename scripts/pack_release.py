"""Pakowanie wynikowych archiwow wylacznie przez Pythona (przenosne, bez smieci
macOS - tarfile/zipfile nie dokladaja xattr/AppleDouble; dziala tak samo na
macOS i Linuksie).

Tworzy w katalogu wyjsciowym:
  <nazwa_katalogu>.zip   - zip z podkatalogiem (jak dotad)
  lista.tar              - pliki listy BEZPOSREDNIO w korzeniu (do /etc/enigma2)
  komplet[_<DDMMRR>].tar - lista.tar + podane tary pikon (jesli podano)

Uzycie: python3 scripts/pack_release.py <katalog_settings> <katalog_wyjsciowy> [picon.tar zzpicon.tar ...]
"""
from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from pathlib import Path

SKIP = {".DS_Store"}
TAR_FORMAT = tarfile.GNU_FORMAT


def _clean(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.pax_headers.clear()
    return info


def build_zip(settings_dir: Path, zip_path: Path) -> int:
    files = sorted(p for p in settings_dir.rglob("*") if p.is_file() and p.name not in SKIP)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f"{settings_dir.name}/{f.relative_to(settings_dir).as_posix()}")
    return len(files)


def build_flat_tar(settings_dir: Path, tar_path: Path) -> int:
    files = sorted(p for p in settings_dir.iterdir() if p.is_file() and p.name not in SKIP)
    with tarfile.open(tar_path, "w", format=TAR_FORMAT) as tf:
        for f in files:
            tf.add(f, arcname=f.name, filter=_clean)
    return len(files)


def build_combined_tar(members: list[Path], tar_path: Path) -> int:
    with tarfile.open(tar_path, "w", format=TAR_FORMAT) as tf:
        for m in members:
            tf.add(m, arcname=m.name, filter=_clean)
    return len(members)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    settings_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    picon_tars = [Path(p) for p in sys.argv[3:]]

    zip_path = out_dir / f"{settings_dir.name}.zip"
    lista_tar = out_dir / "lista.tar"
    print(f"{zip_path.name}: {build_zip(settings_dir, zip_path)} plikow")
    print(f"{lista_tar.name}: {build_flat_tar(settings_dir, lista_tar)} plikow (korzen archiwum)")

    if picon_tars:
        m = re.search(r"(\d{6})$", settings_dir.name)
        komplet = out_dir / (f"komplet_{m.group(1)}.tar" if m else "komplet.tar")
        n = build_combined_tar([lista_tar, *picon_tars], komplet)
        print(f"{komplet.name}: {n} archiwow (lista.tar + pikony)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
