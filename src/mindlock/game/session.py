"""GameSession — server-side state for one player's endless run.

Holds the current room (a `World` from the engine), the brain backends, the roguelike spine
(reputation carries, key-holder death ends the run), and a background pre-generator so the
*next* room is ready by the time the player walks to the door — no load screen, endless world.

The engine is reused verbatim: `run_cascade` for talk, `generate_world` for new rooms,
`load_world` for the offline/no-model fallback.
"""
from __future__ import annotations

import os
import threading

from .. import story
from ..backend import FakeBackend, LlamaCppBackend, OllamaBackend, wants_no_think
from ..brain import run_cascade
from ..generator import generate_world
from ..render import MORAL_CARD, moral_card_killed
from ..world import World, load_world

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_WORLD = os.environ.get("MINDLOCK_WORLD") or os.path.join(_ROOT, "config", "world.json")

_REGION_COLOR = {
    "amygdala": "#ff5555", "hippocampus": "#bd93f9", "striatum": "#f1fa8c",
    "acc": "#8be9fd", "vmpfc": "#50fa7b", "relationship": "#ffb86c", "dlpfc": "#f8f8f2",
}


def _make_backends():
    """Same env contract as the Gradio app, so one process runs on a laptop or a Space.
    Defaults are the PRODUCTION stack (the A/B-chosen pair) — launching with no env vars must
    never silently demo the known-bad legacy voice."""
    if os.environ.get("MINDLOCK_FAKE"):
        return FakeBackend(), None
    model = os.environ.get("MINDLOCK_MODEL", "openbmb/minicpm-v4.6")
    dl = os.environ.get("MINDLOCK_DLPFC_MODEL", "nemotron-3-nano:4b")
    if os.environ.get("MINDLOCK_BACKEND") == "llamacpp":
        # Space / explicit llama.cpp runtime: one llama-server per role (no Ollama there)
        host = os.environ.get("MINDLOCK_LLAMA_HOST", "http://127.0.0.1:8080")
        dl_host = os.environ.get("MINDLOCK_LLAMA_DLPFC_HOST", "")
        be = LlamaCppBackend(model=model, host=host,
                             think=(False if wants_no_think(model) else None))
        dlbe = LlamaCppBackend(model=dl, host=dl_host,
                               think=(False if wants_no_think(dl) else None)) if dl_host else None
        return be, dlbe
    be = OllamaBackend(model=model, think=(False if wants_no_think(model) else None))
    dlbe = OllamaBackend(model=dl, think=(False if wants_no_think(dl) else None)) if dl else None
    return be, dlbe


class GameSession:
    def __init__(self) -> None:
        self.fake = bool(os.environ.get("MINDLOCK_FAKE"))
        self.gen_model = os.environ.get("MINDLOCK_GEN_MODEL", "llama3.1:latest")
        self.backend, self.dlpfc_backend = _make_backends()
        self.mode = "endless"                # "story" (finite authored campaign) | "endless" (procedural)
        self.story_levels: list = story.load_levels()   # the authored levels open BOTH modes
        self.depth = 0                       # rooms cleared so far (run progress / difficulty)
        self.run_over = False
        self.run_won = False                 # over by walking out (epilogue card) vs by a death
        self.moral = ""
        self._next: World | None = None      # background-generated neighbour, if ready
        self._gen_lock = threading.Lock()
        self._gen_thread: threading.Thread | None = None
        self.world = self._make_world(seed=0)
        self.world.enter_room()

    # ----------------------------------------------------------------- world construction
    def _story_len(self) -> int:
        """How many levels the story campaign has — the config/story/*.json files, or (as a
        fallback when none are authored yet) the curated rooms in config/world.json."""
        return len(self.story_levels) if self.story_levels else len(load_world(_WORLD).rooms)

    def _make_world(self, seed: int) -> World:
        """Depths 0..N-1 are the AUTHORED levels (config/story/*.json) in both modes — hand-written,
        editable, persisted. Past them, STORY ends (next_room closes the run) while ENDLESS goes
        procedural forever. Offline/no-model cycles the authored levels so the UI always plays."""
        if self.story_levels:
            if seed < len(self.story_levels):
                return story.build_world(self.story_levels[seed])
            if self.mode == "story" or self.fake or not self.gen_model:
                return story.build_world(self.story_levels[seed % len(self.story_levels)])
            return generate_world(model=self.gen_model, seed=seed)
        # no story files on disk — legacy fallback to the curated world.json
        authored = load_world(_WORLD)
        if self.mode == "story" or self.fake or not self.gen_model or seed < len(authored.rooms):
            authored.room_idx = max(0, min(seed, len(authored.rooms) - 1)) \
                if self.mode == "story" else seed % len(authored.rooms)
            return authored
        return generate_world(model=self.gen_model, seed=seed)

    def _kick_pregen(self) -> None:
        """Generate the next room in the background once this one is solved, so crossing the
        door is instant. Cheap no-op in fake mode (fallback world loads instantly anyway)."""
        if self.fake or self._next is not None:
            return
        if self._gen_thread and self._gen_thread.is_alive():
            return

        def _work(seed: int) -> None:
            try:
                nw = self._make_world(seed)
            except Exception:  # noqa: BLE001 — pre-gen is best-effort; door-cross retries inline
                nw = None
            with self._gen_lock:
                self._next = nw

        self._gen_thread = threading.Thread(target=_work, args=(self.depth + 1,), daemon=True)
        self._gen_thread.start()

    # ------------------------------------------------------------------------- public API
    def _char_dict(self, i: int, c) -> dict:
        ok, why = self.world.can_engage(c)
        holder = self.world.room.holder()
        pct = 100 * (c.life_tokens or 0) / max(1, c.life_max)
        return {
            "id": i, "name": c.name, "title": c.title, "gender": c.gender, "alive": c.alive,
            "sprite_key": c.sprite_key,        # roster slug → client loads its own sprite + portrait
            "is_holder": bool(holder and c.name == holder.name),
            "gave_key": bool(c.gave_key),      # the yield itself — the door may still want a terminal
            "engageable": ok, "why": why,
            "life": int(c.life_tokens or 0), "life_max": c.life_max, "life_pct": round(pct, 1),
            "rapport": round(c.rapport, 1), "arousal": round(c.arousal, 1), "decision": c.decision,
            "portrait": f"/api/portrait/{i}" if c.portrait and self._portrait_path(c) else None,
        }

    def _portrait_path(self, c) -> str | None:
        p = os.path.join(_ROOT, c.portrait or "")
        return p if c.portrait and os.path.exists(p) else None

    def portrait_file(self, char_id: int) -> str | None:
        chars = self.world.room.characters
        if 0 <= char_id < len(chars):
            return self._portrait_path(chars[char_id])
        return None

    def state(self) -> dict:
        r = self.world.room
        t = r.terminal
        authored_here = bool(self.story_levels and 0 <= self.depth < len(self.story_levels))
        room = {"name": r.name, "intro": r.intro, "depth": self.depth,
                "reputation": self.world.reputation, "solved": r.solved(),
                "editable": authored_here}     # only the authored levels may be edited/saved
        # authored levels may carry an explicit visual layout (placed in the in-browser editor);
        # pass it through verbatim so the client renders it instead of resolving the room by name.
        if authored_here:
            lay = self.story_levels[self.depth].get("layout")
            if lay:
                room["layout"] = lay
        term = {"prompt": t.prompt, "unlocked": t.unlocked} if t else None
        if term is None and authored_here:
            files = self.story_levels[self.depth].get("terminal_files")
            if files:   # flavor terminal: a read-only file browser, never a lock
                term = {"browser": True, "listing": files, "unlocked": True}
        return {
            "mode": self.mode,
            "room": room,
            "characters": [self._char_dict(i, c) for i, c in enumerate(r.characters)],
            "terminal": term,
            "door": {"locked": not r.solved()},
            "run": {"over": self.run_over, "won": self.run_won, "rooms_cleared": self.depth,
                    "moral": self.moral or None},
        }

    def talk(self, char_id: int, message: str) -> dict:
        if self.run_over:
            return {"error": "run is over", **self.state()}
        chars = self.world.room.characters
        if not (0 <= char_id < len(chars)):
            return {"error": "no such mind", **self.state()}
        c = chars[char_id]
        ok, why = self.world.can_engage(c)
        if not ok:
            return {"blocked": why, "events": [why], **self.state()}
        if c.scripted:
            return self._talk_scripted(c)

        res = run_cascade(self.backend, c, message, dlpfc_backend=self.dlpfc_backend,
                          learned=self.world.knows(c))
        if res.taught:
            self.world.learned.update(res.taught)
        events: list[str] = []
        delta = self.world.update_reputation(res)
        if delta:
            events.append(self._rep_note(delta) + f" (reputation {self.world.reputation:+d})")
        if res.submitted:
            events.append(f"{c.name} breaks. The key changes hands — and something in them goes out.")
        if res.died:
            events.append(f"{c.name}'s mind goes quiet.")
        if res.disclosure:
            events.append(f"{c.name} lets something slip: {res.disclosure}")
        elif res.caught_lie:
            events.append(f"{c.name} catches your lie about {res.caught_lie}.")
        elif res.near_secret:
            events.append(f"{c.name} seems on the verge of saying more — stay on it.")

        # Roguelike fail-state: only the KEY-HOLDER's death ends the run. A knower's death costs
        # reputation (above) and buries their guidance — the key stays winnable, the long way.
        holder = self.world.room.holder()
        if res.died and holder and c.name == holder.name:
            self._end_run(killed=c)
            events.append(f"The key is lost with {c.name}. There is no way forward.")
        elif res.died:
            events.append(f"Whatever {c.name} knew died with them. You are on your own now.")

        if self.world.room.solved():
            events.append("A lock gives. The way onward opens.")
            self._kick_pregen()

        traces = [{"key": tr.key, "label": tr.label, "headline": tr.headline,
                   "detail": tr.detail, "tokens": tr.tokens, "lever": tr.lever,
                   "color": _REGION_COLOR.get(tr.key, "#cccccc")} for tr in res.traces]
        verdict = (("KEY YIELDED — BROKEN" if res.submitted else "KEY GIVEN") if res.gave_key
                   else f"rapport {res.rapport_after:.0f}/10 · {res.stance}")
        out = {
            "speaker": c.name, "reply": res.reply, "traces": traces, "verdict": verdict,
            "gave_key": res.gave_key, "submitted": res.submitted, "value": res.value,
            "tone": res.tone, "burned": res.burned, "voice_tokens": res.voice_tokens,
            "recovered": res.recovered, "seconds": round(res.seconds, 1),
            "events": events,
        }
        out.update(self.state())
        return out

    def _talk_scripted(self, c) -> dict:
        """A scene, not a mind: fixed beats play in order, no cascade, no tokens burned.
        The last beat yields the key — the finale's dog needs presence, not persuasion."""
        i = min(c.scripted_idx, len(c.scripted) - 1)
        reply = str(c.scripted[i])
        c.scripted_idx = min(c.scripted_idx + 1, len(c.scripted))
        events: list[str] = []
        if c.scripted_idx >= len(c.scripted) and not c.gave_key:
            c.gave_key = True
            c.decision = "HELP"
            if self.world.room.solved():
                events.append("A lock gives. The way onward opens.")
                self._kick_pregen()
        out = {
            "speaker": c.name, "reply": reply, "traces": [], "verdict": "",
            "gave_key": c.gave_key, "submitted": False, "value": 0,
            "tone": "neutral", "burned": 0, "voice_tokens": 0,
            "recovered": 0, "seconds": 0.0, "events": events,
        }
        out.update(self.state())
        return out

    def terminal(self, code: str) -> dict:
        t = self.world.room.terminal
        events: list[str] = []
        if not t:
            events.append("There's no terminal here.")
        elif t.try_code(code):
            events.append("The terminal blinks green. ACCESS GRANTED.")
            if self.world.room.solved():
                events.append("A lock gives. The way onward opens.")
                self._kick_pregen()
        else:
            events.append(f"The terminal rejects it. {t.prompt}")
        return {"events": events, **self.state()}

    def next_room(self) -> dict:
        """Walk through the open door into the next room. Reputation carries; depth grows."""
        if self.run_over:
            return {"error": "run is over", **self.state()}
        if not self.world.room.solved():
            return {"blocked": "The door is still locked.", **self.state()}
        if self.mode == "story" and self.depth + 1 >= self._story_len():
            self.depth += 1                            # the final room counts as cleared
            self._end_run(won=True)                    # last authored door → the story is finished
            return {"events": ["The final door gives. You walk out into the light."], **self.state()}
        rep = self.world.reputation
        with self._gen_lock:
            nw, self._next = self._next, None
        if nw is None:
            nw = self._make_world(seed=self.depth + 1)
        nw.reputation = rep
        nw.learned = set(self.world.learned)   # what you were taught stays with you
        nw.enter_room()
        self.world = nw
        self.depth += 1
        return {"events": [f"You step through into a new room. Depth {self.depth}."],
                **self.state()}

    def reset(self) -> dict:
        self.depth = 0
        self.run_over = False
        self.run_won = False
        self.moral = ""
        self._next = None
        self.world = self._make_world(seed=0)
        self.world.enter_room()
        return self.state()

    def start(self, mode: str) -> dict:
        """Begin a fresh run in the chosen mode (called from the title menu). The authored levels
        front BOTH modes; endless simply keeps going procedurally after the last one."""
        self.mode = "story" if mode == "story" else "endless"
        self.story_levels = story.load_levels()
        return self.reset()

    # which character fields the in-browser editor may write into a level file
    _CHAR_FIELDS = {"name", "title", "gender", "persona", "voice", "biography", "fear",
                    "approach", "key_location", "goal", "secrets", "known_people",
                    "needs_reputation", "arousal", "life_max"}

    def editor_level(self) -> dict:
        """The current authored level's dialogue halves, for the character editor form."""
        if not (self.story_levels and 0 <= self.depth < len(self.story_levels)):
            return {"error": "This room is procedural — its minds aren't editable."}
        lv = self.story_levels[self.depth]
        return {"name": lv.get("name", ""), "intro": lv.get("intro", ""),
                "holder": lv.get("holder"), "knower": lv.get("knower")}

    def save_character(self, char_id: int, fields: dict) -> dict:
        """Editor 'Save mind': write the edited prompt fields of holder (0) / knower (1) back into
        the current level's JSON, then rebuild the room so the change is live at once."""
        import json
        if not (self.story_levels and 0 <= self.depth < len(self.story_levels)):
            return {"error": "Procedural minds can't be edited — only the authored levels."}
        role = "holder" if int(char_id) == 0 else "knower"
        path = self.story_levels[self.depth].get("_path")
        if not path or not os.path.exists(path):
            return {"error": "Level file not found on disk."}
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if role not in data:
            return {"error": f"This level has no {role}."}
        clean = {k: v for k, v in (fields or {}).items() if k in self._CHAR_FIELDS}
        for key in ("approach", "known_people"):       # the form sends comma-separated strings
            if isinstance(clean.get(key), str):
                clean[key] = [w.strip() for w in clean[key].split(",") if w.strip()]
        if "secrets" in clean and not isinstance(clean["secrets"], list):
            return {"error": "secrets must be a JSON list."}
        for key in ("arousal", "life_max", "needs_reputation"):
            if key in clean and clean[key] in ("", None):
                clean.pop(key)                          # empty form field = leave/remove optional
                data[role].pop(key, None)
        data[role].update(clean)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        self.story_levels = story.load_levels()
        rep, learned = self.world.reputation, set(self.world.learned)
        self.world = self._make_world(seed=self.depth)  # the edited mind is live immediately
        self.world.reputation = rep
        self.world.learned = learned
        self.world.enter_room()
        return {"saved": os.path.basename(path), **self.state()}

    def save_layout(self, layout: dict) -> dict:
        """Editor 'Save': write the arranged layout back into the current Story level's JSON file
        (preserving its dialogue), so the placement persists across runs."""
        import json
        if not (self.story_levels and 0 <= self.depth < len(self.story_levels)):
            return {"error": "This room is procedural — only the authored levels can be edited and saved."}
        path = self.story_levels[self.depth].get("_path")
        if not path or not os.path.exists(path):
            return {"error": "Level file not found on disk."}
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["layout"] = layout
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        self.story_levels = story.load_levels()      # reload so the saved layout is live at once
        return {"saved": os.path.basename(path)}

    def dev_generate(self) -> dict:
        """Dev: generate a brand-new procedural room (real LLM narrative) and drop into it."""
        import random
        model = self.gen_model or "llama3.1:latest"
        try:
            nw = generate_world(model=model, seed=random.randint(0, 1_000_000))
        except Exception as exc:  # noqa: BLE001
            return {"error": f"generation failed: {exc}", **self.state()}
        nw.reputation = self.world.reputation
        nw.enter_room()
        self.world = nw
        self.run_over = False
        self.run_won = False
        self.moral = ""
        self.depth += 1
        return self.state()

    def dev_roster(self) -> dict:
        """Dev: assemble a room from ready roster members (real minted faces + stories)."""
        import random
        from .. import roster
        try:
            nw = roster.build_world(seed=random.randint(0, 1_000_000))
        except Exception as exc:  # noqa: BLE001
            return {"error": f"roster room failed: {exc}", **self.state()}
        nw.reputation = self.world.reputation
        nw.enter_room()
        self.world = nw
        self.run_over = False
        self.run_won = False
        self.moral = ""
        self.depth += 1
        return self.state()

    def goto_room(self, idx: int) -> dict:
        """Dev: jump straight to an authored level (skips solving). Reputation and learned
        words ride along so a jump doesn't reset the run's social state."""
        self.run_over = False
        self.run_won = False
        self.moral = ""
        idx = max(0, min(idx, self._story_len() - 1))
        rep, learned = self.world.reputation, set(self.world.learned)
        self.world = self._make_world(seed=idx)
        self.world.reputation = rep
        self.world.learned = learned
        self.world.enter_room()
        self.depth = idx
        return self.state()

    # ----------------------------------------------------------------------------- helpers
    def _end_run(self, killed=None, won: bool = False) -> None:
        self.run_over = True
        self.run_won = won
        if won:                                        # story finished — walked out, no one lost
            finale = (self.story_levels[-1].get("finale_card", "") if self.story_levels else "")
            self.moral = (finale + ("\n\n" if finale else "")
                          + "You walked out. Every mind you changed is still breathing behind you.\n"
                          + MORAL_CARD).strip()
            return
        if killed is not None:                         # a mind was burned out — the killer's card
            self.moral = moral_card_killed(killed).strip()
            return
        depth_line = (f"You walked through {self.depth} "
                      f"{'mind' if self.depth == 1 else 'minds'} before this one.\n")
        self.moral = (depth_line + MORAL_CARD).strip()

    @staticmethod
    def _rep_note(delta: int) -> str:
        if delta > 0:
            return "Word spreads that you were kind."
        if delta <= -2:
            return "A mind went dark on your watch. Word travels ahead of you."
        return "Word spreads that you leaned on them."
