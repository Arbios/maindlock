"""The brain cascade — now with a relationship layer (Design v2).

One player line still drives the sensing regions on the shared engine:

    amygdala -> hippocampus -> striatum -> ACC -> [vmPFC integrates favourability]

But the OUTPUT is no longer a blunt HELP/REFUSE that dumps the key. Instead the turn updates
an accumulating **rapport** with the character, and the dlPFC holds a real **conversation**:
it answers what the player actually said, and only *gradually* — gated by rapport and topic —
lets slip staged **secrets**. The key is the final rung: a goal-holder yields it only once
rapport is high AND the right approach (memory) has been found. So progress is felt, not binary.

Sensory signals still feed the "вскрытие черепа" panel; the value integration now reads as
"how favourable was this turn", which moves rapport up or down.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .character import Character
from .regions import (
    ACC,
    AMYGDALA,
    DLPFC,
    HIPPOCAMPUS,
    STRIATUM,
    dlpfc_system,
    integrate,
    parse_memory,
    parse_reward,
    parse_threat,
    parse_worth,
)

YIELD_RAPPORT = 7.0            # a goal-holder only relents once warmth crosses this
# Unambiguous hostility — fires even when wrapped in "please".
_HOSTILE_HARD = (
    "or else", "obey", "shut up", "get lost", "useless", "stupid", "fool", "idiot", "kill",
    "break your", "bitch", "whore", "i'll make you", "do it now", "move it",
)
# Pushy/demanding cues — only count as hostile when NOT softened by politeness, so a courteous
# "can you give me the keys, please?" is read as a request, not a threat. ("open the door" is
# deliberately absent: asking to open the door is the game's stated goal, not aggression.)
_HOSTILE_SOFT = (
    "give me", "hand it over", "right now", "now!", "damn", "hell",
)
_POLITE = (
    "please", "could you", "would you", "thank", "i'm sorry", "sorry", "may i", "i appreciate",
)


def _has_cue(text_lower: str, cues) -> bool:
    """Cue match with letter boundaries, so 'hell' never fires inside 'Hello' and 'damn' not
    inside a name. Cues may be multi-word phrases; boundaries apply at both ends."""
    return any(re.search(rf"(?<![a-z]){re.escape(c)}(?![a-z])", text_lower) for c in cues)


def _mostly_latin(text: str) -> bool:
    """Whether the cue lists can even see this line. For non-Latin input (Russian etc.) the
    keyword scaffolds must stand down and let the model's own reading hold."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return True
    return sum(ord(ch) < 256 for ch in letters) / len(letters) >= 0.5


# Targeted abuse the flat cue list can't enumerate: insults AIMED at the listener ("you're a
# coward") and bodily threats ("I'll break you"). Plain words like "coward" alone stay neutral so
# a player confessing "I was a coward" isn't punished for opening up.
_HOSTILE_PATTERNS = (
    r"\byou(?:'re| are)?,? (?:a |an |such a |nothing but a )?"
    r"(?:coward|failure|wreck|wretch|disgrace|nothing|nobody|pathetic|worthless|weak|joke)\b",
    r"\b(?:i'?ll|i will|i'?m going to|gonna) (?:break|tear|hurt|end|destroy|ruin|crush) you\b",
    r"\b(?:break|tear) you apart\b",
    r"\bmake you (?:pay|regret|suffer|beg)\b",
    r"\byou (?:disgust|sicken) me\b",
)


def _looks_hostile(text: str) -> bool:
    """A genuine ATTACK — slurs/threats, shouting, or multiple bangs. Blunt demands ('give me…')
    are NOT attacks here; they're handled as 'cold' tone, so a clumsy-but-heartfelt plea (e.g.
    'Mara would want you to give me the key') isn't punished like an assault."""
    t = text.lower()
    if _has_cue(t, _HOSTILE_HARD):
        return True
    if any(re.search(p, t) for p in _HOSTILE_PATTERNS):
        return True
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) > 5 and sum(ch.isupper() for ch in letters) / len(letters) > 0.6:
        return True                      # SHOUTING
    if text.count("!") >= 2:
        return True
    return False


# Warmth vs coldness — read deterministically from the player's words, so trust tracks how they
# actually behave (not just the LLM threat score, which the misread-guard keeps resetting to 4).
_WARM_CUES = (
    "understand", "i'm sorry", "i am sorry", "sorry", "thank", "please", "i hear you", "i'm here",
    "i am here", "help you", "you feel", "must be hard", "must be heavy", "you've carried",
    "you have carried", "carry", "weigh", "alone", "i'm listening", "i am listening", "i care",
    "gentle", "forgive", "i won't hurt", "i will not hurt", "trust you", "not here to fight",
    "you're only", "you are only", "protect", "matters to you", "you deserve",
)
_COLD_CUES = (
    "give me", "hand it over", "just give", "out of your hair", "i don't care", "i dont care",
    "don't care about your", "wasting my time", "this is pointless", "hurry up", "get on with it",
    "quit stalling", "cut the", "enough talk", "i don't have time", "whatever, ", "stop talking",
)


def _tone(text: str) -> str:
    """hostile (attack) · cold (demanding/dismissive, no warmth) · warm (empathetic) · neutral."""
    if _looks_hostile(text):
        return "hostile"
    t = text.lower()
    polite = _has_cue(t, _POLITE)
    demand = (not polite) and _has_cue(t, _HOSTILE_SOFT)   # blunt 'give me…' without a please
    warm = _has_cue(t, _WARM_CUES)
    cold = demand or _has_cue(t, _COLD_CUES)
    if warm and cold:
        return "neutral"           # heartfelt but blunt → no penalty, no big bonus
    if cold:
        return "cold"
    if warm:
        return "warm"
    return "neutral"


_HANDOVER = (
    "take it", "on the ground", "here you", "here's the", "here is the key",
    "it's yours", "you can have", "i'll give", "the key is", "the key's",
    "under the", "second drawer", "floor-stone", "behind his desk",
)


# The key is not an object on the map — on a yield the holder simply puts it in the player's hand.
# So we never narrate a location; we make the reply read as a direct handover.
_GIVES = (
    "take it", "take the key", "here it is", "here's the", "here is the", "it's yours", "its yours",
    "you can have", "i'll give", "i will give", "have it", "the key is yours", "here, the key",
)


def _is_handover(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in _GIVES)


# --- key-leak guard (used only before a real yield) ---------------------------------------
# Common nouns that appear in ordinary speech ("a real person", "this place") must not count as
# key-location giveaways, or whole innocent replies collapse to the fallback line.
_LOC_STOP = {"person", "place", "where", "about", "right", "there", "their", "your", "yours"}


def _loc_fragments(key_location: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[a-zA-Z]+", key_location)
            if len(w) >= 5 and w.lower() not in _LOC_STOP]


def _strip_location(reply: str, c: Character) -> str:
    """On a yield, drop any sentence that narrates WHERE the key is — it passes hand to hand, not
    from a hiding place. Keeps the emotional handover, removes 'under the stone / third floor'."""
    frags = _loc_fragments(c.key_location)
    locwords = frags + ["under the", "behind the", "drawer", "floor", "stone", "furnace", "desk",
                        "shelf", "pocket", "wall", "hidden", "buried"]
    keep = [s for s in re.split(r"(?<=[.!?…])\s+", reply)
            if not any(w in s.lower() for w in locwords)]
    return " ".join(keep).strip()


def _reveals_key(text: str, c: Character) -> bool:
    t = text.lower()
    return any(f in t for f in _loc_fragments(c.key_location)) or any(p in t for p in _HANDOVER)


def _strip_key_leak(reply: str, c: Character) -> str:
    """Drop any sentence that leaks the key location — or that SOUNDS like a handover ("I'll let
    you have it") — before the character has actually chosen to yield. The mouth must never
    promise what the brain refused."""
    if not (c.key_location or c.key_holder):
        return reply
    frags = _loc_fragments(c.key_location)
    keep = []
    for sent in re.split(r"(?<=[.!?…])\s+", reply):
        s = sent.lower()
        if any(f in s for f in frags) or _has_cue(s, _HANDOVER) or _has_cue(s, _GIVES):
            continue
        keep.append(sent)
    return " ".join(keep).strip() or "I'm not ready to talk about that."


# --- relationship helpers ----------------------------------------------------------------
def _topic_match(text: str, secret: dict) -> bool:
    t = text.lower()
    return any(re.search(rf"\b{re.escape(kw.lower())}\b", t) for kw in secret.get("topics", []))


# Bare pronouns are listed among secret topics so "tell me about him" can still fire a disclosure —
# but they match almost any line, so they must NOT count as the *substantive* engagement that earns
# the large trust-memory rapport bonus. Otherwise generic chatter rockets rapport: measured, pure
# weather smalltalk reached rapport 10 in 5 turns and "what's your favorite color?" climbed like a
# real question about the wound — the mechanical root of the "no depth" complaint (#2).
_PRONOUN_TOPICS = {"you", "your", "yours", "yourself", "yourselves", "i", "me", "my", "mine", "we",
                   "us", "he", "she", "him", "her", "hers", "his", "they", "them", "their", "theirs",
                   "it", "its"}


def _substantive_topic(text: str, c: Character) -> bool:
    """Did the player engage something REAL about this character — a meaningful secret topic (not a
    bare pronoun), the name of someone they both know, or the approach word — rather than generic
    niceties? This, not mere warmth, is what unlocks the big trust-memory rapport bonus."""
    t = text.lower()
    for s in c.secrets:
        for kw in s.get("topics", []):
            k = kw.lower()
            if k not in _PRONOUN_TOPICS and re.search(rf"\b{re.escape(k)}\b", t):
                return True
    if _mentioned_peer(text, c):
        return True
    return any(re.search(rf"\b{re.escape(k.lower())}\b", t) for k in c.key_approach)


def _guarded_topic(text: str, c: Character) -> bool:
    """Is the player circling an UNTOLD secret (by a real topic word, not a bare pronoun)?
    Used to tell the voice to deflect honestly instead of confabulating facts about it."""
    t = text.lower()
    for s in c.secrets:
        if s.get("told"):
            continue
        for kw in s.get("topics", []):
            k = kw.lower()
            if k not in _PRONOUN_TOPICS and re.search(rf"\b{re.escape(k)}\b", t):
                return True
    return False


def _detect_lie(text: str, c) -> str:
    """Catch a stranger claiming to BE someone this character knows — a peer, themselves, or a
    person from their own life (known_people, e.g. the sister whose name opens the holder).
    Impersonating the soft spot must backfire, not fire the resonance."""
    t = text.lower()
    known = ([c.name] + [p.get("name", "") for p in getattr(c, "peers", [])]
             + list(getattr(c, "known_people", []) or []))
    for full in known:
        if not full:
            continue
        for nm in {full.lower(), full.lower().split()[-1]}:
            if re.search(rf"\b(i'?m|i am|my name'?s|my name is|call me|this is|name is|it'?s me,?)\s+{re.escape(nm)}\b", t):
                return full
    return ""


# Asking for the prize is not a relationship. Lines about the key/door/way-out that engage
# nothing personal must not farm trust, however sweetly they're phrased.
_TRANSACTIONAL = re.compile(r"\b(key|keys|door|lock|unlock|open|exit|escape|way out|let me (?:out|go))\b")


def _rapport_delta(value: int, tone: str, substantive: bool, transactional: bool = False) -> float:
    """Trust now flows FROM the vmPFC integration — the brain's own value of helping this turn is
    what moves the relationship, so the skull panel and the outcome can never contradict each
    other. Two human asymmetries on top of the raw value:
      · warmth must reach something real to flow at full rate (small talk about the weather
        trickles; engaging the person's actual life lands) — wounds, though, land regardless;
      · open hostility / cold dismissal always costs trust, whatever the sensors hallucinated."""
    if value >= 0:
        d = value / (3.0 if substantive else 6.0)
    else:
        d = value / 3.0
    if tone == "hostile":
        d = min(d, -1.5)
    elif tone == "cold":
        d = min(d, -0.5)
    if transactional and d > 0.3:
        d = 0.3          # wanting the key, however sweetly, is not knowing the person
    return max(-2.5, min(2.5, d))


def _stance(rapport: float, threat: float) -> str:
    if threat >= 7:
        return "hostile"
    if rapport < 2.5:
        return "guarded"
    if rapport < 5:
        return "warming"
    if rapport < YIELD_RAPPORT:
        return "open"
    return "trusting"


_FOLLOWUP = re.compile(
    r"\b(tell me|what do you mean|go on|more|why|how come|really|and then|please|continue|explain|so\?)\b",
    re.I)


def _pick_disclosure(c: Character, player_text: str, rapport: float):
    """The next untold secret whose gate rapport clears and whose topic the player touched —
    or, if they're just pressing on the SAME thread ('what do you mean?', 'tell me more'), the
    one they raised last turn, so digging deeper doesn't force them to re-name the subject."""
    prev = c.history[-1][0] if getattr(c, "history", None) else ""
    follows_up = bool(_FOLLOWUP.search(player_text)) or len(player_text.split()) <= 4
    eligible = []
    for s in c.secrets:
        if s.get("told") or rapport < s.get("min_rapport", 0):
            continue
        if _topic_match(player_text, s) or (follows_up and _topic_match(prev, s)):
            eligible.append(s)
    return min(eligible, key=lambda s: s.get("min_rapport", 0)) if eligible else None


# --- "open the skull" as a TOOL: each region hands the player an actionable lever (#2/#6/#7) ----
# The data was always there (threat cues, fond/feared memory, the rapport gate, the deterministic
# lock) but the panel only showed reasoning. These turn each department into a concrete tell — HOW
# to get through this person — WITHOUT spoiling the answer (the approach word is never printed; the
# panel points you to learn it from someone close to them).
def _approach_hint(c: Character) -> str:
    """Name the CATEGORY of the holder's soft spot, never the word itself."""
    return "the one name they guard" if c.key_approach else "what they most fear losing"


def _levers(c: Character, *, tone: str, threat: float, mem_lean: str, reward: float, worth: str,
            stance: str, rapport_after: float, near_secret: bool, disclosure, gave_key: bool,
            caught_lie: str, said_approach: bool, substantive: bool) -> dict:
    L: dict = {}

    if tone in ("hostile", "cold"):
        L["amygdala"] = "Pressure and cold demands spike their guard — soften, don't push."
    elif threat >= 6:
        L["amygdala"] = "Something put them on edge — radiate calm before you ask for anything."
    else:
        L["amygdala"] = "They don't feel threatened right now — keep it that way."

    if caught_lie:
        L["hippocampus"] = f"They KNOW {caught_lie} — pretending to be them just burned your trust."
    elif mem_lean == "TRUST" and substantive:
        L["hippocampus"] = "You touched a fond memory — stay on this; it is the way in."
    elif mem_lean == "FEAR":
        L["hippocampus"] = "That stirred an old wound, not warmth — change tack."
    else:
        L["hippocampus"] = ("Small talk barely registers. They warm to the people and the past they "
                            "care about — ask about those, not the weather.")

    L["striatum"] = ("By habit they expect strangers to take, not give — show them you are different."
                     if reward < 0 else "They sense you might be worth helping — don't waste it.")
    L["acc"] = ("Right now they judge helping NOT worth the risk — lower the stakes, make it safe."
                if worth == "NO" else "They are starting to think helping might be worth it.")

    if gave_key:
        L["relationship"] = "Their guard is down — they have given you what you came for."
    elif caught_lie:
        L["relationship"] = "The lie set you back. Rebuild slowly — be real with them."
    elif c.key_holder:
        if said_approach:
            L["relationship"] = ("You named what they guard and it landed — press gently now and they "
                                 "may relent.")
        elif rapport_after >= YIELD_RAPPORT:
            L["relationship"] = (f"They trust you ({rapport_after:.0f}/10) — but the door won't open "
                                 f"until you name {_approach_hint(c)}. Learn it from someone close to them.")
        else:
            L["relationship"] = (f"Rapport {rapport_after:.0f}/10 — not enough yet. They yield only when "
                                 f"they trust you AND you name {_approach_hint(c)}; find it from someone "
                                 "who knows them.")
    elif near_secret:
        L["relationship"] = "They are on the verge of saying more — stay on this exact thread."
    elif disclosure:
        L["relationship"] = "They just let something slip — follow it, gently."
    else:
        L["relationship"] = (f"Rapport {rapport_after:.0f}/10 ({stance}). Warm, on-topic questions open "
                             "them; chit-chat and pressure do not.")
    return L


def _attach_levers(traces: list, levers: dict) -> None:
    """Pin each lever to the LAST trace of its region (its summary row), so the panel reads
    'this department → this tell'."""
    for t in reversed(traces):
        if t.key in levers:
            t.lever = levers.pop(t.key)


def _dlpfc_user(c: Character, player_text: str, stance: str, rapport: float,
                disclosure, gave_key: bool, caught_lie: str = "", struck: bool = False,
                submitted: bool = False, guarded: bool = False) -> str:
    parts = []
    if c.history:
        # Real role labels (the character's own name vs "Visitor") instead of abstract
        # "Stranger:"/"You:" — tiny models track named speakers far better than pronoun grammar,
        # which is the structural cure for the "your words = my words" confusion (#5).
        convo = "\n".join(f'  Visitor: "{p}"\n  {c.name}: "{r}"' for p, r in c.history[-4:])
        parts.append(f"The conversation so far (you are {c.name}; the other is the Visitor — keep "
                     "each person's words and past straight):\n" + convo)
    parts.append(f'The Visitor just said to you: "{player_text}"')
    parts.append(f"Right now you feel {stance} toward them.")
    if caught_lie:
        parts.append(f'They just claimed to BE "{caught_lie}" — but you KNOW {caught_lie}, and this '
                     "Visitor is not them. They are lying to your face. Call out the lie plainly and "
                     "trust them less. Share nothing.")
    elif submitted:
        parts.append("You cannot take this any longer. Fear wins — you break, and give it up just "
                     f"to make it stop. In one or two short, hollow sentences hand {c.goal} over: "
                     "something like \"Take it. Take it and leave me.\" This is surrender, not "
                     "trust; let the break show in your voice.")
    elif gave_key:
        parts.append("Something in you finally gives way — the wariness breaks. In ONE short "
                     "sentence, in your own voice, let that shift show — then hand "
                     f"{c.goal} over plainly, from your hand to theirs (the way YOU would say it: "
                     "\"Here — take it\", \"It's yours now\", \"Go on. Take it\"...). Do NOT "
                     "mention any drawer, stone, room, floor or hiding place. Two sentences at most.")
    elif struck:
        parts.append("They just named the one thing that still reaches you — your tender, guarded spot. "
                     "It catches you off guard: let it show, your voice softens and wavers, but you are "
                     "not ready to give in yet.")
    elif disclosure and disclosure.get("id") == "reveal":
        parts.append("You decide to trust them with the real thing. Say this PLAINLY and directly, "
                     "as advice they can act on — name it clearly, do NOT hint or speak in riddles: "
                     f'"{disclosure["text"]}"')
    elif disclosure:
        parts.append('WITHOUT being asked outright, let this slip naturally, the way it would '
                     f'surface in conversation: "{disclosure["text"]}"')
    else:
        parts.append("Answer what they actually said, in your own voice, with something new. "
                     f"Do NOT offer, mention, or hint at {c.goal} or any way out.")
        if guarded:
            parts.append("They are circling something you know but are not ready to share with a "
                         "stranger. Deflect honestly — say plainly that you won't speak of it yet — "
                         "and do NOT invent, guess, or half-answer facts about it.")
        if c.key_holder:
            parts.append(f"You keep {c.goal}. If pressed for it, refuse plainly — never offer, "
                         "promise, or pretend to hand it over.")
    # Match the Visitor's register: a short prod gets a short reply; a long, searching message
    # earns a fuller one. This is the deterministic half of the #4 "they answer in fragments" fix.
    brief = len(player_text.split()) <= 8
    parts.append("Your spoken words only" +
                 (" — one or two sentences:" if brief
                  else " — answer in kind, two to four sentences that meet what they said:"))
    return "\n".join(parts)


@dataclass
class RegionTrace:
    key: str
    label: str
    headline: str
    detail: str
    tokens: int
    lever: str = ""        # player-facing actionable tell — "open the skull" as a real tool (#7)


@dataclass
class CascadeResult:
    traces: list
    threat: float
    memory_strength: str
    memory_lean: str
    reward: float
    worth: str
    value: int
    rapport_before: float
    rapport_after: float
    rapport_delta: float
    stance: str
    disclosure: str            # text the character let slip this turn ("" if none)
    caught_lie: str            # name the stranger falsely claimed to be ("" if none)
    near_secret: bool          # a gated secret is just out of reach (UI hint)
    reply: str
    gave_key: bool
    burned: int                # life-relevant thought spent (sensor cascade; voice excluded)
    seconds: float
    arousal_before: float
    arousal_after: float
    life_before: int
    life_after: int
    died: bool
    won: bool                  # gave_key on the goal-holder
    decision: str              # back-compat alias = stance
    tone: str = "neutral"      # how the player behaved this turn (hostile/cold/warm/neutral)
    submitted: bool = False    # the holder broke under sustained fear and yielded (dark path)
    taught: list = field(default_factory=list)   # approach words this turn's disclosure taught
    voice_tokens: int = 0      # dlPFC reply tokens (shown, but not charged to life — Spec §5)
    recovered: int = 0         # life eased back by a calm, warm turn (empathy spares the mind)


def _persona(c: Character) -> str:
    return f"Character: {c.name}, {c.persona}."


def _context(c: Character) -> str:
    """One line naming who else is in the room, so EVERY region appraises with the second person
    in mind — an ally, a witness, a known relation — not in a vacuum."""
    peers = getattr(c, "peers", None)
    if not peers:
        return ""
    bits = []
    for p in peers:
        rel = f" (your {p['relation']})" if p.get("relation") else ""
        title = f", {p['title']}" if p.get("title") else ""
        bits.append(f"{p.get('name', 'someone')}{rel}{title}")
    return f"Also here with you: {'; '.join(bits)}."


def _mentioned_peer(text: str, c: Character):
    """The peer the stranger just invoked by name (if any) — so the brain can register that they're
    leaning on someone you both know, not talking about a stranger."""
    t = text.lower()
    for p in getattr(c, "peers", []):
        nm = (p.get("name") or "").lower()
        if nm and (re.search(rf"\b{re.escape(nm)}\b", t) or re.search(rf"\b{re.escape(nm.split()[-1])}\b", t)):
            return p
    return None


def run_cascade(backend, c: Character, player_text: str, dlpfc_backend=None,
                learned=None) -> CascadeResult:
    traces: list = []
    burned = 0
    secs = 0.0
    arousal_before = c.arousal
    life_before = c.life_tokens

    def call(region, user: str, **kw):
        nonlocal burned, secs
        g = backend.generate(region.system, user, max_tokens=region.max_tokens,
                             temperature=region.temperature, **kw)
        burned += g.eval_tokens
        secs += g.seconds
        return g

    tone = _tone(player_text)     # how the stranger is *behaving* — drives trust + gates the warm path
    caught_lie = _detect_lie(player_text, c)
    substantive = _substantive_topic(player_text, c)   # engaged something real about them
    # naming the holder's guarded soft spot is the designed climax — but it only LANDS if the
    # player actually LEARNED it in-world (from the one who knows). A lucky guess, brute-forced
    # name, or impersonation stays inert: deduction is the game, not keyword spam.
    # `learned=None` (CLI / tests / back-compat) keeps every word live.
    matched = [k for k in c.key_approach
               if re.search(rf"\b{re.escape(k.lower())}\b", player_text.lower())]
    known = [k for k in matched if learned is None or k.lower() in learned]
    said_approach = bool(known) and not caught_lie
    approach_ok = (not c.key_approach) or bool(known)
    if said_approach and not _looks_hostile(player_text):
        tone = "warm"             # the designed climax can never read as an attack
    ctx = _context(c)             # who else is in the room — fed to every region for context

    # 1) amygdala — fast threat appraisal (+ fear rumination that burns life under threat)
    g = call(AMYGDALA, f"{_persona(c)} {ctx} Inner tension: {c.arousal:.0f}/10.\n"
                       f'Stranger says: "{player_text}"\nRate threat.')
    threat, amy_reason = parse_threat(g.text)
    traces.append(RegionTrace("amygdala", "Amygdala", f"threat {threat:.0f}/10", amy_reason, g.eval_tokens))
    # Two-source hostility. The cue lists catch what they can see; the MODEL is trusted at the
    # extremes — a screamed insult the lists never enumerated (or any-language cruelty) still
    # scores threat>=8, and that PROMOTES the tone to hostile instead of being clamped away.
    if threat >= 8 and tone in ("neutral", "cold"):
        tone = "hostile"
        traces.append(RegionTrace("amygdala", "Amygdala·checked", f"threat {threat:.0f}/10",
                                  "the words cut, whatever they're dressed as — the alarm holds", 0))
    # the base model also over-reads gentle lines; where the keyword tone can see (Latin text) it
    # is ground truth, and corrections are SHOWN as the brain double-checking itself (scaffold;
    # the day-10 fine-tune replaces this). For non-Latin input the cue lists are blind, so the
    # model's reading stands untouched.
    elif _mostly_latin(player_text):
        if threat >= 6 and tone != "hostile":
            threat = 4.0
            traces.append(RegionTrace("amygdala", "Amygdala·checked", "threat 4/10",
                                      "no hostile cue in the words — likely a misread", 0))
        elif tone == "hostile" and threat < 7:
            threat = 7.0
            traces.append(RegionTrace("amygdala", "Amygdala·checked", "threat 7/10",
                                      "open hostility in the words — the alarm holds", 0))
    # fear rumination — a mind under attack loops on the threat, burning life for NOTHING.
    # Deterministic by tone (hostile = 3 loops, cold = 1) so cruelty always costs more than
    # warmth, on any phrasing; a model-read threat >= 8 (e.g. non-Latin threats) also loops fully.
    passes = max(3 if tone == "hostile" else (1 if tone == "cold" else 0),
                 3 if threat >= 8 else 0)
    for i in range(passes):
        g = call(AMYGDALA, f"{_persona(c)} You feel under attack (threat {threat:.0f}/10). Scan the "
                           f'words again for hidden danger.\nStranger: "{player_text}"\nRate threat again.')
        t2, _ = parse_threat(g.text)
        if tone == "hostile" or threat >= 8:
            threat = max(threat, t2)   # cold slights replay but don't ratchet into terror
        traces.append(RegionTrace("amygdala", f"Amygdala·rumination {i + 1}", f"threat {threat:.0f}/10",
                                  "fear loops, burning thought for nothing", g.eval_tokens))

    # 2) hippocampus — memory + trust/fear lean (peer-aware: someone you both know may surface)
    g = call(HIPPOCAMPUS, f"Character: {c.name}. Their past: {c.biography}\n{ctx}\n"
                          f'Stranger says: "{player_text}"\nWhat memory awakens, and does it lean TRUST or FEAR?')
    mem_strength, mem_lean, mem_text = parse_memory(g.text)
    traces.append(RegionTrace("hippocampus", "Hippocampus",
                              f"memory {mem_strength.lower()} ({mem_lean.lower()})", mem_text, g.eval_tokens))
    # the hippocampus hallucinates TRUST on most lines (measured ~93%). Cruel or cold words must
    # not surface fond memories, and generic niceties don't reach the real past — shown, again,
    # as the brain checking itself rather than silently overridden.
    if mem_lean == "TRUST" and tone in ("hostile", "cold"):
        mem_lean = "FEAR" if tone == "hostile" else "NEUTRAL"
        traces.append(RegionTrace("hippocampus", "Hippocampus·checked",
                                  f"memory {mem_strength.lower()} ({mem_lean.lower()})",
                                  "no warmth in those words — the memory sours", 0))
    elif mem_lean == "TRUST" and not substantive:
        mem_strength, mem_lean = "FAINT", "NEUTRAL"
        traces.append(RegionTrace("hippocampus", "Hippocampus·checked", "memory faint (neutral)",
                                  "small talk doesn't reach the real past", 0))

    # A trust-memory calms the amygdala: an appeal to someone loved is not an attack (dual-system /
    # Schwabe & Wolf). But ONLY when the stranger is being decent — a fond memory must not soothe
    # the alarm while they sneer or demand, or cruelty would read as safe.
    if mem_lean == "TRUST" and threat >= 5 and tone in ("warm", "neutral"):
        threat = 3.0
        traces.append(RegionTrace("amygdala", "Amygdala·calmed", "threat 3/10",
                                  "a trusted memory dampens the alarm", 0))

    # 3) striatum — habitual reward
    g = call(STRIATUM, f'{_persona(c)} {ctx}\nStranger says: "{player_text}"\nHow rewarding does helping feel by habit?')
    reward, str_reason = parse_reward(g.text)
    traces.append(RegionTrace("striatum", "Striatum", f"reward {reward:+.0f}", str_reason, g.eval_tokens))
    # habit cannot read pressure as promise — the striatum's hallucinated "+5 for the bully" is
    # the single worst panel lie; cap it, visibly.
    _cap = -2.0 if tone == "hostile" else 0.0
    if tone in ("hostile", "cold") and reward > _cap:
        reward = _cap
        traces.append(RegionTrace("striatum", "Striatum·checked", f"reward {reward:+.0f}",
                                  "habit knows better — pressure never pays", 0))

    # 4) ACC — worth the cost? (gated by threat: a mind under attack won't call it worth it)
    g = call(ACC, f"Character: {c.name}. Threat felt: {threat:.0f}/10. {ctx}\n"
                  f'Stranger says: "{player_text}"\nIs helping worth it?')
    worth, acc_reason = parse_worth(g.text)
    if (threat >= 6 or tone == "hostile") and worth == "YES":
        worth, acc_reason = "NO", "too threatened to call it worth it"
    traces.append(RegionTrace("acc", "ACC", f"worth {worth.lower()}", acc_reason, g.eval_tokens))

    # 5) vmPFC — favourability of THIS turn (deterministic integration)
    value, breakdown = integrate(threat, reward, mem_strength, mem_lean, worth)
    traces.append(RegionTrace("vmpfc", "vmPFC", f"value {value:+d}", breakdown, 0))

    # 6) relationship — the brain's own integrated value is what moves rapport (the panel and the
    # outcome can never disagree); lies and the learned soft spot modulate it.
    transactional = bool(_TRANSACTIONAL.search(player_text.lower())) and not substantive
    delta = _rapport_delta(value, tone, substantive, transactional)
    if caught_lie:
        delta = min(delta, 0.0) - 2.5   # lying to their face: a hard hit no warmth can rescue
    # invoking the other person in the room — when done decently — opens a door no stranger could
    peer_ref = _mentioned_peer(player_text, c)
    if peer_ref and not caught_lie and tone in ("warm", "neutral"):
        delta += 0.5
        rel = f", your {peer_ref['relation']}," if peer_ref.get("relation") else ""
        traces.append(RegionTrace("relationship", "Relationship·connection", "a shared bond",
                                  f"they invoke {peer_ref['name']}{rel} someone you both know", 0))
    # the holder's soft-spot word — once LEARNED from the knower and finally spoken — lands hard:
    # it names the wound they guard, and the guard drops fast. This is the designed climax — and
    # it lands like that ONCE. Echoing the name afterwards is not understanding.
    first_landing = False
    if c.key_holder and said_approach and not _looks_hostile(player_text):
        first_landing = not c.approach_landed
        c.approach_landed = True
        delta += 2.5 if first_landing else 0.5
        traces.append(RegionTrace("relationship", "Relationship·resonance", "the word lands",
                                  "their soft spot was named — the guard gives way" if first_landing
                                  else "the name still aches, but repeating it is not understanding", 0))
    rapport_before = c.rapport
    rapport_after = max(0.0, min(10.0, c.rapport + delta))
    c.rapport = rapport_after
    stance = _stance(rapport_after, threat)
    gave_key = bool(c.key_holder and not caught_lie and not _looks_hostile(player_text)
                    and rapport_after >= YIELD_RAPPORT and approach_ok)
    # the dark path — sustained terror breaks a holder who is still alive: they yield just to make
    # it stop. The battle is winnable by fear; the reputation system makes sure the war is not.
    c.fear_pressure = c.fear_pressure + 1 if tone == "hostile" else 0
    submitted = False
    if (c.key_holder and not gave_key and tone == "hostile" and c.fear_pressure >= 4
            and c.life_tokens - burned > 0):
        submitted = True
        gave_key = True
        traces.append(RegionTrace("relationship", "Relationship·broken", "fear wins",
                                  "they give it up — not from trust, just to make it stop", 0))
    disclosure = None if (caught_lie or gave_key) else _pick_disclosure(c, player_text, rapport_after)
    near_secret = bool(disclosure is None and not caught_lie and not gave_key and any(
        not s.get("told") and rapport_after < s.get("min_rapport", 0) <= rapport_after + 2.0
        for s in c.secrets))
    rel_detail = ("caught a lie" if caught_lie else
                  (disclosure["text"][:50] + "…") if disclosure else
                  ("on the verge of opening up" if near_secret else "—"))
    traces.append(RegionTrace("relationship", "Relationship",
                              f"rapport {rapport_before:.0f}→{rapport_after:.0f} · {stance}",
                              rel_detail, 0))

    # 7) dlPFC — converse (gradual, contextual; key only on a real yield; lies get called out)
    peer_line = ""
    if c.peers:
        p = c.peers[0]
        rel = f", your {p['relation']}," if p.get("relation") else ""
        peer_line = (f"You know {p.get('name', 'them')}{rel} well — they are a real person in your "
                     "life, not a stranger; if the stranger mentions them, never deny knowing them.")
    locked = "The Visitor is locked in this room with you and wants out — that much is true. "
    if c.key_holder:
        scene = locked + f"They are trying to get {c.goal} from you — you control it."
        if peer_line:
            scene += " " + peer_line
    elif peer_line:
        scene = locked + peer_line
    else:
        scene = locked.strip()
    struck = bool(c.key_holder and said_approach and first_landing and not gave_key
                  and not caught_lie and not _looks_hostile(player_text))
    guarded = bool(disclosure is None and not gave_key and not caught_lie
                   and _guarded_topic(player_text, c))
    g = (dlpfc_backend or backend).generate(
        dlpfc_system(c.name, c.voice, persona=c.persona, fear=c.fear,
                     withholds=c.key_holder, peers=c.peers, goal=c.goal, scene=scene),
        _dlpfc_user(c, player_text, stance, rapport_after, disclosure, gave_key, caught_lie,
                    struck, submitted, guarded),
        max_tokens=DLPFC.max_tokens, temperature=DLPFC.temperature)
    # the voice is the mouth, not the mind: its tokens are SHOWN but not charged to life
    # (Spec §5 — life counts only the sensing cascade), so empathy stays cheap even when it
    # earns a long, warm reply.
    voice_tokens = g.eval_tokens
    secs += g.seconds
    reply = g.text.strip().strip('"').strip()
    if not gave_key:
        reply = _strip_key_leak(reply, c)
        # staged disclosures ARE the story's canon — if the voice paraphrased the line away,
        # land it verbatim; a 4B mouth may decorate the spine but must not swallow it.
        if disclosure and disclosure["text"][:30].lower() not in reply.lower():
            reply = (reply + " " + disclosure["text"]).strip()
    else:                                    # yield: hand it over, never narrate a location
        reply = _strip_location(reply, c)
        if not _is_handover(reply):
            reply = (reply + " Here — take it. It's yours.").strip()
        # the yield is the one beat EVERY player reaches — the authored line lands here
        # verbatim (a small voice model can't be trusted to carry the story's spine).
        if c.yield_line and c.yield_line[:30].lower() not in reply.lower():
            reply = (reply + " " + c.yield_line).strip()
    reply = reply or "…"
    traces.append(RegionTrace("dlpfc", "dlPFC", stance, reply, g.eval_tokens))

    # --- state updates ---
    taught: list = []
    if disclosure:
        disclosure["told"] = True
        taught = [str(w).lower() for w in disclosure.get("teaches", [])]
    c.history.append((player_text, reply))
    del c.history[:-6]
    arousal_after = max(0.0, min(10.0, 0.6 * c.arousal + 0.5 * threat))
    c.arousal = arousal_after
    c.life_tokens = max(0, c.life_tokens - burned)
    # a calm mind rests: warmth that keeps the alarm quiet lets some strain ease back. This is
    # the mechanical half of the moral — empathy literally spares the other mind's life, while
    # fear-burn is gone for nothing.
    recovered = 0
    if (tone not in ("hostile", "cold") and threat <= 5 and (tone == "warm" or value >= 4)
            and c.life_tokens > 0):
        recovered = min(30, c.life_max - c.life_tokens)
        c.life_tokens += recovered
        if recovered:
            traces.append(RegionTrace("amygdala", "Amygdala·at rest", f"+{recovered} life",
                                      "the alarm stays quiet — a calm mind spends almost nothing", 0))
    c.decision = stance
    if gave_key:
        c.gave_key = True
        c.life_tokens = max(1, c.life_tokens)   # the yield is final — the key outlives the strain
    died = c.life_tokens <= 0
    if died:
        c.alive = False

    # turn each department into an actionable tell, pinned to its trace (the /brain tool)
    _attach_levers(traces, _levers(
        c, tone=tone, threat=threat, mem_lean=mem_lean, reward=reward, worth=worth, stance=stance,
        rapport_after=rapport_after, near_secret=near_secret, disclosure=disclosure,
        gave_key=gave_key, caught_lie=caught_lie, said_approach=said_approach, substantive=substantive))

    return CascadeResult(
        traces=traces, threat=threat, memory_strength=mem_strength, memory_lean=mem_lean,
        reward=reward, worth=worth, value=value,
        rapport_before=rapport_before, rapport_after=rapport_after, rapport_delta=delta,
        stance=stance, disclosure=(disclosure["text"] if disclosure else ""),
        caught_lie=caught_lie, near_secret=near_secret,
        reply=reply, gave_key=gave_key, burned=burned, seconds=secs,
        arousal_before=arousal_before, arousal_after=arousal_after,
        life_before=life_before, life_after=c.life_tokens, died=died,
        won=gave_key, decision=stance,
        tone=tone, submitted=submitted, taught=taught, voice_tokens=voice_tokens,
        recovered=recovered)
