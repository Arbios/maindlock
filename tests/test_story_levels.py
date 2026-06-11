"""Integrity of the authored story campaign — the trolley arc must stay solvable and renderable.

These guard the content, not the engine: every level loads, every holder's approach word is
teachable (in its own room or earlier), every sprite/prop/portrait referenced actually exists,
and layouts stay inside the canvas with a reachable top door.
"""
import json
import os

import pytest

from mindlock import story

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "src", "mindlock", "game", "static")
LEVELS = story.load_levels()
DIRS8 = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]


def _teaches(level: dict) -> set:
    out = set()
    for role in ("holder", "knower"):
        for s in (level.get(role) or {}).get("secrets", []):
            out.update(str(w).lower() for w in s.get("teaches", []))
    return out


def test_ten_levels_load():
    assert len(LEVELS) == 10
    for lv in LEVELS:
        story.build_world(lv)  # must not raise


def test_every_approach_word_is_taught():
    taught = set()
    for lv in LEVELS:
        taught |= _teaches(lv)
        ap = (lv["holder"].get("approach") or [])
        ap = [ap] if isinstance(ap, str) else ap
        for w in ap:
            assert w.lower() in taught, f"{lv['name']}: approach '{w}' never taught"


def test_finale_is_scripted_and_carded():
    last = LEVELS[-1]
    assert last["holder"].get("scripted"), "finale holder must be scripted"
    assert last.get("finale_card"), "finale must carry the reveal card"


@pytest.mark.parametrize("lv", LEVELS, ids=[lv["name"] for lv in LEVELS])
def test_sprites_exist(lv):
    for role in ("holder", "knower"):
        d = lv.get(role)
        if not d:
            continue
        key = d.get("sprite_key")
        assert key, f"{lv['name']}/{role}: no sprite_key"
        base = os.path.join(STATIC, "sprites", "npc", key)
        for direction in DIRS8:
            assert os.path.exists(os.path.join(base, f"{direction}.png")), \
                f"{lv['name']}/{role}: sprite {key}/{direction}.png missing"
        if d.get("portrait"):
            assert os.path.exists(os.path.join(ROOT, d["portrait"])), \
                f"{lv['name']}/{role}: portrait {d['portrait']} missing"


@pytest.mark.parametrize("lv", LEVELS, ids=[lv["name"] for lv in LEVELS])
def test_layout_sane(lv):
    lay = lv.get("layout")
    assert lay, f"{lv['name']}: authored level should carry a layout"
    objects = lay.get("objects", [])
    assert objects, f"{lv['name']}: empty layout"
    for o in objects:
        png = os.path.join(STATIC, "room", "objects", f"{o['key']}.png")
        assert os.path.exists(png), f"{lv['name']}: prop '{o['key']}' has no PNG"
        assert 0 <= o["x"] <= 640 and 0 <= o["y"] <= 448, f"{lv['name']}: {o['key']} off-canvas"
        if o.get("solid"):
            assert o.get("fw") and o.get("fh"), f"{lv['name']}: solid {o['key']} missing footprint"
    n_chars = 1 + (1 if lv.get("knower") else 0)
    stations = lay.get("stations", [])
    assert len(stations) >= n_chars, f"{lv['name']}: {n_chars} characters but {len(stations)} stations"
    for s in stations:
        assert 64 <= s["x"] <= 608 and 100 <= s["y"] <= 380, f"{lv['name']}: station off-floor {s}"


def test_terminal_answers_are_hinted():
    for lv in LEVELS:
        t = lv.get("terminal")
        if not t:
            continue
        texts = " ".join(s["text"].lower()
                         for role in ("holder", "knower") if lv.get(role)
                         for s in lv[role].get("secrets", []))
        assert t["answer"].lower() in texts, \
            f"{lv['name']}: terminal answer '{t['answer']}' never hinted in any secret"
