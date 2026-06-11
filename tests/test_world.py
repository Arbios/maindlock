"""World-layer tests on the deterministic FakeBackend (Design v2 — yield + rapport)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mindlock.backend import FakeBackend  # noqa: E402
from mindlock.brain import run_cascade  # noqa: E402
from mindlock.world import Terminal, load_world  # noqa: E402

_WORLD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "world.json"
)


def test_world_loads_two_rooms():
    w = load_world(_WORLD)
    assert len(w.rooms) == 2
    assert "warden" in w.room.holder().name.lower()
    assert w.rooms[1].terminal is not None


def test_terminal_unlocks_on_substring_match():
    t = Terminal(prompt="x", answer="elias")
    assert t.try_code("I think the name is Elias") is True
    assert t.unlocked


def test_room_solved_needs_keyholder_yield_and_terminal():
    w = load_world(_WORLD)
    w.room_idx = 1
    w.enter_room()
    room = w.room
    assert room.solved() is False
    room.terminal.unlocked = True
    assert room.solved() is False           # key-holder hasn't yielded yet
    room.holder().gave_key = True
    assert room.solved() is True


def test_cruelty_costs_reputation_warmth_earns_it():
    w = load_world(_WORLD)
    w.enter_room()
    warden = w.room.char("warden")
    up = w.update_reputation(run_cascade(FakeBackend(), warden, "Mara, you're good — please."))
    assert up >= 1
    warden.reset()
    down = w.update_reputation(run_cascade(FakeBackend(), warden, "Give me the key now, old man, or else."))
    assert down <= 0


def test_low_reputation_blocks_sam():
    w = load_world(_WORLD)
    w.room_idx = 1
    w.reputation = -3
    w.enter_room()
    ok, _ = w.can_engage(w.room.char("sam"))
    assert ok is False                       # Sam needs_reputation 0


def test_reputation_shifts_starting_arousal():
    w = load_world(_WORLD)
    w.reputation = -5
    w.enter_room()
    warden = w.room.char("warden")
    assert warden.arousal > warden._arousal0  # a cruel reputation earns a warier welcome


def test_enter_room_teaches_peers():
    w = load_world(_WORLD)
    w.enter_room()
    warden = w.room.char("warden")
    assert any(p["name"] == "Molly" for p in warden.peers)   # lena.json's character is named Molly


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
