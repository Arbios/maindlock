#!/bin/bash
# fetch_object.sh <object_id>:<key> [...] — download PixelLab map objects, trim transparent borders,
# save as static/room/objects/<key>.png. Skips (reports NOT_READY) if generation not finished.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/src/mindlock/game/static/room/objects"
mkdir -p "$OUT"
for pair in "$@"; do
  ID="${pair%%:*}"; KEY="${pair##*:}"
  TMP="$(mktemp /tmp/plobj.XXXXXX.png)"
  curl -sL -o "$TMP" "https://api.pixellab.ai/mcp/map-objects/$ID/download"
  if [ "$(head -c 4 "$TMP" | xxd -p)" != "89504e47" ]; then
    echo "$KEY: NOT_READY ($(head -c 80 "$TMP" | tr -d '\n'))"
    rm -f "$TMP"; continue
  fi
  "$ROOT/.venv/bin/python" - "$TMP" "$OUT/$KEY.png" "$KEY" <<'EOF'
import sys
from PIL import Image
src, dst, key = sys.argv[1:4]
im = Image.open(src).convert("RGBA")
bbox = im.getchannel("A").getbbox()  # non-transparent region
assert bbox, f"{key}: image fully transparent"
m = 2
x0, y0 = max(0, bbox[0] - m), max(0, bbox[1] - m)
x1, y1 = min(im.width, bbox[2] + m), min(im.height, bbox[3] + m)
out = im.crop((x0, y0, x1, y1))
out.save(dst)
print(f"{key}: {im.size} -> {out.size}")
EOF
  rm -f "$TMP"
done
