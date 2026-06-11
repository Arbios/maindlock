"""Restyle a room's Wang tileset with the room-1 'dark ward' recipe.

Operations (each optional, applied in order):
  --desat 0.35            multiply saturation of the whole sheet
  --hue-to 0.52 --hue-mix 0.3   nudge hue toward a target (0..1, HSV) by mix fraction
  --slab "118,116,110"    replace the all-lower (floor) tile with a programmatic
                          matte slab: albedo RGB + jitter, subtle joints on right/bottom
  --wall-mul 0.7          darken every non-floor tile
  --wall-blend 0.35       blend non-floor tiles toward their mean (kills grid noise)

  .venv/bin/python scripts/restyle_tileset.py --dir src/mindlock/game/static/room/r04 \
      --slab "110,112,118" --wall-mul 0.65 --wall-blend 0.4
"""
from __future__ import annotations

import argparse
import colorsys
import json
import os
import random


def main() -> None:
    from PIL import Image

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--desat", type=float, default=None)
    ap.add_argument("--hue-to", type=float, default=None)
    ap.add_argument("--hue-mix", type=float, default=0.3)
    ap.add_argument("--slab", default=None, help="R,G,B floor albedo")
    ap.add_argument("--wall-mul", type=float, default=None)
    ap.add_argument("--wall-blend", type=float, default=None)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    random.seed(args.seed)

    png = os.path.join(args.dir, "tileset.png")
    im = Image.open(png).convert("RGBA")
    meta = json.load(open(os.path.join(args.dir, "tileset.json")))
    tiles = meta["tileset_data"]["tiles"]

    def bbox(t):
        b = t["bounding_box"]
        return (b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"])

    if args.desat is not None or args.hue_to is not None:
        px = im.load()
        for y in range(im.height):
            for x in range(im.width):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                if args.desat is not None:
                    s *= args.desat
                if args.hue_to is not None:
                    h = (h + (args.hue_to - h) * args.hue_mix) % 1
                r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
                px[x, y] = (int(r2 * 255), int(g2 * 255), int(b2 * 255), a)

    all_lower = [t for t in tiles
                 if all(t["corners"][k] == "lower" for k in ("NW", "NE", "SW", "SE"))]
    floor_tile = all_lower[0] if all_lower else None

    if args.slab and floor_tile is not None:
        base = tuple(int(v) for v in args.slab.split(","))
        joint = tuple(max(0, v - 12) for v in base)
        t = Image.new("RGBA", (32, 32))
        px = t.load()
        for y in range(32):
            for x in range(32):
                j = random.randint(-3, 3)
                px[x, y] = (base[0] + j, base[1] + j, base[2] + j, 255)
        for _ in range(4):
            cx, cy, r = random.randint(4, 27), random.randint(4, 27), random.randint(2, 4)
            for y in range(max(0, cy - r), min(32, cy + r)):
                for x in range(max(0, cx - r), min(32, cx + r)):
                    rr, gg, bb, a = px[x, y]
                    px[x, y] = (rr - 4, gg - 4, bb - 5, a)
        for i in range(32):
            px[31, i] = (*joint, 255)
            px[i, 31] = (*joint, 255)
        im.paste(t, bbox(floor_tile))

    if args.wall_mul is not None or args.wall_blend is not None:
        for tl in tiles:
            if tl is floor_tile:
                continue
            b = bbox(tl)
            region = im.crop(b)
            mean = region.convert("RGB").resize((1, 1), Image.BILINEAR).getpixel((0, 0))
            px = region.load()
            mul = args.wall_mul if args.wall_mul is not None else 1.0
            mix = args.wall_blend if args.wall_blend is not None else 0.0
            for y in range(region.height):
                for x in range(region.width):
                    r, g, bl, a = px[x, y]
                    if a == 0:
                        continue
                    r = r * (1 - mix) + mean[0] * mix
                    g = g * (1 - mix) + mean[1] * mix
                    bl = bl * (1 - mix) + mean[2] * mix
                    px[x, y] = (int(r * mul), int(g * mul), int(bl * mul), a)
            im.paste(region, b)

    im.save(png)
    f = im.crop(bbox(floor_tile)) if floor_tile is not None else im
    d = list(f.convert("RGB").getdata())
    avg = tuple(round(sum(c[i] for c in d) / len(d)) for i in range(3))
    print(f"{args.dir}: floor tile avg now {avg}")


if __name__ == "__main__":
    main()
