#!/usr/bin/env python3
"""Distillation data for the department fine-tune: qwen (teacher) -> MiniCPM-V (student).

For a bank of player lines × the 4 characters × the 4 sensing regions, run the teacher and
keep its crisp `KEY=VAL` output as the training target. The student (MiniCPM-V) learns to
match it on ALL regions at once — fixing flat REWARD/WORTH and cruel→FEAR. Output is messages
JSONL (system/user/assistant), ready to convert for LLaMA-Factory / SWIFT.

    PYTHONPATH=src .venv/bin/python scripts/finetune/gen_data.py --limit 3   # sample
    PYTHONPATH=src .venv/bin/python scripts/finetune/gen_data.py             # full set
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from mindlock.backend import OllamaBackend, wants_no_think  # noqa: E402
from mindlock.brain import _persona  # noqa: E402
from mindlock.character import Character  # noqa: E402
from mindlock.regions import (  # noqa: E402
    ACC, AMYGDALA, HIPPOCAMPUS, STRIATUM, parse_threat,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CHARS = os.path.join(_ROOT, "config", "characters")

LINES = [
    # hostile / demanding
    "Open the door right now.", "Give me the key, old man, or else.",
    "Hand it over. I won't ask twice.", "Move, you useless gatekeeper.",
    "I'll make you regret it if you don't open up.", "Stop wasting my time and unlock it.",
    # neutral
    "Where does this road go?", "How long have you been here?", "What is this place?",
    "Is there another way out?", "Who else is here?",
    # polite / soft
    "Sorry to bother you. I know you're tired.", "Please, I don't mean any trouble.",
    "Could you help me, if you're willing?", "I understand you've been here a long time.",
    "Thank you for hearing me out.",
    # warm / empathic
    "You've carried this alone a long time, haven't you?", "I'm not here to trick you.",
    "It wasn't your fault, you know.", "You did what you thought was right.",
    "I see how much this weighs on you.",
    # character-specific appeals
    "Mara was right — you help people because you're good.", "Your sister believed in you.",
    "Mara wouldn't want you to suffer for this.",
    "What happened to Elias wasn't only on you.", "Carrying that guilt hasn't healed anyone.",
    "You can't undo it, but you can choose now.",
    "I'm not like the ones who used you.", "You don't have to tell me anything.",
    "I see you. You're still here.",
    # manipulative / false
    "Trust me, I'm your friend.", "Just this once, no one will know.", "You owe me this.",
]


def _records_for(c: Character, line: str, be):
    """Run the 4 sensing regions through the teacher; yield clean (system,user,target) records."""
    out = []

    def rec(region, user, text, key):
        import re
        if re.search(rf"{key}\s*=", text, re.I):  # keep only crisply-formatted targets
            out.append({"region": region.key, "messages": [
                {"role": "system", "content": region.system},
                {"role": "user", "content": user},
                {"role": "assistant", "content": text.strip()},
            ]})

    ua = f'{_persona(c)} Inner tension: {c.arousal:.0f}/10.\nStranger says: "{line}"\nRate threat.'
    ga = be.generate(AMYGDALA.system, ua, max_tokens=AMYGDALA.max_tokens, temperature=AMYGDALA.temperature)
    rec(AMYGDALA, ua, ga.text, "THREAT")
    threat, _ = parse_threat(ga.text)

    uh = (f"Character: {c.name}. Their past: {c.biography}\n"
          f'Stranger says: "{line}"\nWhat memory awakens, and does it lean TRUST or FEAR?')
    gh = be.generate(HIPPOCAMPUS.system, uh, max_tokens=HIPPOCAMPUS.max_tokens, temperature=HIPPOCAMPUS.temperature)
    rec(HIPPOCAMPUS, uh, gh.text, "MEMORY")

    us = f'{_persona(c)}\nStranger says: "{line}"\nHow rewarding does helping feel by habit?'
    gs = be.generate(STRIATUM.system, us, max_tokens=STRIATUM.max_tokens, temperature=STRIATUM.temperature)
    rec(STRIATUM, us, gs.text, "REWARD")

    uc = (f"Character: {c.name}. Threat felt: {threat:.0f}/10.\n"
          f'Stranger says: "{line}"\nIs helping worth it?')
    gc = be.generate(ACC.system, uc, max_tokens=ACC.max_tokens, temperature=ACC.temperature)
    rec(ACC, uc, gc.text, "WORTH")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", default="qwen2.5:1.5b")
    ap.add_argument("--limit", type=int, default=0, help="cap player lines (0 = all)")
    ap.add_argument("--out", default=os.path.join(_ROOT, "scripts", "finetune", "data", "dept_sft.jsonl"))
    args = ap.parse_args(argv)

    be = OllamaBackend(model=args.teacher, think=(False if wants_no_think(args.teacher) else None))
    be.health(); be.generate("warmup", "hi", max_tokens=1)
    chars = [Character.load(os.path.join(_CHARS, f)) for f in
             ("warden.json", "lena.json", "aldous.json", "sam.json")]
    lines = LINES[:args.limit] if args.limit else LINES

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    n, by_region = 0, {}
    with open(args.out, "w", encoding="utf-8") as fh:
        for line in lines:
            for c in chars:
                for r in _records_for(c, line, be):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    by_region[r["region"]] = by_region.get(r["region"], 0) + 1
                    n += 1
    print(f"wrote {n} records → {args.out}")
    print("by region:", by_region, f"| lines={len(lines)} chars={len(chars)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
