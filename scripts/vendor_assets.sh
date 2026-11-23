#!/usr/bin/env bash
# Downloads frontend libraries into web/assets/vendor/ so the panel works
# fully offline (no CDN). Original script, written from scratch.
set -euo pipefail

DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/web/assets/vendor"
mkdir -p "$DEST"

fetch() {
  local url="$1" out="$2"
  if [[ -f "$DEST/$out" ]]; then
    echo "  exists : $out"
    return
  fi
  echo "  fetch  : $out"
  curl -fsSL "$url" -o "$DEST/$out"
}

echo ">> Vendoring frontend assets into $DEST"

fetch "https://cdn.jsdelivr.net/npm/vue@3.4.38/dist/vue.global.prod.js"       "vue.global.prod.js"
fetch "https://cdn.jsdelivr.net/npm/vue-router@4.4.3/dist/vue-router.global.prod.js" "vue-router.global.prod.js"
fetch "https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"            "xterm.min.js"
fetch "https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css"           "xterm.min.css"
fetch "https://cdn.jsdelivr.net/npm/xterm@5.3.0/addon-fit/fit.min.js"        "xterm-fit.min.js"

echo ">> Done — index.html will prefer these local copies automatically."
