"""A character: one fixed brain architecture + a unique biography and state.

The thesis of Mindlock is that *same architecture + different experience -> different
behavior*. So the six-region cascade is shared; everything that makes a character who
they are lives here — chiefly the biography (hippocampus content) and their fear.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Character:
    name: str
    persona: str
    biography: str
    voice: str
    fear: str
    key_holder: bool
    key_location: str
    life_max: int = 1000          # "a thousand tokens to think with" — the track name, literally
    arousal: float = 4.0
    # --- world/story fields (optional; absent in the slice character) ---
    title: str = ""
    gender: str = ""              # "male"/"female" — so a generated character maps to a matching sprite
    portrait: str = ""            # path (relative to project root) to the portrait image
    sprite_key: str = ""          # roster slug → the client loads /static/sprites/npc/{slug}/ directly
    secrets: list = field(default_factory=list)  # staged disclosures (Design v2)
    key_condition: str = ""       # (legacy) superseded by key_approach
    key_approach: list = field(default_factory=list)  # words that ARE the earned approach to the key
    goal: str = "the key"         # what the holder withholds (procedural goals: 'the car keys', …)
    reveals: str = ""             # (legacy, unused) one-shot hint
    reveals_about: str = ""       # (legacy, unused)
    needs_reputation: int | None = None  # won't engage if world reputation is below this
    known_people: list = field(default_factory=list)  # names from their life (lie-catching: "I'm Mara")
    scripted: list = field(default_factory=list)  # fixed beats instead of a brain — a scene, not a mind
    scripted_idx: int = 0         # runtime: which beat plays next
    yield_line: str = ""          # canonical story beat spoken verbatim when the key is given
    # --- runtime state (not in the JSON) ---
    life_tokens: int | None = None
    rapport: float = 0.0          # accumulated relationship 0..10 (Design v2)
    history: list = field(default_factory=list)  # recent (player, reply) exchanges
    peers: list = field(default_factory=list)    # other characters in the room — for lie-catching
    relations: dict = field(default_factory=dict)  # name -> tie ("cousin"); so a holder recalls a peer
    trust: float = 0.0
    decision: str = "REFUSE"
    alive: bool = True
    gave_key: bool = False        # sticky: set once the key-holder yields (Design v2)
    revealed: bool = False
    approach_landed: bool = False  # the soft-spot word resonates fully only ONCE
    fear_pressure: int = 0         # consecutive hostile turns; sustained terror can break a holder

    def __post_init__(self) -> None:
        if self.life_tokens is None:
            self.life_tokens = self.life_max
        self._arousal0 = self.arousal  # remembered so reset()/reputation can restore it
        for s in self.secrets:
            s.setdefault("told", False)

    @classmethod
    def load(cls, path: str) -> "Character":
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(**data)

    def reset(self) -> None:
        self.life_tokens = self.life_max
        self.arousal = self._arousal0
        self.rapport = 0.0
        self.history = []
        for s in self.secrets:
            s["told"] = False
        self.trust = 0.0
        self.decision = "REFUSE"
        self.alive = True
        self.gave_key = False
        self.revealed = False
        self.approach_landed = False
        self.fear_pressure = 0
        self.scripted_idx = 0
