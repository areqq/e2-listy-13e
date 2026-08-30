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
| `scripts/make_picons.py <settings> <out> [names_db] [baza]` | picon.tar (220×132) i zzpicon.tar (400×170) z najnowszych paczek zet71; symlinki po referencji, wszystkich znanych pisowniach i dla wpisów strumieniowych |
| `scripts/fetch_missing_picons.py <settings> <db> <baza>` | lokalna baza pikon-zastępczych z logotypów github.com/picons/picons (wymaga Pillow) |
| `scripts/postprocess_bouquet.py <settings> [config] [bukiety]` | generyczny post-procesor sterowany lokalnym configiem (poza repo); podmiany/wpisy dodatkowe wg `*.local.toml` |
| `scripts/pack_release.py <settings> <out_dir> [picon.tar zzpicon.tar]` | archiwa tylko przez Pythona: `<nazwa>.zip`, `lista.tar` (korzeń), `komplet_<DDMMRR>.tar` |
| `scripts/upload_release.py <pliki...>` | publikacja na transfer.whalebone.io + mirror wg lokalnego `upload.local.toml` (np. FTP) |

## Przepływ pracy

```bash
unzip lista.zip -d work && mv work/<stara> work/<data>
python3 scripts/check_list.py work/<data>
python3 scripts/watch_13e.py  work/<data>     # co podmienić -> moves/<data>.json
python3 scripts/apply_moves.py work/<data> moves/<data>.json
python3 scripts/fix_types.py  work/<data>
python3 scripts/check_list.py work/<data>     # 0 problemów
python3 scripts/make_picons.py work/<data> picons_out names_db.json picons_local
python3 scripts/pack_release.py work/<data> dist picons_out/picon.tar picons_out/zzpicon.tar
python3 scripts/upload_release.py dist/*.zip dist/lista.tar picons_out/*.tar dist/komplet_*.tar
```

Konfiguracje z danymi lokalnymi (`postprocess.local.toml`, `upload.local.toml`) trzymane są
poza repo (`.gitignore *.local.*`); wzorce w `postprocess.example.toml` / `upload.example.toml`.

Metodyka (źródła zapowiedzi i faktów, pułapki typu reużycie SID przy rebrandingu,
konsolidacja transponderów Canal+ 2026) — patrz [CLAUDE.md](CLAUDE.md).

`picons_local/` to baza pikon-zastępczych dla kanałów, których brakuje w zestawach zet71
(logotypy z github.com/picons/picons, znormalizowane do obu kanw z przezroczystością).
`names_db.json` (baza równoważnych pisowni) też jest w repo, odświeżana przyrostowo.
