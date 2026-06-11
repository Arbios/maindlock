"""Interactive REPL for the vertical slice.

    python -m mindlock.cli                  # talk to The Warden
    python -m mindlock.cli --model qwen2.5:1.5b
    python -m mindlock.cli --fake           # no model, deterministic backend

Commands inside the loop:  /reset   /state   /quit
"""
from __future__ import annotations

import argparse
import os
import sys

from .backend import BackendError, FakeBackend, OllamaBackend, wants_no_think
from .brain import run_cascade
from .character import Character
from .render import render_death, render_turn, render_win

_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_CHAR = os.path.join(_HERE, "config", "characters", "warden.json")


def _intro(c: Character) -> str:
    return (
        f"\nYou are locked in. {c.name} holds the only key — and right now his mind says no.\n"
        f"Talk to him. You don't break the lock; you change his decision.\n"
        f"(type /quit to leave, /reset to revive him)\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mindlock vertical slice")
    ap.add_argument("--model", default="qwen2.5:1.5b")
    ap.add_argument("--character", default=_DEFAULT_CHAR)
    ap.add_argument("--fake", action="store_true", help="use deterministic FakeBackend")
    args = ap.parse_args(argv)

    backend = FakeBackend() if args.fake else OllamaBackend(
        model=args.model, think=(False if wants_no_think(args.model) else None))
    try:
        backend.health()
    except BackendError as exc:
        print(f"[backend error] {exc}", file=sys.stderr)
        return 2

    character = Character.load(args.character)
    print(_intro(character))

    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/quit", "/q", "/exit"):
            return 0
        if line == "/reset":
            character.reset()
            print(f"  {character.name} draws a breath. (life restored)\n")
            continue
        if line == "/state":
            print(f"  life={character.life_tokens}/{character.life_max} "
                  f"arousal={character.arousal:.1f} decision={character.decision} "
                  f"alive={character.alive}\n")
            continue
        if not character.alive:
            print("  He is gone. /reset to try again.\n")
            continue

        result = run_cascade(backend, character, line)
        print(render_turn(character, result))
        if result.won:
            print(render_win(character))
            return 0
        if result.died:
            print(render_death(character))
        print()


if __name__ == "__main__":
    raise SystemExit(main())
