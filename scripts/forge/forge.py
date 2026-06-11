#!/usr/bin/env python3
"""Mindlock character forge — the offline factory that mints reusable characters.

One mint = one local-LLM pass that produces a whole person: a grounded story (biography, fear,
a soft spot, a guarded secret) AND the two prompts that will give them a face — a FLUX
oil-painting portrait prompt and a Pixellab top-down sprite prompt. The heavy art is rendered
by separate stages that read this roster:

    # 1) mint identities + asset prompts (fast — local llama)
    PYTHONPATH=src .venv/bin/python scripts/forge/forge.py mint --n 6

    # 2) render portraits for everyone still missing one (FLUX on Modal)
    .venv/bin/python -m modal run scripts/flux/modal_flux.py

    # 3) render sprites (Pixellab) — Claude drives the MCP from each entry's sprite_prompt,
    #    downloads the 8 directions into static/sprites/npc/{slug}/, then:
    PYTHONPATH=src .venv/bin/python scripts/forge/forge.py mark --slug <slug> --asset sprite

    # inspect what's done / pending at any time
    PYTHONPATH=src .venv/bin/python scripts/forge/forge.py status

The game samples ready members automatically (see mindlock.roster.build_world).
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from mindlock import roster  # noqa: E402
from mindlock.backend import OllamaBackend  # noqa: E402
from mindlock.generator import _extract_json  # noqa: E402  (reuse the lenient JSON grabber)

_SYS = "You are a sharp character designer. Output ONLY valid JSON — no prose, no markdown fences."

# The roster is setting-agnostic on purpose: the FLUX style anchor (oil-painting, candlelit,
# muted, somber) unifies the *look* regardless of who the person is, so we get a cohesive
# painterly cast across wildly different rooms.
_PROMPT = """Invent ONE vivid, grounded human character a stranger might have to win over to get
something. Make them specific and memorable — a wound, a contradiction, a soft spot.

{steer}

Return ONLY JSON of this exact shape:
{{
 "name": "first and last name",
 "gender": "male or female (must match the name)",
 "age": 0,
 "title": "short role, e.g. 'the night warden', 'a grieving widow', 'the pawnbroker'",
 "voice": "one phrase: how they speak (clipped, warm, evasive, formal...)",
 "persona": "one vivid sentence capturing who they are",
 "biography": "3-4 sentences: their life, a wound, and the soft spot underneath",
 "fear": "what they are most afraid of",
 "soft_spot": "ONE personal word that slips past their guard — a loved one's name or a lost thing",
 "secret": "a guarded truth they would only admit once trust is earned",
 "appearance": "physical look in 1-2 sentences: age, build, hair, clothing, distinguishing marks",
 "portrait_prompt": "head-and-shoulders SUBJECT description for an oil-painting portrait — describe ONLY the person and their expression, no art-style words (style is added separately)",
 "sprite_prompt": "concise description for a TOP-DOWN pixel-art game character: clothing, colors, silhouette, kept simple and readable at small size"
}}
Rules: soft_spot is a single concrete word. Keep them human and grounded (no fantasy). The
portrait_prompt and sprite_prompt must clearly describe the SAME person as appearance."""

_REQ = ("name", "gender", "title", "voice", "persona", "biography", "fear", "soft_spot",
        "secret", "appearance", "portrait_prompt", "sprite_prompt")


def _valid(d) -> bool:
    return bool(isinstance(d, dict) and all(str(d.get(k, "")).strip() for k in _REQ)
                and str(d.get("gender", "")).lower() in ("male", "female"))


def _mint_one(be: OllamaBackend, seed: int, gender: str, role: str, theme: str,
              attempts: int = 4) -> dict | None:
    steer = []
    if gender:
        steer.append(f"The character is {gender}.")
    if role:
        steer.append(f"They are: {role}.")
    if theme:
        steer.append(f"Setting/theme: {theme}.")
    steer.append("Avoid prison/asylum clichés unless the theme demands it.")
    prompt = _PROMPT.format(steer=" ".join(steer))
    for i in range(attempts):
        g = be.generate(_SYS, prompt, max_tokens=900, temperature=0.95, seed=seed + i * 101)
        d = _extract_json(g.text)
        if _valid(d):
            d["gender"] = str(d["gender"]).lower()
            d["slug"] = _unique_slug(roster.slugify(d["name"]))
            d["status"] = {"portrait": False, "sprite": False}
            return d
    return None


def _unique_slug(base: str) -> str:
    slug, n = base, 2
    while roster.load_entry(slug) is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


def cmd_mint(args) -> int:
    be = OllamaBackend(model=args.model, timeout=180)
    made = 0
    for j in range(args.n):
        gender = args.gender
        if not gender and args.n > 1:                 # balance genders across a batch by default
            gender = "female" if j % 2 else "male"
        d = _mint_one(be, args.seed + j * 1000, gender, args.role, args.theme)
        if not d:
            print(f"  [{j + 1}/{args.n}] mint failed (invalid JSON after retries)")
            continue
        roster.save_entry(d)
        made += 1
        print(f"  [{j + 1}/{args.n}] ✦ {d['name']} — {d['title']} ({d['gender']})  → {d['slug']}.json")
        print(f"        soft spot: '{d['soft_spot']}'   fear: {d['fear']}")
    print(f"\nminted {made}/{args.n} into {os.path.relpath(roster.ROSTER_DIR, _ROOT)}/")
    if made:
        print("next: render portraits  → .venv/bin/python -m modal run scripts/flux/modal_flux.py")
        print("      render sprites     → Pixellab per entry's sprite_prompt (see `status`)")
    return 0


def cmd_status(args) -> int:
    entries = [roster.sync_status(e) for e in roster.list_entries()]
    if not entries:
        print("roster empty — run `mint` first.")
        return 0
    ready = 0
    for e in entries:
        p = "🖼" if e["status"]["portrait"] else "·"
        s = "🧍" if e["status"]["sprite"] else "·"
        done = e["status"]["portrait"] and e["status"]["sprite"]
        ready += bool(e["status"]["sprite"])
        print(f"  {p}{s}  {e['name']:22} {e['title']:24} [{e['gender'][:1]}]  {e['slug']}")
        if args.verbose and not done:
            if not e["status"]["sprite"]:
                print(f"        sprite_prompt:   {e['sprite_prompt']}")
            if not e["status"]["portrait"]:
                print(f"        portrait_prompt: {e['portrait_prompt']}")
    print(f"\n{len(entries)} minted · {ready} playable (sprite present) · 🖼 portrait 🧍 sprite")
    return 0


def cmd_mark(args) -> int:
    roster.mark(args.slug, args.asset, value=not args.unset)
    e = roster.sync_status(roster.load_entry(args.slug))
    print(f"{args.slug}: portrait={e['status']['portrait']} sprite={e['status']['sprite']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mindlock character forge")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mint", help="LLM-mint character identities + asset prompts")
    m.add_argument("--n", type=int, default=1)
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--gender", default="", choices=["", "male", "female"])
    m.add_argument("--role", default="", help="steer the role, e.g. 'a wary pawnbroker'")
    m.add_argument("--theme", default="", help="steer the setting/theme")
    m.add_argument("--model", default="llama3.1:latest")
    m.set_defaults(func=cmd_mint)

    s = sub.add_parser("status", help="show roster + asset status")
    s.add_argument("-v", "--verbose", action="store_true", help="show pending asset prompts")
    s.set_defaults(func=cmd_status)

    k = sub.add_parser("mark", help="flip an asset flag after it's rendered")
    k.add_argument("--slug", required=True)
    k.add_argument("--asset", required=True, choices=["portrait", "sprite"])
    k.add_argument("--unset", action="store_true")
    k.set_defaults(func=cmd_mark)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
