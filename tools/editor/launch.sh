#!/usr/bin/env bash
# League editor launcher.
#   launch.sh both     editor + game view (game view goes to the second screen)
#   launch.sh editor   editor only
#   launch.sh game     game view only
#   launch.sh stop     stop the local server
# Settings: edit the four lines below.
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DB="/run/media/hasa/HDD/LeagueDatabase"          # league database on the 1 TB HDD
HDD_UUID="8c4db688-dc74-4efe-b68d-b9d02cdae3ec"
PORT=8765
GAME="${IWM_GAME:-nhl13}"
URL="http://127.0.0.1:$PORT"
MODE="${1:-both}"

say() { notify-send -a "League Editor" "League Editor" "$1" 2>/dev/null || echo "$1"; }

if [ "$MODE" = stop ]; then pkill -f "[t]ools/editor/server.py" && say "Server stopped"; exit 0; fi

# 1. the HDD must be mounted (udisks needs no password for internal disks of the logged-in user)
if [ ! -d "$DB" ]; then
    udisksctl mount -b "/dev/disk/by-uuid/$HDD_UUID" >/dev/null 2>&1
    for _ in 1 2 3 4 5; do [ -d "$DB" ] && break; sleep 1; done
fi
if [ ! -d "$DB" ]; then say "League database not found at $DB - is the 1 TB HDD mounted?"; exit 1; fi

# 2. local server (serves the map, the editor and the database)
if ! curl -fs "$URL/api/info" >/dev/null 2>&1; then
    nohup python3 "$REPO/tools/editor/server.py" --db "$DB" --port "$PORT" >>"$DB/server.log" 2>&1 &
    for _ in $(seq 1 30); do curl -fs "$URL/api/info" >/dev/null 2>&1 && break; sleep 0.2; done
fi

# 3. windows: a KWin script puts the editor on the first screen and the game view on the other
#    (one screen: side by side)
if [ "$MODE" = both ] && command -v qdbus6 >/dev/null; then
    Q="qdbus6 org.kde.KWin /Scripting"
    $Q org.kde.kwin.Scripting.unloadScript iwm-place >/dev/null 2>&1
    ID=$($Q org.kde.kwin.Scripting.loadScript "$REPO/tools/editor/kwin-place.js" iwm-place 2>/dev/null)
    [ -n "$ID" ] && qdbus6 org.kde.KWin "/Scripting/Script$ID" org.kde.kwin.Script.run >/dev/null 2>&1
    ( sleep 40; $Q org.kde.kwin.Scripting.unloadScript iwm-place >/dev/null 2>&1 ) &
fi
case "$MODE" in
    editor) firefox --new-window "$URL/editor.html?game=$GAME" ;;
    game)   firefox --new-window "$URL/career-map.html?game=$GAME&live=1" ;;
    *)      running=$(pgrep -c -f "[f]irefox" || true)
            firefox --new-window "$URL/editor.html?game=$GAME"
            # a cold Firefox start takes a while; the second window must wait for it
            if [ "${running:-0}" = 0 ]; then sleep 8; else sleep 2; fi
            firefox --new-window "$URL/career-map.html?game=$GAME&live=1" ;;
esac
