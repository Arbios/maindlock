"""Story mode — a finite campaign of hand-authored levels.

Each level is ONE self-contained JSON file in `config/story/` carrying both halves of a room:
  - the DIALOGUE: a `holder` (controls the goal) and an optional `knower` (reveals the holder's
    soft-spot word). Their fields ARE the dialogue — biography feeds the hippocampus, `secrets`
    are the staged disclosures, `approach` is the word that unlocks the holder.
  - the LAYOUT (optional): `theme` + placed `objects` + NPC `stations`, produced by the in-browser
    placement mode and pasted in. If omitted, the client renders the room by name (so a level named
    like an authored room reuses its curated look, and a new name falls back to a procedural theme).

The server only parses the dialogue half into `Character`s; the `layout` is passed through verbatim
to the client renderer (see GameSession.state).
"""
from __future__ import annotations

import json
import os

from .character import Character
from .world import Room, Terminal, World

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORY_DIR = os.path.join(_ROOT, "config", "story")


def load_levels(path: str = STORY_DIR) -> list[dict]:
    """Every *.json in the story dir, in filename order (so 01-…, 02-… sequence the campaign)."""
    if not os.path.isdir(path):
        return []
    levels = []
    for fn in sorted(os.listdir(path)):
        if fn.endswith(".json"):
            full = os.path.join(path, fn)
            with open(full, encoding="utf-8") as fh:
                data = json.load(fh)
            data["_path"] = full          # remembered so the editor's Save can write layout back
            levels.append(data)
    return levels


def _character(d: dict, *, holder: bool, peer: str = "", relation: str = "") -> Character:
    """Build one Character from a level's holder/knower block. Bakes the approach word and the
    relationship into the biography (the hippocampus input) so naming them LANDS instead of the
    holder denying its own wound — exactly as the procedural generator does."""
    bio = (d.get("biography") or "").rstrip(".")
    ap = d.get("approach") or []                       # one word ("Mara") or several ("elias","guilt")
    if isinstance(ap, str):
        ap = [ap]
    ap = [w.strip().lower() for w in ap if w and w.strip()]
    primary = ap[0] if ap else ""
    if holder and primary and primary not in bio.lower():
        bio = f"{bio}. Deep down, '{primary}' is the one thing that still reaches you — your wound"
    if peer:
        rel_phrase = f"your {relation}" if relation else "someone you have known a long time"
        bio = f"{bio.rstrip('.')}. {peer} is {rel_phrase}; you know them well"
    return Character(
        name=d["name"], persona=d.get("persona", ""), biography=bio + ".",
        voice=d.get("voice", ""), fear=d.get("fear", ""),
        key_holder=holder, key_location=d.get("key_location", ""),
        title=d.get("title", ""), goal=d.get("goal", "the key"),
        key_approach=ap if holder else [],
        secrets=[dict(s) for s in d.get("secrets", [])],
        gender=str(d.get("gender", "")).lower(), sprite_key=d.get("sprite_key", ""),
        portrait=d.get("portrait", ""),
        relations=({peer: relation} if (peer and relation) else {}),
        needs_reputation=d.get("needs_reputation"),
        known_people=list(d.get("known_people", [])),
        life_max=int(d.get("life_max", 1000)),
        scripted=list(d.get("scripted", [])),
        yield_line=d.get("yield_line", ""),
    )


def build_world(level: dict) -> World:
    """One level dict → a one-room World the engine runs (holder [+ knower] [+ terminal])."""
    h = level["holder"]
    k = level.get("knower")
    rel = (k.get("relation_to_holder") if k else "") or ""
    chars = [_character(h, holder=True, peer=(k["name"] if k else ""), relation=rel)]
    if k:
        chars.append(_character(k, holder=False, peer=h["name"], relation=rel))
    term = None
    t = level.get("terminal")
    if t and t.get("answer"):
        term = Terminal(prompt=t.get("prompt", "ENTER CODE — a name unlocks it."),
                        answer=t["answer"], hint_source=t.get("hint_source", ""))
    room = Room(name=level.get("name", "A locked door"), intro=level.get("intro", ""),
                characters=chars, key_holder=h["name"], terminal=term)
    return World(rooms=[room])
