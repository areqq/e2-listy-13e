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
| `scripts/make_picons.py <settings> <store> <out> [names_db]` | picon.tar (220×132) i zzpicon.tar (400×170) **offline z repo store `picons/`**; symlinki po referencji, wszystkich znanych pisowniach i dla wpisów strumieniowych |
| `scripts/update_picons.py <settings> <store> [names_db]` | odświeża store `picons/` z najnowszych paczek zet71 (raz pobrane pikony zostają w repo) |
| `scripts/fetch_missing_picons.py <settings> <db> <store>` | dokłada do store to, czego zet71 nie ma — logotypy github.com/picons/picons (wymaga Pillow) |
| `scripts/postprocess_bouquet.py <settings> [config] [bukiety]` | generyczny post-procesor sterowany lokalnym configiem (poza repo); podmiany/wpisy dodatkowe wg `*.local.toml` |
| `scripts/pack_release.py <settings> <out_dir> [picon.tar zzpicon.tar]` | archiwa tylko przez Pythona: `<nazwa>.zip`, `lista.tar` (korzeń), `komplet_<DDMMRR>.tar` |
| `scripts/upload_release.py <pliki...>` | publikacja na transfer.whalebone.io + mirror wg lokalnego `upload.local.toml` (np. FTP) |
| `scripts/pack_release.py` | (jw.) generuje też `userbouquet.version` (w archiwum) i `version` (do uploadu) z pełnym timestampem |
| `scripts/e2_update.sh <bazowy_url/>` | **na dekoderze**: sprawdza `version`, pobiera i podmienia listę + pikony, przeładowuje bukiety przez OpenWebif — ultra-przenośny POSIX/busybox, URL bazowy jako parametr |

## Przepływ pracy

```bash
unzip lista.zip -d work && mv work/<stara> work/<data>
python3 scripts/check_list.py work/<data>
python3 scripts/watch_13e.py  work/<data>     # co podmienić -> moves/<data>.json
python3 scripts/apply_moves.py work/<data> moves/<data>.json
python3 scripts/fix_types.py  work/<data>
python3 scripts/check_list.py work/<data>     # 0 problemów
python3 scripts/make_picons.py work/<data> picons picons_out names_db.json   # offline z repo store
python3 scripts/pack_release.py work/<data> dist picons_out/picon.tar picons_out/zzpicon.tar
python3 scripts/upload_release.py dist/*.zip dist/lista.tar picons_out/*.tar dist/komplet_*.tar
```

Konfiguracje z danymi lokalnymi (`postprocess.local.toml`, `upload.local.toml`) trzymane są
poza repo (`.gitignore *.local.*`); wzorce w `postprocess.example.toml` / `upload.example.toml`.

Metodyka (źródła zapowiedzi i faktów, pułapki typu reużycie SID przy rebrandingu,
konsolidacja transponderów Canal+ 2026) — patrz [CLAUDE.md](CLAUDE.md).

### Skan z anteny — [satscan](https://github.com/areqq/satscan)

Osobny projekt (Zig, statyczna binarka bez zależności): skanuje ramówki platform
13°E prosto z tunera dekodera — usługi, transpondery i numerację LCN operatora,
albo cały satelita (`--scan-all`). Jego wyjście jest źródłem dla `build_names_db.py`
(świeże pisownie nazw z SI) i do weryfikacji listy względem faktycznego sygnału.

### Aktualizacja na dekoderze (OTA)

`e2_update.sh` porównuje `version` z lokalną `userbouquet.version` i tylko przy nowszej pobiera
`lista.tar` + `picon.tar` + `zzpicon.tar`, podmienia pliki (`/etc/enigma2`, `/usr/share/enigma2`)
i przeładowuje bukiety przez OpenWebif (`/web/servicelistreload?mode=0`, bez restartu GUI).
Po rozpakowaniu wypisuje raport (bukiety, lamedb, liczba i rozmiar pikon).

```sh
sh e2_update.sh https://host/sciezka/           # URL jako parametr (repo nie zawiera adresu)
wget -O - https://host/sciezka/u | sh           # wariant z FTP: 'u' ma URL zaszyty (do crona)
wget -O - https://host/sciezka/u | FORCE=1 sh   # wymuś mimo tej samej wersji (reinstal)
```

Port/schemat OpenWebif czytany jest z `/etc/enigma2/settings` (obsługa zmienionego portu i https).
Gdy localhost wymaga logowania: `OWIF="http://user:haslo@127.0.0.1:PORT"`. Adres serwera podaje się
parametrem lub jest zaszyty tylko w kopii `u`/`e2_update.sh` wgranej na FTP — repo go nie zawiera.

`picons/` to nasz store pikon trzymany w repo (source of truth budowy tarów). Zasilają go
`update_picons.py` (z zet71) i `fetch_missing_picons.py` (z github.com/picons/picons) — raz
pobrane pikony zostają, więc build jest odporny na zniknięcie źródeł. `names_db.json` (baza
równoważnych pisowni) również w repo, odświeżana przyrostowo.
