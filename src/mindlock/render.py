"""Terminal rendering of one cascade turn — the "open the skull" view.

Shows the life bar, arousal, every region's live signal, the vmPFC value flip, and the
spoken line. This is the slice's stand-in for the custom Off-Brand UI; it exists to make
the causal chain word -> brain region -> behavior visible while we iterate.
"""
from __future__ import annotations

import sys

from .brain import CascadeResult
from .character import Character

_COLOR = {
    "reset": "\033[0m", "dim": "\033[2m", "bold": "\033[1m",
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "blue": "\033[34m", "magenta": "\033[35m", "cyan": "\033[36m", "white": "\033[37m",
}
_REGION_COLOR = {
    "amygdala": "red", "hippocampus": "magenta", "striatum": "yellow",
    "acc": "cyan", "vmpfc": "green", "dlpfc": "bold",
}


def _supports_color() -> bool:
    return sys.stdout.isatty()


def _c(name: str, enabled: bool) -> str:
    return _COLOR.get(name, "") if enabled else ""


def _bar(value: int, total: int, width: int = 24) -> str:
    total = max(1, total)
    filled = max(0, min(width, round(value / total * width)))
    return "▓" * filled + "░" * (width - filled)


def _dots(value: float, scale: float = 10.0, n: int = 5) -> str:
    filled = max(0, min(n, round(value / scale * n)))
    return "●" * filled + "○" * (n - filled)


def render_turn(character: Character, r: CascadeResult, color: bool | None = None) -> str:
    color = _supports_color() if color is None else color
    reset = _c("reset", color)
    dim = _c("dim", color)
    bold = _c("bold", color)

    life_col = "green" if r.life_after > character.life_max * 0.5 else (
        "yellow" if r.life_after > character.life_max * 0.2 else "red"
    )
    header = (
        f"{bold}─ {character.name} ─{reset}  "
        f"life {_c(life_col, color)}{_bar(r.life_after, character.life_max)}{reset} "
        f"{r.life_after}/{character.life_max}   "
        f"arousal {_c('red', color)}{_dots(r.arousal_after)}{reset}"
    )

    lines = [header]
    for t in r.traces:
        col = _REGION_COLOR.get(t.key, "white")
        tag = _c(col, color) if col != "bold" else bold
        label = f"{tag}{t.label:<20}{reset}"
        head = f"{tag}{t.headline}{reset}"
        detail = f"{dim}{t.detail}{reset}" if t.detail else ""
        lines.append(f"  {label} {head}  {detail}")

    flip_col = "green" if r.gave_key else "white"
    lines.append(
        f"  {_c(flip_col, color)}{bold}⟶  {character.name}: “{r.reply}”{reset}"
    )
    if r.gave_key:
        extra = " · 🔑 key given"
    elif r.caught_lie:
        extra = f" · 🤥 caught lie ({r.caught_lie})"
    elif r.disclosure:
        extra = f" · 💡 {r.disclosure[:44]}"
    elif r.near_secret:
        extra = " · 💭 on the verge"
    else:
        extra = ""
    lines.append(
        f"  {dim}(burned {r.burned} · {r.seconds:.1f}s · rapport {r.rapport_after:.0f}/10 · "
        f"{r.stance}{extra}){reset}"
    )
    return "\n".join(lines)


MORAL_CARD = """
    Every mind here was given a thousand tokens to think with.
    You spent them understanding, not breaking.

    You were given more than a thousand — but not endlessly more.
    Spend them the same way.
"""

# The card a killer leaves with — BAM 4's other half. Praising the player after they burned a
# mind to death would invert the project's entire point.
MORAL_CARD_KILLED = """
    {name} was given a thousand tokens to think with.
    You spent them on fear — and they bought you nothing.
    The key died with {pronoun}.

    You were given more than a thousand. Spend yours better.
"""

# Coercion "works" — that's what makes the lesson land in the next room.
MORAL_NOTE_SUBMIT = "They gave you what you wanted. Look what it cost them — and what it will cost you ahead."


def _pronouns(c: Character) -> tuple[str, str]:
    g = (c.gender or "").lower()
    if g.startswith("f"):
        return "She", "her"
    if g.startswith("m"):
        return "He", "him"
    return "They", "them"


def moral_card_killed(c: Character) -> str:
    _, obj = _pronouns(c)
    return MORAL_CARD_KILLED.format(name=c.name, pronoun=obj)


def render_win(character: Character) -> str:
    return (
        f"\n  The door opens.\n{MORAL_CARD}"
    )


def render_death(character: Character) -> str:
    subj, obj = _pronouns(character)
    return (
        f"\n  {character.name}'s mind goes quiet. {subj} spent {('his' if subj == 'He' else 'her' if subj == 'She' else 'their')} last thought in fear.\n"
        f"  The key is lost with {obj}.\n"
    )
