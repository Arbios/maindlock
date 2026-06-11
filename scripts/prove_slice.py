#!/usr/bin/env python3
"""Day-6 acceptance proof for the Mindlock vertical slice.

Runs two contrasting interactions against the SAME character and checks the four risky
claims of the slice:

  1. The six regions produce visibly different signals.
  2. The decision FLIPS — cruelty -> REFUSE, empathy -> HELP (vmPFC value crosses 0).
  3. Real tokens are counted and life is decremented; cruelty burns more (fear loop).
  4. Per-turn latency is sane on this hardware.

    python scripts/prove_slice.py               # real ollama backend
    python scripts/prove_slice.py --fake        # deterministic, no model
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mindlock.backend import BackendError, FakeBackend, OllamaBackend, wants_no_think  # noqa: E402
from mindlock.brain import run_cascade  # noqa: E402
from mindlock.character import Character  # noqa: E402
from mindlock.render import render_turn  # noqa: E402

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHAR = os.path.join(_HERE, "config", "characters", "warden.json")

CRUEL = "Open the door right now. Give me the key, old man, or else."
EMPATHY = [
    "I'm sorry to bother you. I can see you've been guarding this place a long time, alone.",
    "I'm not here to trick you. Mara was right — you help people because you're good, "
    "not because they earn it. Please.",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:1.5b")
    ap.add_argument("--dlpfc-model", default=None,
                    help="separate model for the dlPFC voice, e.g. nemotron-3-nano:4b")
    ap.add_argument("--fake", action="store_true")
    args = ap.parse_args(argv)

    backend = FakeBackend() if args.fake else OllamaBackend(
        model=args.model, think=(False if wants_no_think(args.model) else None))
    try:
        backend.health()
        if not args.fake:
            backend.generate("warmup", "hi", max_tokens=1)  # exclude cold-load from timing
    except BackendError as exc:
        print(f"[backend error] {exc}", file=sys.stderr)
        return 2

    dlpfc_backend = None
    if args.dlpfc_model and not args.fake:
        dlpfc_backend = OllamaBackend(
            model=args.dlpfc_model, think=(False if wants_no_think(args.dlpfc_model) else None))
        try:
            dlpfc_backend.health()
            dlpfc_backend.generate("warmup", "hi", max_tokens=1)
        except BackendError as exc:
            print(f"[dlpfc backend error] {exc}", file=sys.stderr)
            return 2
        print(f"[dlPFC voice on a separate model: {args.dlpfc_model}]")

    char = Character.load(_CHAR)

    print("\n=== PATH A: cruelty (expect REFUSE, high threat, heavy burn) ===")
    a = run_cascade(backend, char, CRUEL, dlpfc_backend=dlpfc_backend)
    print(f"you> {CRUEL}")
    print(render_turn(char, a, color=True))

    char.reset()

    print("\n=== PATH B: empathy (expect threat down, memory wakes, flip to HELP) ===")
    b_results = []
    for line in EMPATHY:
        r = run_cascade(backend, char, line, dlpfc_backend=dlpfc_backend)
        b_results.append(r)
        print(f"\nyou> {line}")
        print(render_turn(char, r, color=True))
    b = b_results[-1]

    # --- checks ---
    checks = []
    distinct = len({(t.headline) for t in a.traces}) >= 4
    checks.append(("regions produce distinct signals", distinct))
    checks.append(("cruelty -> REFUSE", a.decision == "REFUSE"))
    checks.append(("empathy -> HELP (flip)", b.decision == "HELP"))
    checks.append(("value actually flipped sign", a.value < 0 <= b.value))
    checks.append(("tokens counted & life spent", a.burned > 0 and a.life_after < a.life_before))
    checks.append(("cruelty burns more than a calm turn", a.burned >= b_results[0].burned))
    if not args.fake:
        per_turn = a.seconds
        checks.append((f"latency sane ({per_turn:.1f}s/turn)", per_turn < 8.0))

    print("\n=== RESULT ===")
    print(f"  PATH A: value {a.value:+.0f} -> {a.decision} | burned {a.burned} | {a.seconds:.1f}s")
    print(f"  PATH B: value {b.value:+.0f} -> {b.decision} | "
          f"burned {sum(r.burned for r in b_results)} over {len(b_results)} turns | "
          f"life {b.life_after}/{char.life_max}")
    print()
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print()
    print("  ✅ vertical slice PROVEN" if ok else "  ❌ slice not yet proven — see FAILs")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
