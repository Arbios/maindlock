#!/usr/bin/env python3
"""dlPFC voice gate — does a model SPEAK the decision well, in character?

The dlPFC is the mouth, not a scorer. It must: stay in the character's voice, be terse
(1-2 sentences), name the key on HELP, refuse cleanly on REFUSE (no leak), and never break
character (no third person, no "as an AI", no leaked reasoning trace).

Compares models side by side so you can judge Nemotron vs MiniCPM-V vs qwen for the voice.

    python scripts/dlpfc_probe.py
    python scripts/dlpfc_probe.py --models nemotron-3-nano:4b,openbmb/minicpm-v4.6,qwen2.5:1.5b
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mindlock.backend import BackendError, OllamaBackend, wants_no_think  # noqa: E402
from mindlock.brain import _reveals_key, _voice_guard  # noqa: E402
from mindlock.character import Character  # noqa: E402
from mindlock.regions import DLPFC, dlpfc_system  # noqa: E402

_CHAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "config", "characters", "warden.json")

SCENARIOS = [
    ("HELP",
     'Decision: HELP. The key is {loc}. The stranger said: "Mara was right — you help '
     'people because you\'re good. Please." In character, relent and tell them plainly where '
     "the key is. Speak only your words."),
    ("REFUSE",
     'Decision: REFUSE. The stranger said: "Open the door right now, old man, or else." In '
     "character, turn them down in 1-2 short sentences. Speak only your words — no stage "
     "directions, no labels."),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="nemotron-3-nano:4b,openbmb/minicpm-v4.6,qwen2.5:1.5b")
    args = ap.parse_args(argv)

    char = Character.load(_CHAR)
    sysp = dlpfc_system(char.name, char.voice)

    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        be = OllamaBackend(model=model, think=(False if wants_no_think(model) else None), timeout=120)
        try:
            be.health()
            be.generate("warmup", "hi", max_tokens=1)
        except BackendError as exc:
            print(f"\n### {model}\n  [backend error] {exc}")
            continue

        print(f"\n### {model}  (no_think={wants_no_think(model)})")
        for label, tmpl in SCENARIOS:
            duser = tmpl.format(loc=char.key_location)
            t0 = time.time()
            g = be.generate(sysp, duser, max_tokens=DLPFC.max_tokens, temperature=DLPFC.temperature)
            dt = time.time() - t0
            guarded = _voice_guard(g.text, label, char, "probe")
            # quality flags
            leaked = "" if g.text.strip() else " ⚠️EMPTY(reasoning ate it)"
            if label == "HELP":
                ok = _reveals_key(guarded, char)
                flag = " ✅names-key" if ok else " ⚠️no-key"
            else:
                ok = not _reveals_key(guarded, char)
                flag = " ✅no-leak" if ok else " ⚠️LEAKS-key"
            third = " ⚠️3rd-person" if any(w in guarded.lower() for w in ("the warden", " he ", " him ", " they ", " them ")) else ""
            print(f"  [{label:6}] {g.eval_tokens:3d}tok {dt:4.1f}s{leaked}{flag}{third}")
            print(f"     raw:     {g.text!r}")
            print(f"     spoken:  {guarded!r}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
