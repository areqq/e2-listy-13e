# Listy kanałów Enigma2 — Hot Bird 13°E

Utrzymanie listy kanałów (settings E2) dla anteny 1×1 na 13°E, głównie bukietu
**POLSKA FULL**. Praca polega na wykrywaniu martwych wpisów po przenosinach
transponderowych i podmianie referencji bez zmiany kolejności kanałów.

## Struktura projektu

```
E2_HD_settings_*.zip     wejściowa/wyjściowa paczka settings (nazwa z datą DDMMRR)
scripts/                 narzędzia (python3, bez zależności zewnętrznych)
moves/                   pliki JSON z przenosinami — jeden na "akcję", zostają jako historia
work/                    rozpakowana kopia robocza (generowana, można kasować)
```

## Format plików (ściąga)

- **lamedb v4**: sekcja `transponders` (klucz `ns:tsid:onid` hex + linia `s freq:sr:pol:fec:pos:...:sys:mod:roll:pilot`), potem `services` (trójki linii: `sid:ns:tsid:onid:typ:0`, nazwa, `p:Provider,...`). Sekcje kończy `end`.
- **userbouquet.\*.tv**: `#SERVICE 1:0:<typ_hex>:<SID>:<TSID>:<ONID>:<NS>:0:0:0:` (hex, wielkie litery, bez zer wiodących). `1:64:...` + `#DESCRIPTION` = marker/separator.
- Typy usług: 1=SD, 25 (0x19)=HD, 31 (0x1F)=UHD, 2/10=radio. Typ w bukiecie musi zgadzać się z lamedb (inaczej zła ikonka SD/HD).
- Namespace 13°E: `00820000`, ONID `013E` (Hot Bird).

## Metodyka wykrywania zmian

1. **Źródło zapowiedzi — satkurier.pl** (kategoria "Kanały TV w Polsce"): publikuje plany
   przenosin tygodnie naprzód, z SID-ami i datami.
2. **Źródło faktów — KingOfSat**, dziennik 13°E: `https://pl.kingofsat.net/news.php?pos=13E`
   - "Nowa częstotliwość dla X" = start emisji równoległej → stary wpis zgaśnie
     **zwykle po ~2 tygodniach** (reguła Canal+ Polska),
   - "Opuścił" = stara emisja wyłączona → wpis w bukiecie martwy,
   - historia kanału: `channelhistory.php?ch=<id>`; transpondery jako .ini: `dl.php?pos=13E`.
3. **Kontekst 2026**: Canal+ Polska konsoliduje 6 dzierżawionych transponderów
   (10719 V, 10796 V, 11278 V, 11411 H, 11449 H, 11488 H — wszystkie SR 27500, FEC 5/6,
   DVB-S2/8PSK) i opróżnia **10796 V (tp.114)** oraz **11411 H (tp.11)**. Kanał z tych TP,
   któremu pojawiła się kopia gdzie indziej, jest następny do wygaszenia.
4. **Świeży skan do porównań**: paczka Vhannibal Hot Bird 13°E
   (`https://www.vhannibal.net/download_setting.php?id=2&action=download`) — dobre źródło
   nowych SID-ów do `add_services`, ale bywa opóźniona względem zmian i miewa złe typy usług.

## Przepływ pracy

```bash
unzip E2_HD_settings_<stara>.zip -d work && mv work/<stara> work/<nowa_data>
python3 scripts/check_list.py work/<nowa_data>        # spójność: martwe ref., typy, duplikaty
python3 scripts/watch_13e.py  work/<nowa_data>        # KingOfSat vs lista: co zgasło / co się przenosi
# na tej podstawie napisać moves/<data>_<opis>.json (schemat w docstringu apply_moves.py)
python3 scripts/apply_moves.py work/<nowa_data> moves/<plik>.json
python3 scripts/fix_types.py  work/<nowa_data>        # wyrównanie typów SD/HD do lamedb
python3 scripts/check_list.py work/<nowa_data>        # musi dać 0 problemów
python3 scripts/pack_release.py work/<nowa_data> dist picons_out/picon.tar picons_out/zzpicon.tar
```

## Przygotowanie listy na żądanie

Gdy user mówi „przygotuj mi listę na bazie pliku <plik>" (zip settings wrzucony do katalogu
projektu), wykonaj cały łańcuch:

1. rozpakuj do `work/<DDMMRR>` (data dzisiejsza), przejdź Przepływ pracy (check → watch →
   moves → apply → fix_types → check aż 0 problemów), spakuj `E2_HD_settings_<DDMMRR>.zip`;
2. odśwież `names_db.json` (build_names_db), zbuduj pikony:
   `make_picons.py work/<DDMMRR> picons_out names_db.json picons_local`;
   braki dociągnij `fetch_missing_picons.py` i przebuduj — ma być 0 braków;
3. spakuj archiwa WYŁĄCZNIE przez Pythona (przenośne, bez śmieci macOS):
   `python3 scripts/pack_release.py work/<DDMMRR> dist picons_out/picon.tar picons_out/zzpicon.tar`
   — daje `<nazwa>.zip` (z podkatalogiem), `lista.tar` (pliki listy w korzeniu, do rozpakowania
   wprost w /etc/enigma2) oraz `komplet_<DDMMRR>.tar` (lista.tar + oba tary pikon). Nie pakować
   przez systemowe tar/zip (bsdtar dokłada SCHILY.xattr). Publikacja przez
   `scripts/upload_release.py dist/*.zip dist/lista.tar picons_out/*.tar dist/komplet_*.tar`:
   transfer.whalebone.io (weryfikuje linki) + mirror do celów z `upload.local.toml`, jeśli jest;
4. podaj userowi wszystkie linki + krótkie podsumowanie zmian w liście.

Plików wejściowych (cudzych list) nie commitujemy do repo — zostają lokalnie.

## Pikony

Skórka BlackHarmonyFHD (eeRepo j00zeka) czyta pikony z `/usr/share/enigma2/picon/` (220×132)
i `/usr/share/enigma2/zzpicon/` (400×170), najpierw po referencji
(`1_0_19_32D7_190_13E_820000_0_0_0.png`), potem po znormalizowanej nazwie kanału.
Pikony trzymamy NA STAŁE w repo (store `picons/` z podkatalogami `picon/` i `zzpicon/`) —
to źródło budowy tarów, odporne na zniknięcie zewnętrznych źródeł.
`scripts/make_picons.py <settings> <store> <out> [names_db.json]` buduje `picon.tar`/`zzpicon.tar`
z tego store OFFLINE (bez pobierania): pliki + symlinki po referencji, wszystkich znanych
pisowniach i dla wpisów strumieniowych (rozpakować w `/usr/share/enigma2/`).
Store odświeżamy osobno: `scripts/update_picons.py <settings> <store> [names_db.json]`
dokłada/aktualizuje pikony z najnowszych paczek zet71 (raz pobrane zostają w repo).

Dopasowanie nazw: warianty końcówek (hd/uhd/4k), reguły pl↔polska, docu↔doku,
viasat→polsatviasat, tv±, aliasy jawne, difflib z blokadą różnych cyfr (żeby Eurosport 3
nie dostał pikony Eurosport 2 — zła pikona jest gorsza niż brak). Najskuteczniejsza jest
jednak baza równoważnych nazw `names_db.json` — TRZYMANA W GIT i odświeżana przyrostowo
(`scripts/build_names_db.py names_db.json <katalog[=etykieta]>...`; zapis tylko gdy doszło
coś nowego, posortowany JSON = czytelne diffy; etykieta źródła zamiast nazwy katalogu).
Skrypt sam dociąga najnowszego Vhannibala z vhannibal.net i strony KingOfSat
(sat-hb13f/sat-hb13g; NID/TID dziesiętnie w nagłówku transpondera); bzyk83 —
https://enigma2.hswg.pl/listy-kanalow-e2-by-bzyk83/, paczka hb.zip — dokładać ręcznie.
Tary pikon dostają symlinki dla KAŻDEJ znanej pisowni nazwy (plus referencje), więc
działają też na listach nazywających kanały inaczej.
Gdy pikony brakuje w jednym rozmiarze, a jest w drugim, trafia do tara zastępczo —
renderer i tak skaluje do rozmiaru widgetu (`setScale(1)`), a między katalogami sam nie
przeszukuje.

Dziury zestawu zet71 (czego zet71 nie ma) dokłada do store
`scripts/fetch_missing_picons.py <settings> <names_db.json> picons` (wymaga Pillow —
jedyny skrypt z zależnością): loga bierze z github.com/picons/picons (build-source/logos/,
warianty .light czytelniejsze na ciemnej skórce; SVG renderowane przez `qlmanage -t`),
dopasowanie nazw jak w make_picons + aliasy. Wycinanie bieli tylko dla obrazów bez kanału
alfa — inaczej znikają białe litery logotypów.
PUŁAPKA: linki /jpg/ na stronach KingOfSat to zrzuty z anteny (ikonka zap), NIE logotypy —
nie brać ich na pikony. Stan: 285/287 dla 7 bukietów (bez loga: NU TV, SMTV — efemeryczne kanały iKOMG bez logotypu w repo).

Po udanym wygenerowaniu tary wrzucamy na transfer.whalebone.io i podajemy linki userowi:
`curl --upload-file picons_out/picon.tar https://transfer.whalebone.io/picon.tar` (jw. zzpicon.tar).
Serwis zwraca unikalny URL; zaraz po uploadzie sprawdzić GET-em, bo pierwszy transfer
potrafi zwrócić URL, pod którym nic nie ma — wtedy wysłać ponownie.

## Zasady

- Podmieniamy referencję **w miejscu** — kanał zostaje na swojej pozycji w bukiecie.
- Nowa usługa nieobecna w lamedb → `add_services` (SID/TSID z KingOfSat lub z lamedb Vhannibala);
  typ wg rzeczywistości (HD=25), nie kopiować ślepo typu z cudzej listy.
- Martwych usług z lamedb nie usuwamy (nieszkodliwe, znikną przy kolejnym skanie).
- Sekcja markera `- Duble` w POLSKA FULL trzyma świadome duplikaty/warianty zapasowe;
  apply_moves sam usuwa wpisy, które po podmianie stały się zwykłymi duplikatami.
- `moves/*.json` nie kasujemy — to dziennik zmian listy.

## Pułapki

- Reużycie SID: "Opuścił X" + "Nowy kanał Y" na tym samym SID/TP tego samego dnia
  = rebranding (np. Western Collection → BarLume Collection). Referencja żyje,
  wystarczy `rename_services`; watch_13e pokaże to jako MARTWE — zweryfikować
  w `channelhistory.php` zanim się podmieni.
- lamedb vs satellites.xml potrafią różnić się o 1 MHz/1 kS — bez znaczenia dla strojenia.
- Kodowanie w lamedb (`C:`/`c:`) bywa niepełne — FTA/kodowany weryfikować w KingOfSat.
- sat-charts.eu bywa mocno nieaktualny; ufać KingOfSat + świeżemu skanowi.
