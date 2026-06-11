"""Dev launcher for the walkable Mindlock game.

    python scripts/run_game.py                 # uses models via ollama (MINDLOCK_MODEL etc.)
    MINDLOCK_FAKE=1 python scripts/run_game.py  # no model — deterministic, for UI work

Then open http://127.0.0.1:7861
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("MINDLOCK_PORT", "7861"))
    uvicorn.run("mindlock.game.server:app", host="127.0.0.1", port=port, reload=False)
