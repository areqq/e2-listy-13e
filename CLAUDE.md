# Listy kanałów Enigma2 — Hot Bird 13°E

Utrzymanie listy kanałów (settings E2) dla anteny 1×1 na 13°E, głównie bukietu
**POLSKA FULL**. Praca polega na wykrywaniu martwych wpisów po przenosinach
transponderowych i podmianie referencji bez zmiany kolejności kanałów.

## Gdzie co jest — czytaj zamiast odtwarzać

Procedury żyją w lokalnych skillach projektu (`.claude/skills/`, poza repo):

| Zadanie | Skill |
|---|---|
| kontrola z sygnałem, skany, „czy są zmiany", przenosiny | `kontrola-orbity` |
| wydanie paczki, praca na cudzej paczce, commit i push | `wydanie-listy` |
| zmiany w satscan, testy na dekoderach, release | `satscan-dev` |

- `STATUS.md` — stan bieżący: aktualna paczka, co obserwujemy, otwarte decyzje.
- `scripts/` — narzędzia, opis w `README.md`. Zanim napiszesz doraźny kod do porównań lub skanów,
  sprawdź `operator_scans.py` i `verify_vs_scan.py` — robią to jednym poleceniem.
- Dane lokalne poza repo (`*.local.toml`, `STATUS.md`, skille) to dowiązania do `~/Documents/configs/listy/`.

## Struktura projektu

```
E2_HD_settings_*.zip     wejściowa/wyjściowa paczka settings (nazwa z datą DDMMRR), nie w repo
scripts/                 narzędzia (python3, stdlib; Pillow tylko w fetch_missing_picons)
moves/                   pliki JSON z przenosinami — jeden na akcję, zostają jako dziennik
operator-scans/          referencyjne skany ramówek operatorów (T/S/L, sortowane, ISO-8859-2)
picons/                  store pikon (źródło budowy tarów)
names_db.json            baza równoważnych pisowni nazw — tylko dla pikon, nie zmienia nazw w liście
work/                    kopie robocze i skany z anteny (generowane, poza repo)
```

## Format plików (ściąga)

- **lamedb v4**: sekcja `transponders` (klucz `ns:tsid:onid` hex + linia `s freq:sr:pol:fec:pos:...:sys:mod:roll:pilot`), potem `services` (trójki linii: `sid:ns:tsid:onid:typ:0`, nazwa, `p:Provider,...`). Sekcje kończy `end`.
- **userbouquet.\*.tv**: `#SERVICE 1:0:<typ_hex>:<SID>:<TSID>:<ONID>:<NS>:0:0:0:` (hex, wielkie litery, bez zer wiodących). `1:64:...` + `#DESCRIPTION` = marker/separator. Wpis z URL na końcu = strumień.
- Typy usług: 1=SD, 25 (0x19)=HD, 31 (0x1F)=UHD, 2/10=radio. Typ w bukiecie musi zgadzać się z lamedb (inaczej zła ikonka SD/HD).
- Namespace 13°E: `00820000`, ONID `013E` (Hot Bird).
- **Kodowanie ISO-8859-2**, nie UTF-8 — w Pythonie czytać jawnie, w shellu `LC_ALL=C`.

## Zasady

- Podmieniamy referencję **w miejscu** — kanał zostaje na swojej pozycji w bukiecie.
- Nowa usługa nieobecna w lamedb → `add_services`; typ wg rzeczywistości (pełny skan), nie z cudzej listy.
- Martwych usług z lamedb nie usuwamy (nieszkodliwe, znikną przy kolejnym skanie).
- Sekcja markera `- Duble` w POLSKA FULL trzyma świadome duplikaty; apply_moves sam usuwa zwykłe duplikaty.
- `moves/*.json` nie kasujemy — to dziennik zmian listy.
- Decyzje o liście zapadają na podstawie bukietów polskich; obce zmiany jadą przy najbliższej polskiej fali.

## Repozytorium jest publiczne

- Bez informacji o dekoderach i sieci — adresy dostępu są wyłącznie w `scan.local.toml`.
- Bez nazw operatorów w prozie (docs, commity); dane funkcjonalne (`p:` w lamedb, `provider` w moves) zostają.
- Bez nazw autorów cudzych list — także w danych, np. w etykietach źródeł `names_db.json`.
- Plików wejściowych (cudzych list) nie commitujemy.

## Pułapki ogólne

- Reużycie SID: „Opuścił X" + „Nowy kanał Y" na tym samym SID/TP tego samego dnia = rebranding.
  Referencja żyje, wystarczy `rename_services`.
- lamedb vs satellites.xml potrafią różnić się o 1 MHz/1 kS — bez znaczenia dla strojenia.
- Kodowanie w lamedb (`C:`/`c:`) bywa niepełne — FTA/kodowany weryfikować w KingOfSat.
- `check_list.py` sprawdza tylko spójność wewnętrzną; zgodność z sygnałem daje `verify_vs_scan.py`.
