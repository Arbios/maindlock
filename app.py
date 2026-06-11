"""Hugging Face Space entry point for Mindlock.

One process serves everything (the Off-Brand pattern):
  /        — the game: custom canvas front (FastAPI + static), the "open the skull" UI
  /about   — a Gradio block with how-to-play, links and the eligibility map

Backends, picked by env:
  MINDLOCK_FAKE=1                       deterministic demo, no models
  (default, laptop)                     Ollama — minicpm-v4.6 + nemotron-3-nano:4b
  MINDLOCK_BACKEND=llamacpp             llama.cpp runtime: llama-server subprocesses,
                                        GGUF weights pulled from the Hub on first boot

  python app.py                                       # laptop (Ollama)
  MINDLOCK_FAKE=1 python app.py                       # no models
  MINDLOCK_BACKEND=llamacpp python app.py             # llama.cpp (the Space path)
"""
import atexit
import os
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# --------------------------------------------------------------- llama.cpp boot (Space)
# Two single-model servers (sensors + voice), weights from the Hub. Started BEFORE the
# game session imports so health checks see them.
_LLAMA = [
    # (env host var,                 port, repo,                                file,                              )
    ("MINDLOCK_LLAMA_HOST", 8091, os.environ.get("MINDLOCK_GGUF_REPO", "openbmb/MiniCPM5-1B-GGUF"),
     os.environ.get("MINDLOCK_GGUF_FILE", "MiniCPM5-1B-Q4_K_M.gguf")),
    ("MINDLOCK_LLAMA_DLPFC_HOST", 8092, os.environ.get("MINDLOCK_GGUF_DLPFC_REPO", "nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF"),
     os.environ.get("MINDLOCK_GGUF_DLPFC_FILE", "NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf")),
]


def _fetch_llama_server() -> str:
    """No system llama-server (the Space): pull the official prebuilt linux-x64 binary
    from the llama.cpp release — a 5MB zip beats a 30-minute source build of the wheel."""
    import io
    import json as _json
    import tarfile

    cache = os.path.expanduser("~/.cache/mindlock/llama")
    marker = os.path.join(cache, ".ready")
    if os.path.exists(marker):
        with open(marker) as fh:
            return fh.read().strip()
    os.makedirs(cache, exist_ok=True)
    rel = _json.loads(urllib.request.urlopen(
        "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest", timeout=30).read())
    asset = next(a for a in rel["assets"]
                 if "bin-ubuntu-x64" in a["name"] and a["name"].endswith(".tar.gz"))
    blob = urllib.request.urlopen(asset["browser_download_url"], timeout=300).read()
    tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz").extractall(cache)
    binpath = ""
    for root, _, files in os.walk(cache):       # binary + its .so live in build/bin
        for f in files:
            full = os.path.join(root, f)
            if f == "llama-server":
                os.chmod(full, 0o755)
                binpath = full
            elif f.endswith(".so"):
                os.chmod(full, 0o755)
    if not binpath:
        raise RuntimeError("llama-server not found inside the release archive")
    os.environ["LD_LIBRARY_PATH"] = (os.path.dirname(binpath) + ":"
                                     + os.environ.get("LD_LIBRARY_PATH", ""))
    with open(marker, "w") as fh:
        fh.write(binpath)
    return binpath


def _llama_cmd(path: str, port: int) -> list[str]:
    server = shutil.which("llama-server") or _fetch_llama_server()
    return [server, "-m", path, "--port", str(port), "-c", "4096", "--no-warmup"]


def _boot_llama() -> None:
    from huggingface_hub import hf_hub_download
    for env_var, port, repo, fname in _LLAMA:
        path = hf_hub_download(repo_id=repo, filename=fname)
        proc = subprocess.Popen(
            _llama_cmd(path, port),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        atexit.register(proc.terminate)
        os.environ[env_var] = f"http://127.0.0.1:{port}"
    deadline = time.time() + 300
    for _, port, _, _ in _LLAMA:
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
                break
            except Exception:  # noqa: BLE001
                time.sleep(1.5)


if os.environ.get("SPACE_ID") and "MINDLOCK_BACKEND" not in os.environ:
    os.environ["MINDLOCK_BACKEND"] = "llamacpp"   # a Space has no Ollama — default to llama.cpp

if os.environ.get("MINDLOCK_BACKEND") == "llamacpp" and not os.environ.get("MINDLOCK_FAKE"):
    _boot_llama()

import gradio as gr  # noqa: E402

from mindlock.game.server import app  # noqa: E402 — the FastAPI game (custom front at /)

ABOUT_MD = """
# 🧠 MINDLOCK

**An escape room where every character is not one AI — but a hierarchy of tiny offline
language models: the departments of one mind.** You don't pick a lock. You change a mind.

**[▶ Play](/)** · every NPC runs a 6-region brain cascade (amygdala → hippocampus →
striatum → ACC → vmPFC → dlPFC) on small local models. Cruelty burns their finite
thinking tokens; empathy lets them heal. A mind that reaches zero is gone — with
everything it knew.

## How to play
- **WASD / arrows** — move · **E** — talk / use · **🧠 / /brain** — open the skull
- Each room: someone holds the key. Someone else knows what reaches them. Listen,
  learn the word that matters, say it like you mean it.
- **Story** — ten rooms of one man's memory. Find out who you are. *(~30 min)*
- **Endless** — procedurally generated minds, forever.

## Small models, doing the carrying
| Role | Model |
|---|---|
| Sensory regions (threat, memory, habit, cost) | MiniCPM (OpenBMB) |
| Voice — the words a mind says out loud | Nemotron 3 Nano 4B (NVIDIA) |
| Runtime | llama.cpp / Ollama — fully offline |

*Links: demo video · social post · GitHub repo — added at submission.*

---

🤗 *Built small for the **Hugging Face × Gradio** hackathon (Thousand Token Wood track).
Minds by **OpenBMB MiniCPM** and **NVIDIA Nemotron**, running on **llama.cpp** — fully offline.*
"""

about = gr.Blocks(title="Mindlock — about")
with about:
    gr.Markdown(ABOUT_MD)

app = gr.mount_gradio_app(app, about, path="/about")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", os.environ.get("MINDLOCK_PORT", 7860))))
