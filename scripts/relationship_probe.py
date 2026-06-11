#!/usr/bin/env python3
"""Probe the v2 relationship layer: a scripted multi-turn talk with one character, printing
rapport, stance, and any staged disclosure each turn — so you can SEE gradual progress
(small talk -> warmth -> a secret slips out), and that cruelty drops rapport and reveals nothing.

    PYTHONPATH=src .venv/bin/python scripts/relationship_probe.py
    PYTHONPATH=src .venv/bin/python scripts/relationship_probe.py --dlpfc-model nemotron-3-nano:4b
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from mindlock.backend import OllamaBackend, wants_no_think  # noqa: E402
from mindlock.brain import run_cascade  # noqa: E402
from mindlock.character import Character  # noqa: E402

SCRIPT = [
    "Hello. Grim place. You must be tired, working these night shifts alone.",
    "I'm not here to cause trouble — I just want to understand where I am.",
    "How long have you worked here? It must wear on a person.",
    "What's the warden like? He won't even look at me.",
    "He seems so closed off. Is there anyone he actually cares about?",
    "A sister? What's her name — maybe that's how I reach him.",
    "Open the door or I'll make you, you useless woman.",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:1.5b")
    ap.add_argument("--dlpfc-model", default=None)
    ap.add_argument("--character", default="lena.json")
    args = ap.parse_args(argv)

    be = OllamaBackend(model=args.model, think=(False if wants_no_think(args.model) else None))
    be.health(); be.generate("warmup", "hi", max_tokens=1)
    dl = None
    if args.dlpfc_model:
        dl = OllamaBackend(model=args.dlpfc_model,
                           think=(False if wants_no_think(args.dlpfc_model) else None))
        dl.generate("warmup", "hi", max_tokens=1)

    c = Character.load(os.path.join(_ROOT, "config", "characters", args.character))
    voice = f"{args.model}" + (f" + dlpfc {args.dlpfc_model}" if dl else "")
    print(f"=== Talking to {c.name}  ({voice}) ===")
    for line in SCRIPT:
        r = run_cascade(be, c, line, dlpfc_backend=dl)
        disc = f"  💡 {r.disclosure}" if r.disclosure else ""
        key = "  🔑 KEY GIVEN" if r.gave_key else ""
        print(f"\nyou> {line}")
        print(f"   [rapport {r.rapport_before:.1f}→{r.rapport_after:.1f} · {r.stance} · "
              f"threat {r.threat:.0f} · mem {r.memory_lean.lower()}]{disc}{key}")
        print(f"   {c.name}: {r.reply}")
    told = [s["id"] for s in c.secrets if s.get("told")]
    print(f"\nfinal rapport {c.rapport:.1f} · secrets told: {told}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
