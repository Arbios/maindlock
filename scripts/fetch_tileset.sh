#!/bin/bash
# fetch_tileset.sh <tileset_id>:<dirname> [...] — download PixelLab topdown tilesets into static/room/<dirname>
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for pair in "$@"; do
  ID="${pair%%:*}"; DIR="${pair##*:}"
  OUT="$ROOT/src/mindlock/game/static/room/$DIR"
  mkdir -p "$OUT"
  TMP="$(mktemp /tmp/plts.XXXXXX.png)"
  curl -sL -o "$TMP" "https://api.pixellab.ai/mcp/tilesets/$ID/image"
  if [ "$(head -c 4 "$TMP" | xxd -p)" != "89504e47" ]; then
    echo "$DIR: NOT_READY ($(head -c 80 "$TMP" | tr -d '\n'))"
    rm -f "$TMP"; continue
  fi
  mv "$TMP" "$OUT/tileset.png"
  curl -sL -o "$OUT/tileset.json" "https://api.pixellab.ai/mcp/tilesets/$ID/metadata"
  "$ROOT/.venv/bin/python" - "$OUT" "$DIR" <<'EOF'
import json, sys
from PIL import Image
out, name = sys.argv[1:3]
im = Image.open(out + "/tileset.png"); im.load()
d = json.load(open(out + "/tileset.json"))
tiles = d["tileset_data"]["tiles"]
ok = [t for t in tiles if "corners" in t and "bounding_box" in t
      and all(k in t["corners"] for k in ("NW", "NE", "SW", "SE"))]
assert len(ok) >= 14, f"{name}: only {len(ok)} valid tiles"
print(f"{name}: png {im.size} {im.mode}, {len(ok)} tiles OK")
EOF
done
