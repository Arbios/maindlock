"""Play the full Mindlock world — rooms of minds, a key per room, a reputation that follows
you. Cruelty can still win a room, but it walks into the next one ahead of you.

    python -m mindlock.play                                   # dev engine (qwen)
    python -m mindlock.play --model openbmb/minicpm-v4.6 --dlpfc-model nemotron-3-nano:4b
    python -m mindlock.play --fake                            # no model, deterministic

Inside:  /talk <name>   /terminal <code>   /who   /rep   /reset   /quit
"""
from __future__ import annotations

import argparse
import os
import sys

from .backend import BackendError, FakeBackend, OllamaBackend, wants_no_think
from .brain import run_cascade
from .render import MORAL_CARD, moral_card_killed, render_death, render_turn
from .world import load_world

_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WORLD = os.path.join(_HERE, "config", "world.json")


def _backend(model: str, fake: bool):
    if fake:
        return FakeBackend()
    return OllamaBackend(model=model, think=(False if wants_no_think(model) else None))


def _show_room(world) -> None:
    r = world.room
    print(f"\n=== {r.name} ===   reputation {world.reputation:+d}")
    if r.intro:
        print(r.intro)
    print("With you:")
    holder = r.holder()
    for c in r.characters:
        title = f" — {c.title}" if c.title else ""
        key = "  (holds the key)" if holder and c.name == holder.name else ""
        gone = "  [gone]" if not c.alive else ""
        print(f"  · {c.name}{title}{key}{gone}")
    if r.terminal:
        print(f"  · A terminal [{('unlocked' if r.terminal.unlocked else 'locked')}] — {r.terminal.prompt}")
    print("(/talk <name>, /terminal <code>, /who, /rep, /reset, /quit)")


def _rep_note(delta: int) -> str:
    if delta > 0:
        return "Word spreads that you were kind."
    if delta <= -3:
        return "A mind went dark on your watch. Word travels ahead of you."
    return "Word spreads that you leaned on them."


def _progress(world, active):
    """If the room is solved, narrate and advance. Returns (game_over, active)."""
    if not world.room.solved():
        return False, active
    if world.last_room:
        print("\n  The last lock gives. The door swings open.")
        print(MORAL_CARD)
        return True, active
    print(f"\n  A way opens out of {world.room.name}. You carry your name into the next room.")
    world.advance()
    _show_room(world)
    return False, world.room.characters[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mindlock — play the world")
    ap.add_argument("--model", default="openbmb/minicpm-v4.6")
    ap.add_argument("--dlpfc-model", default="nemotron-3-nano:4b",
                    help="separate model for the dlPFC voice (pass '' to reuse --model)")
    ap.add_argument("--fake", action="store_true")
    args = ap.parse_args(argv)

    backend = _backend(args.model, args.fake)
    try:
        backend.health()
    except BackendError as exc:
        print(f"[backend error] {exc}", file=sys.stderr)
        return 2
    dlpfc_backend = None
    if args.dlpfc_model and not args.fake:
        dlpfc_backend = _backend(args.dlpfc_model, False)
        try:
            dlpfc_backend.health()
        except BackendError as exc:
            print(f"[dlpfc backend error] {exc}", file=sys.stderr)
            return 2

    world = load_world(_WORLD)
    world.enter_room()
    print("\nYou wake locked in. The way out runs through the people in these rooms — through")
    print("what they fear and what they remember. You don't break the locks. You change minds.")
    _show_room(world)
    active = world.room.characters[0]
    print(f"\n(you turn to {active.name})")

    while True:
        try:
            line = input(f"you→{active.name}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        low = line.lower()

        if low in ("/quit", "/q", "/exit"):
            return 0
        if low in ("/who", "/look"):
            _show_room(world)
            continue
        if low in ("/rep", "/reputation"):
            print(f"  reputation: {world.reputation:+d}")
            continue
        if low == "/reset":
            for c in world.room.characters:
                c.reset()
            world.enter_room()
            print("  The room resets. The minds steady.")
            continue
        if low.startswith("/talk"):
            c = world.room.char(line[5:])
            if not c:
                print("  No one here by that name.")
                continue
            ok, msg = world.can_engage(c)
            if not ok:
                print(f"  {msg}")
                continue
            active = c
            print(f"  (you turn to {active.name})")
            continue
        if low.startswith("/terminal"):
            t = world.room.terminal
            if not t:
                print("  There's no terminal here.")
                continue
            if t.try_code(line[len("/terminal"):], backend):
                print("  The terminal blinks green. ACCESS GRANTED.")
            else:
                print(f"  The terminal rejects it. {t.prompt}")
            over, active = _progress(world, active)
            if over:
                return 0
            continue

        # plain text -> speak to the active character
        ok, msg = world.can_engage(active)
        if not ok:
            print(f"  {msg}")
            continue

        r = run_cascade(backend, active, line, dlpfc_backend=dlpfc_backend,
                        learned=world.knows(active))
        if r.taught:
            world.learned.update(r.taught)
        print(render_turn(active, r))
        delta = world.update_reputation(r)
        if delta:
            print(f"  {_rep_note(delta)}  (reputation {world.reputation:+d})")
        if r.submitted:
            print(f"  💔 {active.name} breaks. The key changes hands — and something in them goes out.")
        if r.died:
            print(render_death(active))
            holder = world.room.holder()
            if holder and active.name == holder.name:
                print(moral_card_killed(active))
                return 0
            print(f"  Whatever {active.name} knew died with them. You are on your own now.")
        if r.disclosure:
            print(f"  💡 {active.name} lets slip: {r.disclosure}")
        elif r.caught_lie:
            print(f"  🤥 {active.name} catches your lie about {r.caught_lie}.")
        elif r.near_secret:
            print(f"  💭 {active.name} seems on the verge of saying more.")
        over, active = _progress(world, active)
        if over:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
