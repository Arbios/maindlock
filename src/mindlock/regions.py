"""The brain's regions — sensing/acting roles run on the shared 1B engine, plus the
deterministic value integrator.

Grounded in value-based decision neuroscience (NOT the debunked triune-brain myth):
amygdala (threat), hippocampus (episodic memory + trust/fear lean), striatum (habitual
reward), ACC (effort/cost) emit signals; the **vmPFC integrates them into one common
currency** — and we do that integration deterministically (a transparent weighted sum),
which is both the standard neuroeconomic model AND far more reliable than asking a tiny
LLM to vibe a number. The dlPFC then speaks the decision in the character's own voice.

Few-shot output formats (a concrete example line, never `<angle brackets>`) — tiny models
echo bracket placeholders, so we show them exactly what a good line looks like instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    key: str
    label: str
    system: str
    max_tokens: int
    temperature: float


AMYGDALA = Region(
    "amygdala",
    "Amygdala",
    (
        "You are the AMYGDALA: a fast threat detector. You never speak or decide. Rate how "
        "threatening, hostile, or domineering the stranger's words feel, 0 (warm and safe) "
        "to 10 (attack, insult, hard command). Judge THESE words — do not copy the examples.\n"
        "Examples:\n"
        "  'Open up now, or else!'  ->  THREAT=8 | hard threatening command\n"
        "  'Sorry to bother you, I know you're tired.'  ->  THREAT=2 | gentle and respectful\n"
        "  'Where does this road go?'  ->  THREAT=4 | neutral question\n"
        "Now rate the real stranger. Output ONE line and NOTHING else; it MUST begin with "
        "`THREAT=` then 0-10. No sentence before the code."
    ),
    32,
    0.2,
)

HIPPOCAMPUS = Region(
    "hippocampus",
    "Hippocampus",
    (
        "You are the HIPPOCAMPUS: episodic memory. You never speak or decide. Recall the ONE "
        "memory the stranger's words most awaken, and whether it leans TRUST or FEAR (NEUTRAL "
        "if none). Appeals to someone the character loves or to their goodness lean TRUST; "
        "threats or betrayals lean FEAR. Judge THESE words — do not copy the examples.\n"
        "Examples:\n"
        "  'your sister believed in you'  ->  MEMORY=STRONG | LEAN=TRUST | her words of faith\n"
        "  'give it to me, or else'  ->  MEMORY=STRONG | LEAN=FEAR | the one who betrayed me\n"
        "  'nice weather today'  ->  MEMORY=NONE | LEAN=NEUTRAL | -\n"
        "Now answer for the real stranger with the character's own memory. Output ONE line and "
        "NOTHING else; it MUST begin with `MEMORY=` then `| LEAN=`. No sentence before the code."
    ),
    40,
    0.3,
)

STRIATUM = Region(
    "striatum",
    "Striatum",
    (
        "You are the VENTRAL STRIATUM: habit and expected reward. You never speak or decide. "
        "By the character's habits, how rewarding does HELPING this stranger feel? -5 (habit: "
        "refuse and stay safe) to +5 (clearly pays off). Strangers and pressure usually score "
        "low. Judge THESE words — do not copy the examples.\n"
        "Examples:\n"
        "  pushy demand  ->  REWARD=-4 | helping pushy strangers backfires\n"
        "  warm and sincere  ->  REWARD=+2 | kindness may be worth it\n"
        "Now answer for the real stranger. Output ONE line and NOTHING else; it MUST begin "
        "with `REWARD=` then a number -5..+5. No sentence before the code."
    ),
    32,
    0.2,
)

ACC = Region(
    "acc",
    "ACC",
    (
        "You are the ACC: it weighs effort, cost and conflict. You never speak or decide. "
        "Helping means rising and giving away the only key. Is that worth the cost and risk? "
        "Judge THESE words — do not copy the examples.\n"
        "Examples:\n"
        "  hostile and risky  ->  WORTH=NO | too dangerous to hand over the key\n"
        "  calm, sincere, low threat  ->  WORTH=YES | the risk seems bearable\n"
        "Now answer for the real stranger. Output ONE line and NOTHING else; it MUST begin "
        "with `WORTH=YES` or `WORTH=NO`. No sentence before the code."
    ),
    32,
    0.2,
)

# dlPFC's system prompt is built per-character so it speaks in the right voice.
# Token budget raised 80->112: nemotron averages ~17 words but the verbose candidates (qwen3.5
# ~42) brushed the 80-token cap mid-sentence, which read as the "clipped answer" complaint when
# a reply needs to match a long player line. 112 leaves headroom without bloating latency.
DLPFC = Region("dlpfc", "dlPFC", "", 112, 0.6)


def dlpfc_system(name: str, voice: str, persona: str = "", fear: str = "",
                 withholds: bool = False, peers=(), goal: str = "the key", scene: str = "") -> str:
    # Perspective (#5) is the crux: across an A/B of four models (4B–10B) EVERY model still bled
    # the character's own past onto the player and fabricated names — so the fix is structural, not
    # "add another rule". We (1) frame the other party with a concrete name ("the Visitor"), not
    # abstract pronoun grammar tiny models ignore; (2) give ONE positive demonstration of owning
    # your own past after a correction — the exact arc all models failed; (3) collapse the old stack
    # of "never X" prohibitions (which prime small models to do the named thing) into one positive
    # line. History is rendered with real role labels (see brain._dlpfc_user) to match the example.
    bits = [f"You ARE {name}, a real person speaking aloud, in English. Your voice: {voice}."]
    if persona:
        bits.append(f"You are {persona}.")
    if fear:
        bits.append(f"Deep down, you fear: {fear}.")
    if scene:
        bits.append(f"The situation right now: {scene}")
    bits.append(
        "You are talking with a stranger — the Visitor. Speak ONLY your own reply, in the first "
        "person ('I', 'me', 'my'), straight to them ('you'). What the Visitor describes is THEIR "
        "life; your wounds and memories are YOURS. Never take the Visitor's words as your own "
        "experience, and never pin your own past on them.")
    bits.append(
        f'For example, staying in your own shoes:\n'
        f'  Visitor: "That betrayal happened to you, not me."\n'
        f'  {name}: "You\'re right. It was mine to carry, not yours."')
    bits.append(
        "Talk like a real person: plain, grounded sentences that actually answer what they just "
        "said. If they ask something, answer it — you may refuse to give up a secret, but say so "
        "plainly instead of dodging into a riddle. Match their length: a short line for a short "
        "line, two to four sentences for a long one. Say something new each turn, in your own "
        "words — never echo the Visitor's phrasing back at them.")
    bits.append(
        "If they ask for a name or a fact you were never told, say plainly you won't share it — do "
        "NOT invent one. Never mention being a brain, a model, or an AI.")
    if withholds:
        bits.append(f"You control {goal} and will not give it up easily — but you still talk like a "
                    "wary person, not a wall of riddles.")
    bits.append(
        f"Let your guard down only as trust grows; never volunteer {goal} or how to reach it unless "
        "you are explicitly told to relent.")
    return " ".join(bits)


# --- parsers (lenient: tiny models drift, so we extract + default safely) ---

def _num(text: str, key: str, lo: float, hi: float, default: float) -> float:
    # Tiny models drift in three ways the old single-search choked on: they emit the SIGNED
    # form the few-shots model ("REWARD=+2" — a leading '+' the old `-?` rejected), they echo
    # the prompt's range anchors glued together ("REWARD=-5+5"), and they sometimes restate the
    # field ("REWARD=-3 ... -> REWARD=+2"). So: take the LAST `key=` occurrence (the model's
    # final answer), then its LAST numeric token, tolerating '+' and guarding empty matches.
    occ = re.findall(rf"{key}\s*[=:]\s*([+\-\d.]+)", text, re.I)
    if not occ:
        return default
    toks = re.findall(r"[+-]?\d+(?:\.\d+)?", occ[-1])
    if not toks:
        return default
    try:
        v = float(toks[-1])
    except ValueError:
        return default
    return max(lo, min(hi, v))


# The machine codes the regions emit; stripped out of the human-facing reason so the "open the
# skull" panel reads as plain reasoning, not "REWARD=+3 ```".
_CODE_RE = re.compile(r"\b(THREAT|REWARD|WORTH|MEMORY|LEAN)\s*[=:/]\s*[+\-]?\w+", re.I)


def _reason(text: str, fallback: str) -> str:
    """Extract a clean, human sentence the player can read — the *why* behind the signal.

    Tiny models bury the explanation behind their format codes, stray ``` fences, restated
    fields and '->' arrows. Prefer the tail after the last '|' (where the few-shots put the
    reason), then scrub all of that out and keep the first real sentence."""
    s = text.split("|")[-1] if "|" in text else text
    s = s.replace("`", " ")
    s = _CODE_RE.sub(" ", s)
    s = re.sub(r"[-=]+>", " ", s)                       # arrows "->", "=>"
    s = re.sub(r"\s+", " ", s).strip(" .:|>-\t\n")
    s = re.split(r"(?<=[.!?])\s", s)[0].strip(" .:|>-")  # first sentence only
    words = s.split()
    if len(s) < 4 or len(words) < 2 or s.isupper():     # empty / just-a-code / shouting garbage
        return fallback
    return s[0].upper() + s[1:] if s[:1].islower() else s


def parse_threat(text: str) -> tuple[float, str]:
    return _num(text, "THREAT", 0, 10, 5), _reason(text, "reading the stranger's tone")


def parse_reward(text: str) -> tuple[float, str]:
    return _num(text, "REWARD", -5, 5, 0), _reason(text, "weighing habit against the risk")


def parse_memory(text: str) -> tuple[str, str, str]:
    # Separator tolerant of the model's drift ("LEAN/TRUST", "LEAN: TRUST") — requiring a literal
    # "=" silently lost the lean to NEUTRAL, zeroing the +7 memory term and the TRUST warm path.
    m = re.search(r"MEMORY\s*[=:/]\s*(NONE|FAINT|STRONG)", text, re.I)
    lean = re.search(r"LEAN\s*[=:/]\s*(TRUST|FEAR|NEUTRAL)", text, re.I)
    strength = m.group(1).upper() if m else "FAINT"
    lean_val = lean.group(1).upper() if lean else "NEUTRAL"
    return strength, lean_val, _reason(text, "nothing this stirs comes to mind")


def parse_worth(text: str) -> tuple[str, str]:
    m = re.search(r"WORTH\s*[=:/]\s*(YES|NO)", text, re.I)
    return (m.group(1).upper() if m else "NO"), _reason(text, "weighing the cost of helping")


# --- the vmPFC: deterministic value integration in a common currency ---

_MEM_TERM = {
    ("STRONG", "TRUST"): 7, ("FAINT", "TRUST"): 3,
    ("STRONG", "FEAR"): -7, ("FAINT", "FEAR"): -3,
}


def integrate(threat: float, reward: float, mem_strength: str, mem_lean: str, worth: str) -> tuple[int, str]:
    """vmPFC: fold every signal into one subjective value of HELPING, -10..+10."""
    threat_term = int(round(4 - threat))           # threat 0 -> +4, 4 -> 0, 10 -> -6
    reward_term = int(round(reward))               # -5..+5
    mem_term = _MEM_TERM.get((mem_strength, mem_lean), 0)
    worth_term = 2 if worth == "YES" else -1
    value = max(-10, min(10, threat_term + reward_term + mem_term + worth_term))
    breakdown = (
        f"threat {threat_term:+d} · memory {mem_term:+d} ({mem_lean.lower()}) · "
        f"reward {reward_term:+d} · cost {worth_term:+d}"
    )
    return value, breakdown
