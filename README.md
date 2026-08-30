# e2-listy-13e

Narzędzia do utrzymania list kanałów Enigma2 dla **Hot Bird 13°E**: wykrywanie martwych
wpisów po przenosinach transponderowych, podmiany referencji w miejscu (bez zmiany
kolejności kanałów) oraz budowa kompletu pikon dopasowanego do listy.

## Zależności

Tylko biblioteka standardowa Pythona 3. Jedyny wyjątek: `fetch_missing_picons.py`
(budowa lokalnej bazy pikon-zastępczych) wymaga **Pillow** — reszta narzędzi działa na
samej stdlib. Config post-procesora i uploadu w TOML wymaga Pythona 3.11+ (`tomllib`);
na starszym Pythonie użyj równoważnego configu `.json`.

## Skrypty

| skrypt | rola |
|---|---|
| `scripts/check_list.py <settings>` | walidacja: martwe referencje, brakujące transpondery, typy SD/HD, duplikaty |
| `scripts/watch_13e.py <settings>` | dziennik KingOfSat 13°E vs lista: co zgasło, co się przenosi (emisje równoległe) |
| `scripts/apply_moves.py <settings> <moves.json>` | wykonanie przenosin: podmiany referencji, dopisy/rename w lamedb, sprzątanie duplikatów |
| `scripts/fix_types.py <settings>` | wyrównanie typów usług w bukietach do lamedb |
| `scripts/build_names_db.py <out.json> <listy...>` | baza równoważnych pisowni nazw kanałów (klucz SID:TSID:ONID) z wielu list + KingOfSat |
| `scripts/make_picons.py <settings> <out> [names_db] [baza]` | picon.tar (220×132) i zzpicon.tar (400×170) z najnowszych paczek zet71, pliki po nazwach + symlinki po referencjach |
| `scripts/fetch_missing_picons.py <settings> <db> <baza>` | lokalna baza pikon-zastępczych z logotypów KingOfSat (po SID, nie po nazwie) |

## Przepływ pracy

```bash
unzip lista.zip -d work && mv work/<stara> work/<data>
python3 scripts/check_list.py work/<data>
python3 scripts/watch_13e.py  work/<data>     # co podmienić -> moves/<data>.json
python3 scripts/apply_moves.py work/<data> moves/<data>.json
python3 scripts/fix_types.py  work/<data>
python3 scripts/check_list.py work/<data>     # 0 problemów
(cd work && zip -r ../E2_HD_settings_<data>.zip <data>)
python3 scripts/make_picons.py work/<data> picons_out names_db.json picons_local
```

Metodyka (źródła zapowiedzi i faktów, pułapki typu reużycie SID przy rebrandingu,
konsolidacja transponderów Canal+ 2026) — patrz [CLAUDE.md](CLAUDE.md).

`picons_local/` to baza pikon-zastępczych dla kanałów, których brakuje w zestawach zet71
(loga z KingOfSat i github.com/picons/picons, znormalizowane do obu kanw z przezroczystością).
