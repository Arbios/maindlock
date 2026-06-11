"""Procedural scenario generator (Design v2, Phase 2).

Authors a fresh, *solvable* social-puzzle scenario OFFLINE with a local LLM, on a fixed
solvable skeleton: a HOLDER who has what the player wants + a KNOWER who knows the holder's
soft spot. The LLM invents the theme and the people; the skeleton guarantees a valid path
(KNOWER reveals the HOLDER's `approach` word → use it on the HOLDER → goal). Output is the
same World the engine already runs.
"""
from __future__ import annotations

import json
import os
import re

from .backend import OllamaBackend
from .character import Character
from .world import Room, World

_SYS = "You are a sharp game designer. Output ONLY valid JSON — no prose, no markdown fences."

_PROMPT = """Invent a tense, grounded SOCIAL scenario: a stranger must get something from someone
who will not give it easily, and the ONLY way through is to win them over by understanding them.

Be fresh and specific — NOT a prison or asylum. Pick one: a strict parent, a nightclub bouncer,
a landlord, a used-car dealer, a border guard, an estranged sibling, a wary pawnbroker, a grieving
widow, a school principal, etc.

Return ONLY JSON of this exact shape:
{
 "setting": "1-2 sentences, second person, e.g. 'You need X from Y, who ...'",
 "goal": "short noun phrase the stranger wants (e.g. 'the car keys', 'permission to leave')",
 "holder": {"name":"","gender":"male or female (match the name)","title":"short role","voice":"how they speak","persona":"one vivid sentence",
            "biography":"2-3 sentences incl. a wound and a soft spot","fear":"what they fear",
            "goal_location":"where/how they keep the goal","approach":"ONE personal word that breaks their guard"},
 "knower": {"name":"","gender":"male or female (match the name)","title":"short role","voice":"how they speak","persona":"one vivid sentence",
            "biography":"2-3 sentences; they know the holder well","fear":"what they fear",
            "relation_to_holder":"the knower's tie to the holder in 1-2 words: e.g. 'cousin', 'old friend', 'former employee', 'neighbor', 'sister'",
            "hint_vague":"an early VAGUE hint about the holder's soft spot (does NOT name it)",
            "hint_reveal":"a later line that EXPLICITLY contains the holder's approach word"}
}
Rules: holder.approach is a single specific word (a loved one's name, a lost thing). knower.hint_reveal
MUST contain that exact word. Holder and knower have different names. Keep everyone human and grounded."""

_REQ_H = ("name", "gender", "title", "voice", "persona", "biography", "fear", "goal_location", "approach")
_REQ_K = ("name", "gender", "title", "voice", "persona", "biography", "fear", "hint_vague", "hint_reveal")


def _extract_json(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _valid(d) -> bool:
    return bool(isinstance(d, dict) and d.get("setting") and d.get("goal")
                and isinstance(d.get("holder"), dict) and all(d["holder"].get(k) for k in _REQ_H)
                and isinstance(d.get("knower"), dict) and all(d["knower"].get(k) for k in _REQ_K))


def _topics(*phrases) -> list:
    seen, out = set(), []
    for p in phrases:
        for w in re.findall(r"[A-Za-z]{3,}", p or ""):
            w = w.lower()
            if w not in seen:
                seen.add(w)
                out.append(w)
    return out


def _build_world(d) -> World:
    h, k = d["holder"], d["knower"]
    approach = h["approach"].strip()
    rel = (k.get("relation_to_holder") or "").strip()
    rel_phrase = f"your {rel}" if rel else "someone you have known for years"
    # The soft spot AND the relationship must live in each one's own memory, not only in the
    # knower's secrets — otherwise the holder denies the very thing the player learned ("I don't
    # ride bikes, it's not mine") or denies even knowing the knower ("Juan is not my cousin").
    # Bake both into the biography (the hippocampus input) so naming them lands instead of looping.
    holder_bio = h["biography"]
    if approach.lower() not in holder_bio.lower():
        holder_bio = (f"{holder_bio.rstrip('.')}. Deep down, '{approach}' is the one thing that "
                      "still reaches you — your tender, guarded wound.")
    holder_bio = f"{holder_bio.rstrip('.')}. {k['name']} is {rel_phrase}; you know them well."
    knower_bio = f"{k['biography'].rstrip('.')}. {h['name']} is {rel_phrase}; you know them and their wound well."
    holder = Character(
        name=h["name"], persona=h["persona"], biography=holder_bio, voice=h["voice"],
        fear=h["fear"], key_holder=True, key_location=h["goal_location"], title=h["title"],
        goal=d["goal"], key_approach=[approach.lower()], secrets=[],
        gender=str(h.get("gender", "")).lower(), relations={k["name"]: rel},
        known_people=[approach])
    reveal = k["hint_reveal"]
    if approach.lower() not in reveal.lower():           # repair: guarantee solvability
        reveal = f"{reveal.rstrip('.')}. The word is {approach}."
    htopics = _topics(h["name"], h["title"]) + ["he", "she", "him", "her", "his", "they", "them"]
    # Generated characters have no scripted TRUST hooks (unlike the hand-authored rooms), so the
    # only rapport engine is warmth + staying on-topic. Gates of 3/6 made the reveal practically
    # unreachable → soft-lock. 2/4 keeps it earned but attainable through patient, kind questioning.
    knower = Character(
        name=k["name"], persona=k["persona"], biography=knower_bio, voice=k["voice"],
        fear=k["fear"], key_holder=False, key_location="", title=k["title"], goal=d["goal"],
        gender=str(k.get("gender", "")).lower(), relations={h["name"]: rel},
        known_people=[approach],
        secrets=[
            {"id": "vague", "topics": htopics, "min_rapport": 2, "text": k["hint_vague"]},
            {"id": "reveal", "topics": htopics + _topics(approach), "min_rapport": 4,
             "teaches": [approach.lower()], "text": reveal},
        ])
    room = Room(name=(d["goal"][:50].strip() or "A closed door"), intro=d["setting"],
                characters=[holder, knower], key_holder=h["name"], terminal=None)
    return World(rooms=[room])


def generate_world(model: str = "llama3.1:latest", seed: int = 0, theme: str = "", attempts: int = 4) -> World:
    be = OllamaBackend(model=model, timeout=180)
    prompt = _PROMPT + (f"\n\nUse this theme: {theme}." if theme else "")
    for i in range(attempts):
        g = be.generate(_SYS, prompt, max_tokens=1100, temperature=0.95, seed=seed + i)
        d = _extract_json(g.text)
        if _valid(d):
            return _build_world(d)
    raise RuntimeError("scenario generation failed after retries (model output not valid JSON)")


def _char_to_dict(c: Character) -> dict:
    d = {"name": c.name, "persona": c.persona, "biography": c.biography, "voice": c.voice,
         "fear": c.fear, "key_holder": c.key_holder, "key_location": c.key_location,
         "title": c.title, "goal": c.goal, "key_approach": c.key_approach,
         "known_people": list(c.known_people),
         "secrets": [{k: v for k, v in s.items() if k != "told"} for s in c.secrets]}
    if c.relations:
        d["relations"] = c.relations
    if c.needs_reputation is not None:
        d["needs_reputation"] = c.needs_reputation
    return d


def save_world(world: World, out_dir: str) -> str:
    cdir = os.path.join(out_dir, "characters")
    os.makedirs(cdir, exist_ok=True)
    rooms = []
    for r in world.rooms:
        files = []
        for c in r.characters:
            fn = (re.sub(r"[^a-z0-9]+", "_", c.name.lower()).strip("_") or "char") + ".json"
            with open(os.path.join(cdir, fn), "w", encoding="utf-8") as fh:
                json.dump(_char_to_dict(c), fh, ensure_ascii=False, indent=2)
            files.append(fn)
        rooms.append({"name": r.name, "intro": r.intro, "key_holder": r.key_holder, "characters": files})
    path = os.path.join(out_dir, "world.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"rooms": rooms}, fh, ensure_ascii=False, indent=2)
    return path
