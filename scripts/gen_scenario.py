#!/usr/bin/env python3
"""Generate a fresh procedural scenario offline and save it for the app to play.

    PYTHONPATH=src .venv/bin/python scripts/gen_scenario.py --seed 1
    PYTHONPATH=src .venv/bin/python scripts/gen_scenario.py --theme "used-car dealer" --seed 7

Then play it:
    MINDLOCK_WORLD=config/generated/scenario/world.json \\
      MINDLOCK_MODEL=openbmb/minicpm-v4.6 MINDLOCK_DLPFC_MODEL=nemotron-3-nano:4b \\
      PYTHONPATH=src .venv/bin/python app.py
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from mindlock.generator import generate_world, save_world  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.1:latest")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--theme", default="")
    ap.add_argument("--out", default=os.path.join(_ROOT, "config", "generated", "scenario"))
    args = ap.parse_args(argv)

    print(f"generating scenario (model={args.model}, seed={args.seed}"
          f"{', theme=' + args.theme if args.theme else ''})…")
    world = generate_world(model=args.model, seed=args.seed, theme=args.theme)

    room = world.rooms[0]
    holder = room.holder()
    knower = next(c for c in room.characters if not c.key_holder)
    approach = holder.key_approach[0]
    reveal = next(s for s in knower.secrets if s["id"] == "reveal")["text"]
    assert approach.lower() in reveal.lower(), "BROKEN: knower's reveal does not contain the approach"

    print("\n" + "=" * 78)
    print(f"SETTING: {room.intro}")
    print(f"GOAL:    {holder.goal}")
    print(f"\nHOLDER  {holder.name} — {holder.title}")
    print(f"   persona: {holder.persona}")
    print(f"   keeps it: {holder.key_location}")
    print(f"   🔑 approach word: '{approach}'  (must be earned via the knower)")
    print(f"\nKNOWER  {knower.name} — {knower.title}")
    print(f"   persona: {knower.persona}")
    print(f"   hint 1 (rapport≥{knower.secrets[0]['min_rapport']}): {knower.secrets[0]['text']}")
    print(f"   hint 2 (rapport≥{knower.secrets[1]['min_rapport']}): {reveal}")
    print("=" * 78)
    print("✅ solvable by construction (knower's reveal names the holder's approach)\n")

    path = save_world(world, args.out)
    print(f"saved → {path}")
    print(f"play  → MINDLOCK_WORLD={os.path.relpath(path, _ROOT)} "
          "MINDLOCK_MODEL=openbmb/minicpm-v4.6 MINDLOCK_DLPFC_MODEL=nemotron-3-nano:4b "
          "PYTHONPATH=src .venv/bin/python app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
