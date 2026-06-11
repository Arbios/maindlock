"""Gradio web app for Mindlock — the submission artifact (HF Space) and the Off-Brand wow.

Three panels: THE ROOM (who's here, life, reputation), DIALOGUE (talk to a mind), and
OPEN THE SKULL (the live region signals + the value flip). It wraps the proven engine
(world.py + brain.py); nothing about the cascade changes here.

Backend is chosen from the environment so the same app runs on a laptop or a Space:
    MINDLOCK_FAKE=1                 -> deterministic, no model (offline demo / dev)
    MINDLOCK_MODEL=openbmb/minicpm-v4.6
    MINDLOCK_DLPFC_MODEL=nemotron-3-nano:4b
"""
from __future__ import annotations

import base64
import html
import io
import os
import random

import gradio as gr

from .backend import FakeBackend, OllamaBackend, wants_no_think
from .brain import run_cascade
from .generator import generate_world
from .render import MORAL_CARD, moral_card_killed
from .world import load_world

_GEN_MODEL = os.environ.get("MINDLOCK_GEN_MODEL", "llama3.1:latest")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WORLD = os.environ.get("MINDLOCK_WORLD") or os.path.join(_ROOT, "config", "world.json")

_THUMB_CACHE: dict = {}


def _thumb_b64(rel_path: str, size: int = 96):
    """Small base64 thumbnail of a portrait, cached so room re-renders stay cheap."""
    if not rel_path:
        return None
    path = os.path.join(_ROOT, rel_path)
    if not os.path.exists(path):
        return None
    key = (path, os.path.getmtime(path), size)
    if key not in _THUMB_CACHE:
        from PIL import Image

        im = Image.open(path).convert("RGB")
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82)
        _THUMB_CACHE[key] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return _THUMB_CACHE[key]

_REGION_COLOR = {
    "amygdala": "#ff5555", "hippocampus": "#bd93f9", "striatum": "#f1fa8c",
    "acc": "#8be9fd", "vmpfc": "#50fa7b", "relationship": "#ffb86c", "dlpfc": "#f8f8f2",
}


# ----------------------------------------------------------------------------- backends
def _make_backends():
    if os.environ.get("MINDLOCK_FAKE"):
        return FakeBackend(), None
    model = os.environ.get("MINDLOCK_MODEL", "openbmb/minicpm-v4.6")
    dl = os.environ.get("MINDLOCK_DLPFC_MODEL", "nemotron-3-nano:4b")
    be = OllamaBackend(model=model, think=(False if wants_no_think(model) else None))
    dlbe = OllamaBackend(model=dl, think=(False if wants_no_think(dl) else None)) if dl else None
    return be, dlbe


BACKEND, DLPFC_BACKEND = _make_backends()


# ------------------------------------------------------------------------------ helpers
def _rep_note(delta: int) -> str:
    if delta > 0:
        return "Word spreads that you were kind."
    if delta <= -3:
        return "A mind went dark on your watch. Word travels ahead of you."
    return "Word spreads that you leaned on them."


def _life_color(pct: float) -> str:
    return "#50fa7b" if pct > 50 else ("#f1fa8c" if pct > 20 else "#ff5555")


def _bar(pct: float, color: str) -> str:
    pct = max(0, min(100, pct))
    return (f'<div class="bar"><div class="bar-fill" style="width:{pct:.0f}%;'
            f'background:{color}"></div></div>')


def _room_html(world) -> str:
    r = world.room
    holder = r.holder()
    rep = world.reputation
    rep_col = "#50fa7b" if rep > 0 else ("#ff5555" if rep < 0 else "#8be9fd")
    cards = ""
    for c in r.characters:
        pct = 100 * (c.life_tokens or 0) / max(1, c.life_max)
        col = _life_color(pct)
        badges = ""
        if holder and c.name == holder.name:
            badges += '<span class="badge key">KEY</span>'
        if not c.alive:
            badges += '<span class="badge dead">GONE</span>'
        else:
            ok, _ = world.can_engage(c)
            if not ok:
                badges += '<span class="badge wary">WON\'T TALK</span>'
        arousal = "●" * int(round(c.arousal / 2)) + "○" * (5 - int(round(c.arousal / 2)))
        thumb = _thumb_b64(c.portrait)
        face = f'<img class="face" src="{thumb}">' if thumb else '<div class="face noface"></div>'
        rap_pct = (c.rapport or 0) * 10
        cards += (
            f'<div class="char">{face}<div class="char-info">'
            f'<div class="char-top"><b>{html.escape(c.name)}</b>'
            f'<span class="title">{html.escape(c.title)}</span>{badges}</div>'
            f'{_bar(pct, col)}'
            f'<div class="char-sub">life {int(c.life_tokens or 0)}/{c.life_max}'
            f'<span class="arousal">{arousal}</span></div>'
            f'{_bar(rap_pct, "#ffb86c")}'
            f'<div class="char-sub">trust {c.rapport:.0f}/10<span class="title">{html.escape(c.decision)}</span></div>'
            f'</div></div>'
        )
    term = ""
    if r.terminal:
        state = "UNLOCKED" if r.terminal.unlocked else "LOCKED"
        scol = "#50fa7b" if r.terminal.unlocked else "#ff5555"
        term = (f'<div class="terminal"><span style="color:{scol}">▣ TERMINAL [{state}]</span> '
                f'<span class="title">{html.escape(r.terminal.prompt)}</span></div>')
    return (
        f'<div class="room"><div class="room-head"><span class="room-name">{html.escape(r.name)}</span>'
        f'<span class="rep" style="color:{rep_col}">reputation {rep:+d}</span></div>'
        f'<div class="room-intro">{html.escape(r.intro)}</div>{cards}{term}</div>'
    )


def _brain_html(r, c) -> str:
    rows = ""
    for t in r.traces:
        col = _REGION_COLOR.get(t.key, "#cccccc")
        rows += (
            f'<div class="region" style="border-left:3px solid {col}">'
            f'<div class="region-h"><span class="rlabel" style="color:{col}">'
            f'{html.escape(t.label)}</span><span class="rhead">{html.escape(t.headline)}</span></div>'
            f'<div class="rdetail">{html.escape(t.detail)}</div></div>'
        )
    dcol = "#50fa7b" if r.gave_key else "#ffb86c"
    verdict = "🔑 KEY GIVEN" if r.gave_key else f"rapport {r.rapport_after:.0f}/10 · {r.stance}"
    return (
        f'<div class="skull"><div class="skull-title">🧠 {html.escape(c.name)} — open the skull</div>'
        f'{rows}<div class="verdict" style="color:{dcol}">{verdict}</div>'
        f'<div class="burn">burned {r.burned} tokens · {r.seconds:.1f}s</div></div>'
    )


def _brain_idle() -> str:
    return ('<div class="skull idle"><div class="skull-title">🧠 open the skull</div>'
            '<div class="rdetail">Say something to a mind, and watch its regions argue '
            'and the decision form.</div></div>')


def _alive_names(world):
    return [c.name for c in world.room.characters if c.alive]


def _progress_events(world):
    """If the room is solved, return (events, radio_update)."""
    if not world.room.solved():
        return [], gr.update()
    if world.last_room:
        return (["🚪 **The last lock gives. The door opens.**\n\n> " +
                 MORAL_CARD.strip().replace("\n", "\n> ")], gr.update())
    world.advance()
    names = _alive_names(world)
    return ([f"➡️ **A way opens. You enter: {world.room.name}.** "
             f"You carry your reputation with you."],
            gr.update(choices=names, value=names[0] if names else None))


# ----------------------------------------------------------------------------- handlers
def _start():
    world = load_world(_WORLD)
    world.enter_room()
    names = _alive_names(world)
    intro = ("*You wake locked in. The way out runs through the people in these rooms — "
             "through what they fear and what they remember. You don't break the locks. "
             "You change minds.*")
    return world, _room_html(world), gr.update(choices=names, value=names[0]), _brain_idle(), intro, []


def _on_send(message, world, active_name, chat):
    chat = list(chat or [])
    message = (message or "").strip()
    if not message:
        return chat, gr.update(), _room_html(world), gr.update(), "", world, ""
    active = world.room.char(active_name) if active_name else world.room.characters[0]
    ok, why = world.can_engage(active)
    if not ok:
        return chat, gr.update(), _room_html(world), gr.update(), f"*{why}*", world, ""

    r = run_cascade(BACKEND, active, message, dlpfc_backend=DLPFC_BACKEND,
                    learned=world.knows(active))
    if r.taught:
        world.learned.update(r.taught)
    chat.append({"role": "user", "content": message})
    chat.append({"role": "assistant", "content": f"**{active.name}** — {r.reply}"})

    events = []
    delta = world.update_reputation(r)
    if delta:
        events.append(f"*{_rep_note(delta)} (reputation {world.reputation:+d})*")
    if r.submitted:
        events.append(f"💔 **{active.name} breaks. The key changes hands — and something in them goes out.**")
    if r.died:
        holder = world.room.holder()
        events.append(f"**{active.name}'s mind goes quiet.**")
        if holder and active.name == holder.name:
            events.append("> " + moral_card_killed(active).strip().replace("\n", "\n> "))
        else:
            events.append(f"*Whatever {active.name} knew died with them. You are on your own now.*")
    if r.disclosure:
        events.append(f"💡 *{active.name} lets something slip:* {r.disclosure}")
    elif r.caught_lie:
        events.append(f"🤥 *{active.name} catches your lie about {r.caught_lie}.*")
    elif r.near_secret:
        events.append(f"💭 *{active.name} seems on the verge of saying more — stay on it.*")
    prog, radio_update = _progress_events(world)
    events += prog
    return (chat, _brain_html(r, active), _room_html(world), radio_update,
            "\n\n".join(events), world, "")


def _on_terminal(code, world, chat):
    chat = list(chat or [])
    t = world.room.terminal
    if not t:
        return _room_html(world), "*There's no terminal in this room.*", gr.update(), world, chat
    if t.try_code(code):
        events = ["🖥️ **The terminal blinks green. ACCESS GRANTED.**"]
    else:
        events = [f"🖥️ *The terminal rejects it. {t.prompt}*"]
    prog, radio_update = _progress_events(world)
    events += prog
    return _room_html(world), "\n\n".join(events), radio_update, world, chat


def _on_reset():
    return _start()


def _on_new(world):
    """Generate a brand-new procedural scenario offline and drop the player into it."""
    try:
        nw = generate_world(model=_GEN_MODEL, seed=random.randint(0, 1_000_000))
        nw.enter_room()
    except Exception as exc:  # noqa: BLE001 — keep the current world if generation hiccups
        names = _alive_names(world) if world else []
        return (world, _room_html(world) if world else "",
                gr.update(choices=names, value=names[0] if names else None),
                _brain_idle(), f"*Couldn't conjure a new scenario: {exc}*", [])
    names = _alive_names(nw)
    intro = f"*A new world takes shape…*\n\n{nw.room.intro}"
    return (nw, _room_html(nw), gr.update(choices=names, value=names[0]), _brain_idle(), intro, [])


# -------------------------------------------------------------------------------- build
CSS = """
.gradio-container {max-width: 1300px !important}
.room {font-family: ui-monospace, monospace; font-size: 13px}
.room-head {display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px}
.room-name {font-weight:700; font-size:15px}
.room-intro {opacity:.7; margin-bottom:10px; line-height:1.4}
.char {background:rgba(255,255,255,.04); border-radius:8px; padding:8px 10px; margin-bottom:7px;
       display:flex; gap:10px; align-items:center}
.face {width:56px; height:56px; border-radius:8px; object-fit:cover; flex:0 0 auto}
.face.noface {background:rgba(255,255,255,.06)}
.char-info {flex:1; min-width:0}
.char-top {display:flex; gap:8px; align-items:center; flex-wrap:wrap}
.title {opacity:.55; font-size:11px; font-style:italic}
.badge {font-size:9px; padding:1px 6px; border-radius:6px; font-weight:700; letter-spacing:.5px}
.badge.key {background:#ffd86633; color:#ffd866}
.badge.dead {background:#ff555533; color:#ff5555}
.badge.wary {background:#ff79c633; color:#ff79c6}
.bar {height:6px; background:rgba(255,255,255,.1); border-radius:4px; overflow:hidden; margin:5px 0}
.bar-fill {height:100%; border-radius:4px; transition:width .4s}
.char-sub {display:flex; justify-content:space-between; opacity:.6; font-size:11px}
.arousal {color:#ff5555; letter-spacing:1px}
.terminal {margin-top:8px; font-family:ui-monospace,monospace; font-size:12px}
.skull {font-family: ui-monospace, monospace; font-size:12px; background:#10121a;
        border-radius:10px; padding:12px}
.skull.idle {opacity:.6}
.skull-title {font-weight:700; margin-bottom:8px; letter-spacing:.5px}
.region {padding:5px 8px; margin:4px 0; background:rgba(255,255,255,.03); border-radius:0 6px 6px 0}
.region-h {display:flex; justify-content:space-between}
.rlabel {font-weight:700}
.rhead {opacity:.9}
.rdetail {opacity:.55; font-size:11px; margin-top:2px; line-height:1.35}
.verdict {font-weight:800; font-size:15px; text-align:center; margin-top:10px;
          padding:6px; border-radius:8px; background:rgba(255,255,255,.04)}
.burn {opacity:.4; font-size:10px; text-align:center; margin-top:4px}
"""

_HEADER = (
    "<div style='text-align:center; padding:6px 0 2px'>"
    "<div style='font-size:24px; font-weight:800; letter-spacing:1px'>MINDLOCK</div>"
    "<div style='opacity:.6'>an escape room where the lock is a mind · "
    "five tiny models and two deterministic circuits per mind · everything offline</div></div>"
)


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Mindlock") as demo:
        world = gr.State()
        gr.HTML(_HEADER)
        with gr.Row():
            with gr.Column(scale=3):
                room = gr.HTML()
                active = gr.Radio(label="Talk to", interactive=True)
                with gr.Row():
                    code = gr.Textbox(label="Terminal code", scale=3, placeholder="a name…")
                    term_btn = gr.Button("Enter", scale=1)
                log = gr.Markdown()
            with gr.Column(scale=4):
                chat = gr.Chatbot(label="Dialogue", height=440)
                msg = gr.Textbox(label="Say something", placeholder="Speak plainly. You change his mind, not the lock.")
                with gr.Row():
                    send = gr.Button("Speak", variant="primary")
                    reset = gr.Button("Restart room")
                    new_btn = gr.Button("🎲 New scenario")
            with gr.Column(scale=3):
                brain = gr.HTML()

        demo.load(_start, outputs=[world, room, active, brain, log, chat])
        send_io = dict(fn=_on_send, inputs=[msg, world, active, chat],
                       outputs=[chat, brain, room, active, log, world, msg])
        send.click(**send_io)
        msg.submit(**send_io)
        term_btn.click(_on_terminal, inputs=[code, world, chat],
                       outputs=[room, log, active, world, chat])
        reset.click(_on_reset, outputs=[world, room, active, brain, log, chat])
        new_btn.click(_on_new, inputs=[world], outputs=[world, room, active, brain, log, chat])
    return demo
