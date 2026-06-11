"""FastAPI server for the walkable game.

Serves the canvas frontend and a small JSON API over a single `GameSession`. The movement
loop lives in the browser; every server call is a discrete game action (talk / terminal /
walk through door), so the round-trips stay coarse and the canvas stays smooth.

Run for dev:  python scripts/run_game.py   (or MINDLOCK_FAKE=1 python scripts/run_game.py)
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .session import GameSession

_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# One process == one player for now. Per-session state (cookies) is a later step; the slice
# proves the canvas <-> engine loop first.
SESSION = GameSession()


def create_app() -> FastAPI:
    app = FastAPI(title="Mindlock")
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(_STATIC, "index.html"))

    @app.get("/api/state")
    def state():
        return SESSION.state()

    @app.get("/api/manifest")
    def manifest():
        """Frame counts for every animation dir under static/ — the client loads sprite
        sequences from known counts instead of 404-probing for the end of each one."""
        out = {}
        for root, _dirs, files in os.walk(_STATIC):
            n = sum(1 for f in files if f.startswith("frame_") and f.endswith(".png"))
            if n:
                out[os.path.relpath(root, _STATIC).replace(os.sep, "/")] = n
        return out

    @app.get("/favicon.ico")
    def favicon():
        return FileResponse(os.path.join(_STATIC, "menu", "key.png"))

    @app.post("/api/talk")
    async def talk(request: Request):
        body = await request.json()
        return SESSION.talk(int(body.get("char_id", -1)), str(body.get("message", "")))

    @app.post("/api/terminal")
    async def terminal(request: Request):
        body = await request.json()
        return SESSION.terminal(str(body.get("code", "")))

    @app.post("/api/next-room")
    def next_room():
        return SESSION.next_room()

    @app.post("/api/reset")
    def reset():
        return SESSION.reset()

    @app.post("/api/start")               # title menu: begin a run in "story" or "endless" mode
    async def start(request: Request):
        body = await request.json()
        return SESSION.start(str(body.get("mode", "endless")))

    @app.post("/api/editor/save")         # layout editor: write the arranged layout into the level
    async def editor_save(request: Request):
        body = await request.json()
        return SESSION.save_layout(body.get("layout") or {})

    @app.get("/api/editor/level")         # character editor: the current level's dialogue halves
    def editor_level():
        return SESSION.editor_level()

    @app.post("/api/editor/character")    # character editor: write edited prompt fields into the level
    async def editor_character(request: Request):
        body = await request.json()
        return SESSION.save_character(int(body.get("char_id", -1)), body.get("fields") or {})

    @app.post("/api/dev/room")            # dev: jump to a specific room
    async def dev_room(request: Request):
        body = await request.json()
        return SESSION.goto_room(int(body.get("idx", 0)))

    @app.post("/api/dev/generate")        # dev: generate a real procedural room (LLM narrative)
    def dev_generate():
        return SESSION.dev_generate()

    @app.post("/api/dev/roster")          # dev: assemble a room from minted roster members
    def dev_roster():
        return SESSION.dev_roster()

    @app.get("/api/portrait/{char_id}")
    def portrait(char_id: int):
        path = SESSION.portrait_file(char_id)
        if not path:
            return JSONResponse({"error": "no portrait"}, status_code=404)
        return FileResponse(path)

    return app


app = create_app()
