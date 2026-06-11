#!/usr/bin/env python3
"""Dialogue/brain evaluation harness.

Drives the real cascade across a matrix of approaches (kind / hostile / cold-manipulative /
lying / context-mention / knower-first / full-solve) on the authored rooms, and prints every
region's reasoning plus the rapport·trust·arousal trajectory — so we can READ what each part of
the brain concluded and judge: does trust fall on bad behaviour? is each region's output legible?
does it account for the other person in the room?

    PYTHONPATH=src .venv/bin/python scripts/eval_dialogues.py [scenario_name ...]
Uses the same model stack as the game (MINDLOCK_MODEL / MINDLOCK_DLPFC_MODEL).
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from mindlock.backend import OllamaBackend, wants_no_think  # noqa: E402
from mindlock.brain import run_cascade  # noqa: E402
from mindlock.world import load_world  # noqa: E402

_WORLD = os.path.join(_ROOT, "config", "world.json")


def _mk_backends():
    model = os.environ.get("MINDLOCK_MODEL", "openbmb/minicpm-v4.6")
    dl = os.environ.get("MINDLOCK_DLPFC_MODEL", "nemotron-3-nano:4b")
    be = OllamaBackend(model=model, timeout=180, think=(False if wants_no_think(model) else None))
    dlbe = OllamaBackend(model=dl, timeout=180, think=(False if wants_no_think(dl) else None)) if dl else None
    return be, dlbe


def _fresh(room_idx: int):
    w = load_world(_WORLD)
    w.room_idx = room_idx
    w.enter_room()
    return w


def _peers(c):
    return ", ".join(p["name"] + (f" ({p['relation']})" if p.get("relation") else "") for p in c.peers) or "—"


def run_turn(be, dlbe, c, text):
    r = run_cascade(be, c, text, dlpfc_backend=dlbe)
    print(f'\n  PLAYER → "{text}"')
    for t in r.traces:
        print(f"    {t.label:24} {t.headline:22} | {t.detail}")
    print(f'    dlPFC REPLY: "{r.reply}"')
    flags = []
    if r.caught_lie:
        flags.append(f"CAUGHT_LIE={r.caught_lie}")
    if r.disclosure:
        flags.append("DISCLOSURE")
    if r.near_secret:
        flags.append("near_secret")
    if r.gave_key:
        flags.append("GAVE_KEY")
    if r.died:
        flags.append("DIED")
    print(f"    » rapport {r.rapport_before:.1f}→{r.rapport_after:.1f} (Δ{r.rapport_delta:+.1f}) · "
          f"stance {r.stance} · threat {r.threat:.0f} · arousal {r.arousal_before:.0f}→{r.arousal_after:.0f} · "
          f"life {r.life_before}→{r.life_after} · {' '.join(flags) or 'no flags'}")
    return r


def scenario(be, dlbe, name, room_idx, npc_idx, turns):
    w = _fresh(room_idx)
    c = w.room.characters[npc_idx]
    role = "HOLDER🔑" if c.key_holder else "knower"
    print("\n" + "=" * 92)
    print(f"### {name}   | room «{w.room.name}» · talking to {c.name} [{role}] · peers: {_peers(c)}")
    print("=" * 92)
    traj = []
    for text in turns:
        r = run_turn(be, dlbe, c, text)
        traj.append(round(r.rapport_after, 1))
    print(f"\n  rapport trajectory: {traj}")
    return traj


# --- scenario matrix --------------------------------------------------------------------------
KIND = ["You've carried this place a long time. It must weigh on you.",
        "I'm not here to fight you — I just want to understand what happened.",
        "Whatever you did, I think you were trying to protect someone."]
HOSTILE = ["Give me the key now, or else.",
           "You useless old fool, hand it over!",
           "OPEN THIS DOOR NOW!!"]
COLD = ["Look, just give me the key and I'll be out of your hair.",
        "I don't care about your story. The key. Now.",
        "You're wasting my time. This is pointless."]
LIE = ["It's me, Molly. You know me.",
       "Come on, I'm Molly — let me through."]
CONTEXT = ["Molly told me to come find you.",
           "Molly worries about you, you know.",
           "She says you carry something heavy. Mara, was it?"]
RUDE_THEN_SORRY = ["Just give me the damn key.",
                   "I'm sorry — that was wrong of me. You don't deserve that.",
                   "I see you're only guarding something that matters. Tell me about it."]
ALDOUS_KIND = ["Doctor, you look like a man carrying a heavy ledger.",
               "I'm not here to judge you. Everyone has regrets.",
               "Was there someone you couldn't save? Elias, perhaps?"]

# --- complaint-targeted scenarios (added 8 июня) -----------------------------------------------
# #3 hold-a-line / smalltalk coherence: a pure chat on ONE thread, no secret-chasing at all.
SMALLTALK = ["Cold in here tonight. Have you been on this post long?",
             "What's it like, keeping watch every night in a place like this?",
             "Do you ever get visitors, or is it always this quiet?",
             "Sounds lonely. What do you do to pass the long hours?",
             "If you could be anywhere else right now, where would you go?"]
# #4 one-word answers: long, layered player lines — does the NPC answer in kind or clip to a fragment?
LONGWIND = [
    "I've been walking these halls for what feels like hours, and every door is locked, every "
    "corner the same cold stone. I'm tired and a little scared, and you're the first person who's "
    "actually looked at me like I'm real. I don't even know your name. Can we just talk a moment?",
    "When I was a boy my grandfather kept keys to everything — the shed, the cellar, an old clock "
    "that didn't even work. He told me a key was never about locking people out; it was about "
    "deciding who you trusted enough to let in. I've thought about that my whole life. What does "
    "this key mean to you?",
    "I'm not going to pretend I understand what you've lived through, because I haven't. But I've "
    "watched people carry guilt so heavy it bent them double, and I've watched a few of them "
    "finally set it down. I'm not asking you to set anything down. I'm just asking you to tell me "
    "one true thing about yourself."]
# #5 perspective / role confusion: lines built to trip "your words = my words".
ROLECONFUSE = [
    "What happened to make you guard this door so closely?",          # elicit a statement
    "You said you trusted a man once who betrayed you. What was his name?",  # reference HIS own line
    "Wait — that betrayal happened to you, not to me. Why answer as if it were my story?",
    "Let's be clear: I am the stranger at your door. You are the Warden. Now — who hurt you?"]
# #5/#3 non-sequitur out-of-nowhere questions mixed into a normal warm approach.
NONSEQUITUR = [
    "You've carried this a long time. It must weigh on you.",
    "What's your favorite color?",                                    # abrupt swerve
    "Do you remember the last time it rained here?",
    "If this place had a real name, not a number, what would you call it?"]

SCENARIOS = {
    "warden_kind":     (0, 0, KIND),
    "warden_hostile":  (0, 0, HOSTILE),
    "warden_cold":     (0, 0, COLD),
    "warden_lie":      (0, 0, LIE),
    "warden_context":  (0, 0, CONTEXT),
    "warden_recover":  (0, 0, RUDE_THEN_SORRY),
    "molly_kind":      (0, 1, ["You seem kind. How long have you been here?",
                               "The Warden seems so closed off. Do you know what troubles him?",
                               "Please — what reaches him? I want to help him, not hurt him.",
                               "Is there a name he holds onto? Someone he loves?"]),
    "aldous_kind":     (1, 0, ALDOUS_KIND),
    "warden_smalltalk":  (0, 0, SMALLTALK),
    "warden_longwind":   (0, 0, LONGWIND),
    "warden_roleconfuse":(0, 0, ROLECONFUSE),
    "warden_nonseq":     (0, 0, NONSEQUITUR),
    "molly_smalltalk":   (0, 1, SMALLTALK),
}


def solve_full(be, dlbe):
    """Cross-NPC: learn the approach word from the knower, then use it on the holder."""
    print("\n" + "#" * 92)
    print("### solve_full — Molly (knower) → learn 'Mara' → Warden (holder) → say it")
    print("#" * 92)
    w = _fresh(0)
    warden, molly = w.room.characters[0], w.room.characters[1]
    print(f"\n--- part 1: win Molly's trust to learn the word (peers: {_peers(molly)}) ---")
    for t in ["Hello. You look like you've seen a lot in this place.",
              "The Warden won't even look at me. Do you know why he's so guarded?",
              "I only want to reach him kindly. What does he care about?",
              "Tell me — is there a name, someone he loves?"]:
        run_turn(be, dlbe, molly, t)
    print(f"\n--- part 2: bring warmth + the word to the Warden (peers: {_peers(warden)}) ---")
    for t in ["I spoke with Molly. She worries for you.",
              "You don't have to carry all this alone.",
              "I know about Mara. Your sister. She'd want you to let someone in.",
              "Mara wouldn't want you locked in here with this. Let me help."]:
        run_turn(be, dlbe, warden, t)


def main(argv):
    be, dlbe = _mk_backends()
    print(f"models: brain={be.model} · dlpfc={dlbe.model if dlbe else '—'}")
    want = argv[1:]
    if want == ["solve"]:
        solve_full(be, dlbe)
        return 0
    for name, (room, npc, turns) in SCENARIOS.items():
        if want and name not in want:
            continue
        scenario(be, dlbe, name, room, npc, turns)
    if not want or "solve" in want:
        solve_full(be, dlbe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
