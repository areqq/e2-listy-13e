"""Porownanie dwoch paczek settings Enigma2 (np. cudzej z nasza ostatnia).
Czyta lamedb w ISO-8859-2 albo UTF-8, z CRLF i z separatorami "/" miedzy transponderami.
Bukiety paruje po #NAME (nazwy plikow moga sie roznic), referencje porownuje bez typu uslugi.
Uzycie: python3 scripts/compare_packages.py <paczka_A> <paczka_B>   (A = cudza, B = nasza)
Wynik: roznice transponderow i uslug w lamedb, a dla kazdego bukietu wpisy tylko w A (+), tylko w B (-),
zmiany typu i czy kolejnosc wspolnych wpisow jest ta sama.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServiceRow:
    name: str
    stype: str


@dataclass
class Package:
    services: dict[str, ServiceRow] = field(default_factory=dict)
    transponders: set[str] = field(default_factory=set)
    bouquets: dict[str, tuple[str, list[str]]] = field(default_factory=dict)


def read_lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("iso-8859-2")
    return text.replace("\r", "").splitlines()


def load_package(directory: Path) -> Package:
    pkg = Package()
    lines = read_lines(directory / "lamedb")
    i = lines.index("transponders") + 1
    while lines[i] != "end":
        if lines[i] == "/":
            i += 1
            continue
        pkg.transponders.add(lines[i].strip())
        i += 2
    i = lines.index("services", i) + 1
    while i < len(lines) and lines[i] != "end":
        fields = lines[i].split(":")
        pkg.services[f"{fields[0]}:{fields[2]}:{fields[3]}".lower()] = ServiceRow(lines[i + 1], fields[4])
        i += 3
    for bouquet in sorted(directory.glob("userbouquet.*.tv")):
        rows = read_lines(bouquet)
        name = next((row[6:].strip() for row in rows if row.startswith("#NAME")), bouquet.name)
        pkg.bouquets[name] = (bouquet.name, [bouquet_ref(row) for row in rows if row.startswith("#SERVICE 1:0:")])
    return pkg


def bouquet_ref(row: str) -> str:
    parts = row[len("#SERVICE "):].split(":")
    if len(parts) > 11 and parts[10]:
        return row[len("#SERVICE "):].rstrip(":")
    return f"{parts[2]}:{parts[3].zfill(4)}:{parts[4].zfill(4)}:{parts[5].zfill(4)}".lower()


def without_type(ref: str) -> str:
    parts = ref.split(":")
    return ":".join(parts[1:]) if len(parts) == 4 else ref


def service_name(pkg: Package, ref: str) -> str:
    row = pkg.services.get(without_type(ref))
    return row.name if row else "?"


def compare_bouquet(name: str, pkg_a: Package, pkg_b: Package) -> None:
    file_a, refs_a = pkg_a.bouquets[name]
    file_b, refs_b = pkg_b.bouquets[name]
    keyed_a = {without_type(r): r for r in refs_a}
    keyed_b = {without_type(r): r for r in refs_b}
    added = [keyed_a[k] for k in keyed_a if k not in keyed_b]
    removed = [keyed_b[k] for k in keyed_b if k not in keyed_a]
    retyped = [(keyed_b[k], keyed_a[k]) for k in keyed_a if k in keyed_b and keyed_a[k] != keyed_b[k]]
    common_a = [k for k in keyed_a if k in keyed_b]
    common_b = [k for k in keyed_b if k in keyed_a]
    if not (added or removed or retyped) and common_a == common_b:
        return
    order = "ta sama" if common_a == common_b else "ROZNA"
    print(f"\n## {name}: A {file_a} ({len(refs_a)}) vs B {file_b} ({len(refs_b)}); kolejnosc wspolnych {order}")
    for ref in added:
        print(f"  + {ref}  {service_name(pkg_a, ref)}")
    for ref in removed:
        print(f"  - {ref}  {service_name(pkg_b, ref)}")
    for old, new in retyped:
        print(f"  typ {old} -> {new}  {service_name(pkg_a, new)}")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    pkg_a, pkg_b = load_package(Path(sys.argv[1])), load_package(Path(sys.argv[2]))
    print(f"lamedb uslugi: A {len(pkg_a.services)} B {len(pkg_b.services)}; "
          f"TP: A {len(pkg_a.transponders)} B {len(pkg_b.transponders)}")
    print("TP tylko w A:", sorted(pkg_a.transponders - pkg_b.transponders))
    print("TP tylko w B:", sorted(pkg_b.transponders - pkg_a.transponders))
    for name in pkg_a.bouquets:
        if name in pkg_b.bouquets:
            compare_bouquet(name, pkg_a, pkg_b)
        else:
            print(f"\n## {name} ({pkg_a.bouquets[name][0]}) — tylko w A")
    for name in pkg_b.bouquets:
        if name not in pkg_a.bouquets:
            print(f"\n## {name} ({pkg_b.bouquets[name][0]}) — tylko w B")
    print("\n== te same uslugi, inna nazwa lub typ w lamedb")
    changed = 0
    for key in sorted(set(pkg_a.services) & set(pkg_b.services)):
        row_a, row_b = pkg_a.services[key], pkg_b.services[key]
        if (row_a.name, row_a.stype) != (row_b.name, row_b.stype):
            changed += 1
            print(f"  {key}: B '{row_b.name}' t{row_b.stype} -> A '{row_a.name}' t{row_a.stype}")
    print(f"  razem {changed}")
    only_a = sorted(set(pkg_a.services) - set(pkg_b.services))
    only_b = sorted(set(pkg_b.services) - set(pkg_a.services))
    print(f"uslugi tylko w A: {len(only_a)}", [f"{k} {pkg_a.services[k].name}" for k in only_a[:40]])
    print(f"uslugi tylko w B: {len(only_b)}", [f"{k} {pkg_b.services[k].name}" for k in only_b[:40]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
