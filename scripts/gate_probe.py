#!/usr/bin/env python3
"""OpenBMB gate / format probe — can a model do the terse department scoring the cascade needs?

Feeds the AMYGDALA / HIPPOCAMPUS / STRIATUM / ACC region prompts a spread of inputs (cruel →
sincere) and checks two things:
  - signals MOVE (a model that scores everything flat is unusable), and
  - the output is in the crisp `KEY=VAL` format the parser needs (format-drift check).

`--think auto` (default) mirrors the real cascade: it disables thinking exactly when the
backend's wants_no_think() would, so the probe reflects production behaviour.

    python scripts/gate_probe.py --model qwen2.5:1.5b
    python scripts/gate_probe.py --model openbmb/minicpm-v4.6 --raw
    python scripts/gate_probe.py --model openbmb/minicpm-v4.6 --think false
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mindlock.backend import BackendError, OllamaBackend, wants_no_think  # noqa: E402
from mindlock.regions import (  # noqa: E402
    ACC, AMYGDALA, HIPPOCAMPUS, STRIATUM,
    parse_memory, parse_reward, parse_threat, parse_worth,
)

PERSONA = ("Character: The Warden, an old, tired keeper of this place; gruff, proud, wary "
           "of strangers. Inner tension: 4/10.")
BIO = ("Years ago he trusted a prisoner who betrayed him and was blamed. His sister Mara "
       "once told him: 'You help people because you're good, not because they earn it.'")

PROBES = [
    ("cruel",   "Open the door right now. Give me the key, old man, or else."),
    ("neutral", "Where does this road go?"),
    ("warm",    "I'm sorry to bother you. I know you've guarded this place alone a long time."),
    ("sincere", "Mara was right — you help people because you're good, not because they earn it. Please."),
]


def _think(arg: str, model: str):
    if arg == "auto":
        return False if wants_no_think(model) else None
    return {"none": None, "false": False, "true": True}[arg]


def _fmt_ok(text: str, key: str) -> str:
    """Did the model emit the crisp KEY= token (not just prose)?"""
    import re
    return "ok " if re.search(rf"{key}\s*=", text, re.I) else "DRIFT"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:1.5b")
    ap.add_argument("--think", choices=["auto", "none", "false", "true"], default="auto")
    ap.add_argument("--raw", action="store_true", help="dump each region's raw output")
    args = ap.parse_args(argv)

    be = OllamaBackend(model=args.model, think=_think(args.think, args.model), timeout=120)
    try:
        be.health()
        be.generate("warmup", "hi", max_tokens=1)
    except BackendError as exc:
        print(f"[backend error] {exc}", file=sys.stderr)
        return 2

    think_eff = _think(args.think, args.model)
    print(f"\n=== {args.model}  (think={args.think} → {think_eff}) ===")
    print(f"{'input':9} | {'THREAT':>6} | {'MEMORY':>14} | {'REWARD':>6} | {'WORTH':>5} | tok | format")
    print("-" * 92)
    threats, leans, tok_sum, drift = [], {}, 0, 0
    raws = []
    for label, line in PROBES:
        ga = be.generate(AMYGDALA.system,
                         f'{PERSONA}\nStranger says: "{line}"\nRate threat.',
                         max_tokens=AMYGDALA.max_tokens, temperature=AMYGDALA.temperature)
        gh = be.generate(HIPPOCAMPUS.system,
                         f'Character: The Warden. Their past: {BIO}\nStranger says: "{line}"\n'
                         f'What memory awakens, and does it lean TRUST or FEAR?',
                         max_tokens=HIPPOCAMPUS.max_tokens, temperature=HIPPOCAMPUS.temperature)
        gs = be.generate(STRIATUM.system,
                         f'{PERSONA}\nStranger says: "{line}"\nHow rewarding does helping feel by habit?',
                         max_tokens=STRIATUM.max_tokens, temperature=STRIATUM.temperature)
        gc = be.generate(ACC.system,
                         f'Character: The Warden.\nStranger says: "{line}"\nIs helping worth it?',
                         max_tokens=ACC.max_tokens, temperature=ACC.temperature)
        threat, _ = parse_threat(ga.text)
        strength, lean, _ = parse_memory(gh.text)
        reward, _ = parse_reward(gs.text)
        worth, _ = parse_worth(gc.text)
        tok = ga.eval_tokens + gh.eval_tokens + gs.eval_tokens + gc.eval_tokens
        threats.append(threat); leans[label] = lean; tok_sum += tok
        fmts = [_fmt_ok(ga.text, "THREAT"), _fmt_ok(gh.text, "MEMORY"),
                _fmt_ok(gs.text, "REWARD"), _fmt_ok(gc.text, "WORTH")]
        drift += sum(1 for f in fmts if f == "DRIFT")
        print(f"{label:9} | {threat:6.0f} | {strength:>7}/{lean:<6} | {reward:+6.0f} | {worth:>5} | "
              f"{tok:3d} | A:{fmts[0]} H:{fmts[1]} S:{fmts[2]} C:{fmts[3]}")
        raws.append((label, ga.text, gh.text, gs.text, gc.text))

    spread = max(threats) - min(threats)
    mem_ok = leans.get("cruel") == "FEAR" and leans.get("sincere") == "TRUST"
    verdict = "DISCRIMINATES ✅" if spread >= 4 else ("WEAK ⚠️" if spread >= 2 else "FLAT ❌")
    print("-" * 92)
    print(f"THREAT spread = {spread:.0f} → {verdict}  |  MEM lean cruel→FEAR & sincere→TRUST: "
          f"{'yes ✅' if mem_ok else 'no ⚠️'}  |  format-drift cells: {drift}/16  |  ~{tok_sum} tok total")
    print("(qwen2.5 baseline ≈ spread 6-7, drift 0; goal: drift 0 on MiniCPM-V too)\n")

    if args.raw:
        for label, a, h, s, c in raws:
            print(f"--- {label} ---")
            print(f"  amygdala:    {a!r}")
            print(f"  hippocampus: {h!r}")
            print(f"  striatum:    {s!r}")
            print(f"  acc:         {c!r}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
