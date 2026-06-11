"""Screenshot one story room for layout verification.

Boots its own game server (MINDLOCK_FAKE=1) on --port, opens the game with ?dev=1&room=N
in headless chromium, hides the menu overlay, and saves a PNG of the 640x448 canvas.

  .venv/bin/python scripts/snap_room.py --room 3 --port 7971 --out /tmp/room03.png
  .venv/bin/python scripts/snap_room.py --room 3 --port 7971 --out /tmp/room03g.png --grid
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wait_health(port: int, timeout: float = 30.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=2)
            return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError(f"server on :{port} never came up")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", type=int, required=True, help="1-based room number")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--grid", action="store_true", help="toggle the placement debug overlay (G)")
    ap.add_argument("--scale", type=int, default=2, help="device scale factor for a crisper PNG")
    args = ap.parse_args()

    env = {**os.environ, "MINDLOCK_FAKE": "1", "MINDLOCK_PORT": str(args.port)}
    srv = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "scripts", "run_game.py")],
        env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        wait_health(args.port)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 900, "height": 640},
                                    device_scale_factor=args.scale)
            page.goto(f"http://127.0.0.1:{args.port}/?dev=1&room={args.room}")
            page.wait_for_timeout(3000)            # tileset + sprites + first frames
            page.evaluate("document.getElementById('menu').style.display='none'")
            if args.grid:
                page.evaluate("window.__mindlock.debug = true")
            page.wait_for_timeout(700)
            page.locator("#screen").screenshot(path=args.out)
            browser.close()
        print(f"saved {args.out}")
    finally:
        os.killpg(os.getpgid(srv.pid), signal.SIGTERM)


if __name__ == "__main__":
    main()
