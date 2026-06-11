"""Mindlock as a walkable, endless top-down game.

A thin spatial + roguelike shell over the proven engine (world/brain/generator). The browser
runs the movement on a canvas; the server (FastAPI, mounted on the same process) runs the
brain cascade and streams new procedural rooms. The engine itself is untouched.
"""
