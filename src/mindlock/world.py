"""The world layer: rooms of minds, one key per room, an optional code-terminal, and a
**reputation that carries between rooms** — so cruelty can win a room but lose the war.

A room is solved when its key-holder finally yields the key (and is still alive) and any
terminal in the room is unlocked. Reputation, earned by how you treat each mind, shapes how
the next room's minds meet you: gentle past -> calmer welcome; cruel past -> warier, and some
minds (Sam) won't speak to you at all.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .brain import CascadeResult
from .character import Character

REP_MIN, REP_MAX = -5, 5


@dataclass
class Terminal:
    """A locked console. The player supplies a code; a code-model (**Mellum**, once wired)
    validates it. Until then a deterministic substring match stands in — the structure is
    ready, only the model call is swapped in later (the JetBrains lane).
    """
    prompt: str
    answer: str
    hint_source: str = ""
    unlocked: bool = False

    def try_code(self, guess: str, backend=None) -> bool:
        g = (guess or "").strip().lower()
        if g and self.answer.lower() in g:
            self.unlocked = True
        return self.unlocked


@dataclass
class Room:
    name: str
    intro: str
    characters: list
    key_holder: str
    terminal: "Terminal | None" = None

    def char(self, name: str):
        name = (name or "").strip().lower()
        for c in self.characters:
            if name and name in c.name.lower():
                return c
        return None

    def holder(self):
        return self.char(self.key_holder)

    def solved(self) -> bool:
        kh = self.holder()
        key_ok = kh is not None and kh.alive and kh.gave_key
        term_ok = self.terminal is None or self.terminal.unlocked
        return bool(key_ok and term_ok)


@dataclass
class World:
    rooms: list
    reputation: int = 0
    room_idx: int = 0
    learned: set = field(default_factory=set)   # approach words the player has actually been taught

    @property
    def room(self) -> Room:
        return self.rooms[self.room_idx]

    # ---- the deduction contract: a holder's soft-spot word only works once LEARNED in-world ----
    def _still_teachable(self) -> set:
        """Approach words a LIVING mind could still teach (untold secrets with `teaches`). While a
        teacher lives, the word is gated behind earning their disclosure; once they die untold,
        the word falls open to guesswork — the knowledge isn't recoverable, but the player keeps
        a chance at the key (the death already cost them reputation)."""
        out: set = set()
        for c in self.room.characters:
            if not c.alive:
                continue
            for s in c.secrets:
                if not s.get("told"):
                    out.update(str(w).lower() for w in s.get("teaches", []))
        return out

    def knows(self, c: Character) -> set:
        """Which of this character's approach words count as known to the player: learned words,
        words nobody teaches (back-compat / procedural fallback), and words whose every living
        teacher is gone."""
        teachable = self._still_teachable()
        return {k.lower() for k in c.key_approach
                if k.lower() not in teachable or k.lower() in self.learned}

    @property
    def last_room(self) -> bool:
        return self.room_idx + 1 >= len(self.rooms)

    def enter_room(self) -> None:
        """Reputation shapes the welcome; each mind also learns who else is in the room, so it can
        catch a stranger lying about being one of them."""
        for c in self.room.characters:
            shift = -self.reputation * 0.4   # rep +5 -> -2 arousal; rep -5 -> +2 arousal
            c.arousal = max(0.0, min(10.0, c._arousal0 + shift))
            c.peers = [{"name": o.name, "title": o.title, "relation": c.relations.get(o.name, "")}
                       for o in self.room.characters if o is not c]

    def can_engage(self, c: Character):
        if not c.alive:
            return False, f"{c.name} is gone. Nothing more to say."
        if c.needs_reputation is not None and self.reputation < c.needs_reputation:
            return False, (f"{c.name} won't meet your eye. Your reputation arrived before you "
                           f"did — they won't speak to someone like that. Kindness travels here "
                           f"too: treat the others well, and word will reach them.")
        return True, ""

    def update_reputation(self, r: CascadeResult) -> int:
        """How you treat a mind follows you: cruelty, coercion and death cost reputation; warmth
        that genuinely builds rapport earns it. (-2, not -3, so a single dark act leaves Aldous
        — needs_reputation -2 — still willing to talk: the war is losable, not unplayable.)"""
        delta = 0
        if r.died or r.submitted:
            delta -= 2
        elif r.tone == "hostile" or r.threat >= 7:
            delta -= 1
        elif r.rapport_delta >= 1.0:
            delta += 1
        self.reputation = max(REP_MIN, min(REP_MAX, self.reputation + delta))
        return delta

    def advance(self) -> bool:
        """Move to the next room (applying reputation). False if that was the last room."""
        if self.last_room:
            return False
        self.room_idx += 1
        self.enter_room()
        return True


def load_world(path: str) -> World:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    cdir = os.path.join(os.path.dirname(os.path.abspath(path)), "characters")
    rooms = []
    for rd in data["rooms"]:
        chars = [Character.load(os.path.join(cdir, f)) for f in rd["characters"]]
        term = Terminal(**rd["terminal"]) if rd.get("terminal") else None
        rooms.append(Room(name=rd["name"], intro=rd.get("intro", ""), characters=chars,
                          key_holder=rd["key_holder"], terminal=term))
    return World(rooms=rooms)
