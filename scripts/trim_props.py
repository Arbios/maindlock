"""Trim transparent borders from generated prop PNGs and report measurements.

Usage: trim_props.py <raw_dir> <out_dir> [key ...]
Trims fully-transparent borders (keeping a 1px margin), verifies non-empty,
saves to <out_dir>/<key>.png and prints "key WxH -> WxH".
"""
import sys
from pathlib import Path
from PIL import Image

def trim(src: Path, dst: Path) -> str:
    im = Image.open(src).convert("RGBA")
    bbox = im.getbbox()  # bbox of non-zero (incl. alpha) region
    if bbox is None:
        return f"{src.stem} EMPTY (skipped)"
    # use alpha channel only for the bbox
    alpha = im.split()[3]
    bbox = alpha.getbbox()
    if bbox is None:
        return f"{src.stem} EMPTY-ALPHA (skipped)"
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - 1); y0 = max(0, y0 - 1)
    x1 = min(im.width, x1 + 1); y1 = min(im.height, y1 + 1)
    out = im.crop((x0, y0, x1, y1))
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)
    return f"{src.stem} {im.width}x{im.height} -> {out.width}x{out.height}"

if __name__ == "__main__":
    raw_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    keys = sys.argv[3:] or sorted(p.stem for p in raw_dir.glob("*.png"))
    for k in keys:
        src = raw_dir / f"{k}.png"
        if not src.exists():
            print(f"{k} MISSING")
            continue
        print(trim(src, out_dir / f"{k}.png"))
