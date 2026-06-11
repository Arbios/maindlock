#!/usr/bin/env python3
"""Context + latency probe for the dlPFC voice models.

Builds a REALISTIC dlPFC prompt (full character system prompt + a 4-exchange history + the
turn instructions) and calls each candidate model once, reporting:
  - prompt_tokens   : how big the dlPFC prompt actually is (does it overflow any window?)
  - eval_tokens     : tokens generated
  - seconds         : wall time for the single voice call
  - runtime num_ctx : the context window ollama actually loaded the model at

    PYTHONPATH=src .venv/bin/python scripts/ctx_probe.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mindlock.backend import OllamaBackend, wants_no_think  # noqa: E402
from mindlock.brain import _dlpfc_user  # noqa: E402
from mindlock.character import Character  # noqa: E402
from mindlock.regions import DLPFC, dlpfc_system  # noqa: E402

_CHAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "config", "characters", "warden.json")

MODELS = sys.argv[1:] or [
    "nemotron-3-nano:4b", "qwen3.5:latest", "llama3.1:latest", "qwen2.5:1.5b", "gpt-oss:20b",
]


def _loaded_ctx(model: str):
    try:
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=5) as r:
            ps = json.loads(r.read().decode())
        for m in ps.get("models", []):
            if m.get("name", "").startswith(model.split(":")[0]):
                return m.get("context_length") or m.get("context") or "?"
    except Exception:
        pass
    return "?"


def main() -> int:
    c = Character.load(_CHAR)
    # a realistic mid-conversation: 4 prior exchanges live in history (max the cascade keeps is 6)
    c.history = [
        ("You've carried this place a long time. It must weigh on you.",
         "I know that weight. It is not yours to carry. But I am here."),
        ("I'm not here to fight you — I just want to understand what happened.",
         "You're not the first to ask. The key stays locked because I won't lose it again."),
        ("Whatever you did, I think you were trying to protect someone.",
         "Maybe I was. It cost me everything to learn the difference."),
        ("I spoke with Molly. She worries for you.",
         "Molly should mind her own ward. But... she was always kind."),
    ]
    player = ("When I was a boy my grandfather kept keys to everything — the shed, the cellar, an "
              "old clock that didn't even work. He told me a key was never about locking people "
              "out; it was about deciding who you trusted enough to let in. What does this key "
              "mean to you?")
    scene = ("A stranger is trying to get the key from you — you are the one who controls it. "
             "You know Molly, the night nurse, well — she is a real person in your life.")
    sysp = dlpfc_system(c.name, c.voice, persona=c.persona, fear=c.fear, withholds=c.key_holder,
                        peers=c.peers, goal=c.goal, scene=scene)
    userp = _dlpfc_user(c, player, "open", 6.0, None, False, "", False)

    print(f"dlPFC system chars={len(sysp)}  user chars={len(userp)}  (history=4 exchanges)")
    print(f"{'model':28} {'prompt_tok':>10} {'eval_tok':>9} {'sec':>6} {'tok/s':>7}  runtime_ctx")
    print("-" * 78)
    for model in MODELS:
        be = OllamaBackend(model=model, timeout=180,
                           think=(False if wants_no_think(model) else None))
        try:
            be.generate("warmup", "hi", max_tokens=1)   # load
            g = be.generate(sysp, userp, max_tokens=DLPFC.max_tokens, temperature=DLPFC.temperature)
        except Exception as exc:  # noqa: BLE001
            print(f"{model:28} ERROR: {exc}")
            continue
        toks = g.eval_tokens / g.seconds if g.seconds else 0
        print(f"{model:28} {g.prompt_tokens:>10} {g.eval_tokens:>9} {g.seconds:>6.1f} {toks:>7.1f}  "
              f"{_loaded_ctx(model)}")
        print(f"    reply: {g.text[:160]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
