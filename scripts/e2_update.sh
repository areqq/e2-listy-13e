#!/bin/sh
# Aktualizator listy kanalow Enigma2 (ultra-przenosny, POSIX/busybox).
#
# Pobiera <BASE>version, porownuje z lokalna /etc/enigma2/userbouquet.version
# (pierwsza linia = epoch); gdy zdalna nowsza, sciaga lista.tar + pikony,
# podmienia pliki i przeladowuje bukiety przez OpenWebif (bez restartu GUI).
#
# Uzycie:  e2_update.sh <bazowy_url/>
# Przyklad: e2_update.sh http://twoj-host/sciezka/
# Zmienne opcjonalne: OWIF (pelny adres OpenWebif; gdy pusty - port/schemat
#                       czytany z E2ROOT/settings; auth: OWIF=http://user:haslo@127.0.0.1:PORT)
#                     E2ROOT (domyslnie /etc/enigma2), PICONROOT (/usr/share/enigma2)

set -eu

BASE="${1:-}"
[ -n "$BASE" ] || { echo "Uzycie: $0 <bazowy_url/>"; exit 2; }
case "$BASE" in */) ;; *) BASE="$BASE/" ;; esac

E2ROOT="${E2ROOT:-/etc/enigma2}"
PICONROOT="${PICONROOT:-/usr/share/enigma2}"
TMP="${TMPDIR:-/tmp}/e2list-update.$$"

# Adres(y) OpenWebif do przeladowania: OWIF z env wygrywa, inaczej port i schemat
# czytamy z /etc/enigma2/settings (obsluguje zmieniony port / wlaczone https).
owif_candidates() {
  if [ -n "${OWIF:-}" ]; then echo "$OWIF"; return; fi
  s="$E2ROOT/settings"
  port=$(sed -n 's/^config\.OpenWebif\.port=//p' "$s" 2>/dev/null | head -n1)
  https=$(sed -n 's/^config\.OpenWebif\.https=//p' "$s" 2>/dev/null | head -n1)
  hport=$(sed -n 's/^config\.OpenWebif\.https_port=//p' "$s" 2>/dev/null | head -n1)
  echo "http://127.0.0.1:${port:-80}"
  [ "$https" = "true" ] && [ -n "$hport" ] && echo "https://127.0.0.1:${hport}"
}
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT INT TERM

fetch() {  # fetch <url> <plik>
  if command -v wget >/dev/null 2>&1; then wget -q -O "$2" "$1"
  elif command -v curl >/dev/null 2>&1; then curl -fsSL -o "$2" "$1"
  else echo "brak wget/curl"; return 1; fi
}

fetch "${BASE}version" "$TMP/version" || { echo "nie pobrano ${BASE}version"; exit 1; }
REMOTE=$(head -n1 "$TMP/version" | tr -dc '0-9')
LOCAL=$(head -n1 "$E2ROOT/userbouquet.version" 2>/dev/null | tr -dc '0-9' || true)
LOCAL="${LOCAL:-0}"
[ -n "$REMOTE" ] || { echo "pusta/zla zawartosc version"; exit 1; }

if [ "${FORCE:-0}" != 1 ] && [ "$REMOTE" -le "$LOCAL" ]; then
  echo "lista aktualna (lokalna=$LOCAL, zdalna=$REMOTE) - FORCE=1 wymusza"
  exit 0
fi
echo "nowa wersja $REMOTE (lokalna $LOCAL) - aktualizuje..."

for f in lista.tar picon.tar zzpicon.tar; do
  fetch "${BASE}${f}" "$TMP/$f" || { echo "blad pobierania $f"; exit 1; }
  echo "  pobrano ${f} ($(wc -c < "$TMP/$f") B)"
done

new_bouquets=$(tar tf "$TMP/lista.tar" | sed 's#.*/##' | grep -E '^userbouquet\.' || true)

# Bukiety IPTV uzytkownika (e2iPlayer/e2kodiPlayer): userbouquet.e2i_* albo dowolny
# userbouquet.* z wpisami strumieniowymi e2kodiPlayer to wlasne listy uzytkownika,
# nie z naszej paczki. Robimy ich kopie i po rozpakowaniu przywracamy oraz
# dopisujemy NA KONCU bouquets.tv/bouquets.radio - inaczej czyszczenie sierot
# ponizej by je skasowalo, a nasza lista (nadpisuje bouquets.*) by je ukryla.
iptv_list=""
mkdir -p "$TMP/iptv"
for f in "$E2ROOT"/userbouquet.*.tv "$E2ROOT"/userbouquet.*.radio; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  echo "$new_bouquets" | grep -qxF "$base" && continue   # nazwa z naszej paczki - nie ruszaj
  is_iptv=0
  case "$base" in userbouquet.e2i_*) is_iptv=1 ;; esac
  if [ "$is_iptv" = 0 ] && grep -qi 'e2kodiplayer' "$f" 2>/dev/null; then is_iptv=1; fi
  if [ "$is_iptv" = 1 ]; then
    cp "$f" "$TMP/iptv/$base"
    iptv_list="$iptv_list $base"
    echo "  zachowuje bukiet IPTV uzytkownika: $base"
  fi
done

# Usun osierocone bukiety z poprzednich list: pliki userbouquet.*, ktorych NIE ma
# w nowej paczce ANI nie sa zachowanymi bukietami IPTV. Inaczej enigma dokleja je
# z powrotem do bouquets.tv (nasz plik jest nadpisywany przy kazdej zmianie w GUI /
# zamknieciu), przez co obce bukiety laduja przed POLSKA FULL i numeracja startuje
# od ich liczby kanalow, nie od 1.
for f in "$E2ROOT"/userbouquet.*.tv "$E2ROOT"/userbouquet.*.radio; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  echo "$new_bouquets" | grep -qxF "$base" && continue
  case " $iptv_list " in *" $base "*) continue ;; esac
  rm -f "$f"
  echo "  usunieto stary bukiet spoza listy: $base"
done

tar xf "$TMP/lista.tar"   -C "$E2ROOT"
tar xf "$TMP/picon.tar"   -C "$PICONROOT"
tar xf "$TMP/zzpicon.tar" -C "$PICONROOT"

# Przywroc bukiety IPTV uzytkownika i dopisz ich referencje na KONCU list (za
# naszymi bukietami, wiec numeracja POLSKA FULL zaczyna sie od 1).
for base in $iptv_list; do
  cp "$TMP/iptv/$base" "$E2ROOT/$base"
  case "$base" in
    *.radio) idx="$E2ROOT/bouquets.radio"; svc="1:7:2:0:0:0:0:0:0:0:" ;;
    *)       idx="$E2ROOT/bouquets.tv";    svc="1:7:1:0:0:0:0:0:0:0:" ;;
  esac
  [ -f "$idx" ] || continue
  grep -qF "\"$base\"" "$idx" 2>/dev/null && continue   # juz w indeksie
  echo "#SERVICE ${svc}FROM BOUQUET \"$base\" ORDER BY bouquet" >> "$idx"
  echo "  przywrocono bukiet IPTV na koncu listy: $base"
done

echo "rozpakowano:"
echo "  lista:   $(ls "$E2ROOT"/userbouquet.*.tv 2>/dev/null | wc -l) bukietow, lamedb $(wc -l < "$E2ROOT/lamedb" 2>/dev/null || echo 0) linii"
echo "  picon:   $(ls "$PICONROOT/picon" 2>/dev/null | wc -l) plikow ($(du -sh "$PICONROOT/picon" 2>/dev/null | cut -f1))"
echo "  zzpicon: $(ls "$PICONROOT/zzpicon" 2>/dev/null | wc -l) plikow ($(du -sh "$PICONROOT/zzpicon" 2>/dev/null | cut -f1))"

# przeladowanie lamedb + bukietow przez OpenWebif (mode=0), bez restartu GUI
reloaded=0
for owif in $(owif_candidates); do
  if fetch "${owif}/web/servicelistreload?mode=0" "$TMP/reload" 2>/dev/null; then
    echo "przeladowano liste (${owif})"
    reloaded=1
    break
  fi
done
[ "$reloaded" = 1 ] || echo "reload przez API nieudany - ustaw OWIF=http://user:haslo@127.0.0.1:PORT albo zrestartuj E2"

echo "gotowe (wersja $REMOTE)"
