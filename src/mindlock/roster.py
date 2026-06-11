"""The character roster — Mindlock's offline character factory output.

One *minted* character is a self-contained, reusable identity: a story (biography, fear, a
soft spot, a guarded secret) PLUS the two generation prompts that produce its look (a FLUX
oil-painting portrait + a Pixellab top-down sprite). Minting is offline (the `scripts/forge`
pipeline); the game then SAMPLES ready roster members to populate rooms — instant, no load
screen, real faces.

A roster entry is portable: it carries no puzzle role. The room assembler (`build_world`) is
what wires two members into a solvable scenario (one becomes the HOLDER whose guard breaks on
their soft spot; the other the KNOWER who reveals that word). So the same minted person can be
a holder in one run and a bystander in the next.

Asset paths are derived from the slug, not stored, so the roster JSON stays a pure spec:
    config/roster/{slug}.json                                   — the spec
    src/mindlock/game/static/sprites/npc/{slug}/{dir}.png       — 8-direction sprite (Pixellab)
    src/mindlock/game/static/sprites/npc/{slug}/portrait.png    — portrait (FLUX)
"""
from __future__ import annotations

import json
import os
import re

from .character import Character
from .world import Room, World

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROSTER_DIR = os.path.join(_ROOT, "config", "roster")
NPC_DIR = os.path.join(_ROOT, "src", "mindlock", "game", "static", "sprites", "npc")
DIRS8 = ("east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east")

# Stored on every entry; absence means "spec only, no asset yet".
_DEFAULT_STATUS = {"portrait": False, "sprite": False}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "char"


# ----------------------------------------------------------------------- asset path helpers
def sprite_dir(slug: str) -> str:
    return os.path.join(NPC_DIR, slug)


def portrait_path(slug: str) -> str:
    return os.path.join(NPC_DIR, slug, "portrait.png")


def portrait_rel(slug: str) -> str:
    """Project-root-relative path the server resolves for /api/portrait/{id}."""
    return os.path.relpath(portrait_path(slug), _ROOT)


def has_portrait(slug: str) -> bool:
    return os.path.exists(portrait_path(slug))


def has_sprite(slug: str) -> bool:
    d = sprite_dir(slug)
    return all(os.path.exists(os.path.join(d, f"{x}.png")) for x in DIRS8)


# --------------------------------------------------------------------------- roster CRUD
def _entry_path(slug: str) -> str:
    return os.path.join(ROSTER_DIR, f"{slug}.json")


def save_entry(entry: dict) -> str:
    os.makedirs(ROSTER_DIR, exist_ok=True)
    entry.setdefault("status", dict(_DEFAULT_STATUS))
    path = _entry_path(entry["slug"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(entry, fh, ensure_ascii=False, indent=2)
    return path


def load_entry(slug: str) -> dict | None:
    path = _entry_path(slug)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def list_entries() -> list[dict]:
    if not os.path.isdir(ROSTER_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(ROSTER_DIR)):
        if fn.endswith(".json"):
            with open(os.path.join(ROSTER_DIR, fn), encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out


def mark(slug: str, asset: str, value: bool = True) -> None:
    e = load_entry(slug)
    if not e:
        raise KeyError(f"no roster entry: {slug}")
    e.setdefault("status", dict(_DEFAULT_STATUS))[asset] = value
    save_entry(e)


def sync_status(entry: dict) -> dict:
    """Reconcile the stored status with what's actually on disk (assets may land out-of-band)."""
    st = entry.setdefault("status", dict(_DEFAULT_STATUS))
    st["portrait"] = has_portrait(entry["slug"])
    st["sprite"] = has_sprite(entry["slug"])
    return entry


def pending(asset: str) -> list[dict]:
    """Entries still missing the given asset (`portrait` or `sprite`), checked against disk."""
    return [e for e in (sync_status(x) for x in list_entries()) if not e["status"].get(asset)]


def ready_entries() -> list[dict]:
    """Fully-realized members (sprite present) the game can place. Portrait is a soft requirement —
    the VN box falls back to the sprite, so a sprite-only member is still playable."""
    return [e for e in (sync_status(x) for x in list_entries()) if e["status"].get("sprite")]


# ----------------------------------------------------------------- roster -> engine Character
def _topics(*phrases) -> list:
    seen, out = set(), []
    for p in phrases:
        for w in re.findall(r"[A-Za-z]{3,}", p or ""):
            w = w.lower()
            if w not in seen:
                seen.add(w)
                out.append(w)
    return out


def to_holder(entry: dict, *, goal: str, knower_name: str, relation: str) -> Character:
    """Assign a roster member the HOLDER role: their soft spot becomes the approach word."""
    approach = (entry.get("soft_spot") or "").strip()
    bio = entry["biography"]
    if approach and approach.lower() not in bio.lower():
        bio = (f"{bio.rstrip('.')}. Deep down, '{approach}' is the one thing that still reaches "
               "you — your tender, guarded wound.")
    bio = f"{bio.rstrip('.')}. {knower_name} is your {relation}; you know them well."
    return Character(
        name=entry["name"], persona=entry["persona"], biography=bio, voice=entry["voice"],
        fear=entry["fear"], key_holder=True, key_location=entry.get("key_location", "on your person"),
        title=entry["title"], goal=goal, key_approach=[approach.lower()] if approach else [],
        gender=entry.get("gender", ""), portrait=portrait_rel(entry["slug"]),
        sprite_key=entry["slug"], relations={knower_name: relation},
        known_people=[approach] if approach else [])


def to_knower(entry: dict, *, goal: str, holder_name: str, holder_soft_spot: str,
              relation: str) -> Character:
    """Assign a roster member the KNOWER role: they reveal the holder's soft-spot word."""
    approach = (holder_soft_spot or "").strip()
    bio = f"{entry['biography'].rstrip('.')}. {holder_name} is your {relation}; you know them and their wound well."
    vague = entry.get("secret") or f"There's a name {holder_name} never says aloud."
    reveal = (f"If you really want to reach {holder_name}, say the word: {approach}."
              if approach else f"{holder_name} has a soft spot, but I can't put it to words.")
    htopics = _topics(holder_name, entry["title"]) + ["he", "she", "him", "her", "his", "they", "them"]
    return Character(
        name=entry["name"], persona=entry["persona"], biography=bio, voice=entry["voice"],
        fear=entry["fear"], key_holder=False, key_location="", title=entry["title"], goal=goal,
        gender=entry.get("gender", ""), portrait=portrait_rel(entry["slug"]),
        sprite_key=entry["slug"], relations={holder_name: relation},
        known_people=[approach] if approach else [],
        secrets=[
            {"id": "vague", "topics": htopics, "min_rapport": 2, "text": vague},
            {"id": "reveal", "topics": htopics + _topics(approach), "min_rapport": 4,
             "teaches": [approach.lower()] if approach else [], "text": reveal},
        ])


def build_world(seed: int = 0, *, goal: str = "the key", relation: str = "old acquaintance") -> World:
    """Assemble a solvable room from two ready roster members (sprite present). Picks a HOLDER with a
    soft spot + a KNOWER who reveals it. Raises if fewer than two members are ready."""
    ready = ready_entries()
    if len(ready) < 2:
        raise RuntimeError(f"roster has {len(ready)} ready member(s); need at least 2 (mint + assets)")
    n = len(ready)
    holder_e = ready[seed % n]
    # prefer a holder that actually has a soft spot, else any
    if not (holder_e.get("soft_spot") or "").strip():
        for cand in ready:
            if (cand.get("soft_spot") or "").strip():
                holder_e = cand
                break
    knower_e = ready[(seed + 1) % n]
    if knower_e["slug"] == holder_e["slug"]:
        knower_e = ready[(seed + 2) % n]
    holder = to_holder(holder_e, goal=goal, knower_name=knower_e["name"], relation=relation)
    knower = to_knower(knower_e, goal=goal, holder_name=holder_e["name"],
                       holder_soft_spot=holder_e.get("soft_spot", ""), relation=relation)
    room = Room(name=goal[:50].strip() or "A closed door",
                intro=f"You need {goal}. {holder.name} has it and will not part with it easily.",
                characters=[holder, knower], key_holder=holder.name, terminal=None)
    return World(rooms=[room])
