#!/bin/sh
# Aktualizator listy kanalow Enigma2 (ultra-przenosny, POSIX/busybox).
#
# Pobiera <BASE>version, porownuje z lokalna /etc/enigma2/userbouquet.version
# (pierwsza linia = epoch); gdy zdalna nowsza, sciaga lista.tar + pikony,
# podmienia pliki i przeladowuje bukiety przez OpenWebif (bez restartu GUI).
#
# Uzycie:  e2_update.sh <bazowy_url/>
# Przyklad: e2_update.sh http://twoj-host/sciezka/
# Zmienne opcjonalne: OWIF (adres OpenWebif, domyslnie http://127.0.0.1)
#                     E2ROOT (domyslnie /etc/enigma2), PICONROOT (/usr/share/enigma2)

set -eu

BASE="${1:-}"
[ -n "$BASE" ] || { echo "Uzycie: $0 <bazowy_url/>"; exit 2; }
case "$BASE" in */) ;; *) BASE="$BASE/" ;; esac

E2ROOT="${E2ROOT:-/etc/enigma2}"
PICONROOT="${PICONROOT:-/usr/share/enigma2}"
OWIF="${OWIF:-http://127.0.0.1}"
TMP="${TMPDIR:-/tmp}/e2list-update.$$"
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

if [ "$REMOTE" -le "$LOCAL" ]; then
  echo "lista aktualna (lokalna=$LOCAL, zdalna=$REMOTE)"
  exit 0
fi
echo "nowa wersja $REMOTE (lokalna $LOCAL) - aktualizuje..."

for f in lista.tar picon.tar zzpicon.tar; do
  fetch "${BASE}${f}" "$TMP/$f" || { echo "blad pobierania $f"; exit 1; }
done

tar xf "$TMP/lista.tar"   -C "$E2ROOT"
tar xf "$TMP/picon.tar"   -C "$PICONROOT"
tar xf "$TMP/zzpicon.tar" -C "$PICONROOT"

# przeladowanie lamedb + bukietow przez OpenWebif (mode=0), bez restartu GUI
if fetch "${OWIF}/web/servicelistreload?mode=0" "$TMP/reload" 2>/dev/null; then
  echo "przeladowano liste (OpenWebif)"
else
  echo "reload przez API nieudany - przeladuj liste recznie lub zrestartuj E2"
fi

echo "gotowe (wersja $REMOTE)"
