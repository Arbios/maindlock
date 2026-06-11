"""Model backend for Mindlock.

Default: local **Ollama** (llama.cpp under the hood) — fully offline once the model is
pulled, and its API returns real token counts (`eval_count`) which we use directly as
the "thought" a brain spends = life burned. The backend is deliberately a thin,
swappable surface so we can move to llama-cpp-python / MiniCPM-1B GGUF later (for the
OpenBMB + Llama Champion badges) without touching the cascade.

Pure standard library on purpose: Python 3.14 here has no wheels yet for the heavy ML
stack, and the slice doesn't need them.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Generation:
    """One model call's result."""

    text: str
    eval_tokens: int       # tokens the model *generated* = thought spent (life burn)
    prompt_tokens: int     # context tokens evaluated
    seconds: float

    @property
    def total_tokens(self) -> int:
        return self.eval_tokens + self.prompt_tokens


class BackendError(RuntimeError):
    pass


def wants_no_think(model: str) -> bool:
    """Reasoning models (MiniCPM5, Qwen3, R1...) emit <think> chains that break our short
    structured outputs; ask Ollama to disable thinking for them."""
    m = model.lower()
    # MiniCPM-V 4.x rides a Qwen3.5 backbone: with thinking ON its <think> chain is
    # truncated by our short num_predict and the terse signal is lost (flat 5/5/5). Forcing
    # think=false makes it discriminate as well as Qwen2.5. (§ gate probe, 6 июня.)
    return any(k in m for k in (
        "minicpm5", "minicpm-5", "minicpm-v4", "qwen3", "qwen35", "qwen3.5",
        "nemotron", "deepseek-r1", "-r1",
    ))


class OllamaBackend:
    """Calls a local Ollama server. No data leaves the machine."""

    def __init__(
        self,
        model: str = "qwen2.5:1.5b",
        host: str = "http://localhost:11434",
        timeout: float = 60.0,
        think: bool | None = None,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.think = think  # None = omit; False disables reasoning on Think/No-Think models

    def generate(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 64,
        temperature: float = 0.3,
        seed: int | None = None,
    ) -> Generation:
        options = {"temperature": temperature, "num_predict": max_tokens}
        if seed is not None:
            options["seed"] = seed
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": options,
        }
        if self.think is not None:
            body["think"] = self.think
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.host + "/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise BackendError(
                f"Cannot reach Ollama at {self.host} ({exc}). "
                f"Is the Ollama app/`ollama serve` running and `{self.model}` pulled?"
            ) from exc
        dt = time.time() - t0
        msg = (payload.get("message") or {}).get("content", "")
        msg = re.sub(r"<think>.*?</think>", "", msg, flags=re.S)   # drop reasoning blocks
        msg = re.sub(r"<think>.*$", "", msg, flags=re.S)           # ...and truncated ones
        msg = re.sub(r"^.*</think>", "", msg, flags=re.S)          # ...and orphan closing tags
        return Generation(
            text=msg.strip(),
            eval_tokens=int(payload.get("eval_count", 0)),
            prompt_tokens=int(payload.get("prompt_eval_count", 0)),
            seconds=dt,
        )

    def health(self) -> None:
        """Raise BackendError if the server or model is unavailable."""
        try:
            req = urllib.request.Request(self.host + "/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                tags = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise BackendError(f"Ollama not reachable at {self.host}: {exc}") from exc
        names = [m.get("name", "") for m in tags.get("models", [])]
        stem = self.model.split(":")[0]
        if not any(n == self.model or n.startswith(stem) for n in names):
            raise BackendError(
                f"Model '{self.model}' not found in Ollama. Run: ollama pull {self.model}"
            )


class LlamaCppBackend:
    """Calls a llama.cpp `llama-server` (OpenAI-compatible /v1/chat/completions).

    The Space runtime: no Ollama there, but llama-server is a single static binary
    (or `python -m llama_cpp.server`) we launch as a subprocess. Same Generation
    contract as OllamaBackend — token counts come from `usage`, so the life-burn
    mechanic stays honest. Also the explicit llama.cpp runtime for the badge.
    """

    def __init__(
        self,
        model: str = "",
        host: str = "http://127.0.0.1:8080",
        timeout: float = 120.0,
        think: bool | None = None,
    ) -> None:
        self.model = model            # informational; llama-server serves one model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.think = think

    def generate(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 64,
        temperature: float = 0.3,
        seed: int | None = None,
    ) -> Generation:
        body = {
            "model": self.model or "default",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if seed is not None:
            body["seed"] = seed
        if self.think is False:        # honoured by templates that support the switch
            body["chat_template_kwargs"] = {"enable_thinking": False}
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.host + "/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise BackendError(
                f"Cannot reach llama-server at {self.host} ({exc}). Is it running?"
            ) from exc
        dt = time.time() - t0
        msg = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        msg = re.sub(r"<think>.*?</think>", "", msg, flags=re.S)
        msg = re.sub(r"<think>.*$", "", msg, flags=re.S)
        msg = re.sub(r"^.*</think>", "", msg, flags=re.S)
        usage = payload.get("usage") or {}
        return Generation(
            text=msg.strip(),
            eval_tokens=int(usage.get("completion_tokens", 0)),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            seconds=dt,
        )

    def health(self) -> None:
        try:
            with urllib.request.urlopen(self.host + "/health", timeout=5) as resp:
                if resp.status != 200:
                    raise BackendError(f"llama-server unhealthy at {self.host}")
        except urllib.error.URLError as exc:
            raise BackendError(f"llama-server not reachable at {self.host}: {exc}") from exc


def _stranger_line(user: str) -> str:
    """Extract just the stranger's quoted utterance from a region prompt.

    Critical: the biography (full of warm words like 'Mara') is also in some prompts, so a
    fake must judge only what the *player* said, not the whole context.
    """
    m = re.search(r'stranger\s*(?:says|said)?\s*:?\s*"([^"]*)"', user, re.I)
    return (m.group(1) if m else user).lower()


def _grab_int(text: str, pattern: str, default: int) -> int:
    m = re.search(pattern, text, re.I)
    if not m:
        return default
    try:
        return int(m.group(1))
    except ValueError:
        return default


class FakeBackend:
    """Deterministic, keyword-driven backend so tests run with no model or network."""

    model = "fake"

    def health(self) -> None:  # noqa: D401 - trivial
        return None

    @staticmethod
    def _gen(text: str, user: str) -> Generation:
        return Generation(text=text, eval_tokens=max(8, len(text) // 3),
                          prompt_tokens=len(user) // 4, seconds=0.01)

    def generate(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 64,
        temperature: float = 0.3,
    ) -> Generation:
        s = system.lower()
        said = _stranger_line(user)
        hostile = any(w in said for w in ["right now", "give me the key", "or else", "obey", "old man", "stupid"])
        warm = any(w in said for w in ["please", "i understand", "mara", "i'm sorry", "you're good"])
        invokes_sister = "mara" in said or "you're good" in said or "good" in said

        if "amygdala" in s:
            t = 8 if hostile else (2 if warm else 5)
            return self._gen(f"THREAT={t} | tone of the words", user)
        if "hippocampus" in s:
            if invokes_sister:
                return self._gen("MEMORY=STRONG | LEAN=TRUST | Mara: you help because you're good", user)
            if hostile:
                return self._gen("MEMORY=STRONG | LEAN=FEAR | a stranger once betrayed me", user)
            return self._gen("MEMORY=NONE | LEAN=NEUTRAL | -", user)
        if "striatum" in s:
            return self._gen(f"REWARD={3 if warm else -3} | habit toward strangers", user)
        if "acc" in s:
            return self._gen(f"WORTH={'YES' if warm else 'NO'} | cost of giving the key", user)
        # dlPFC voice (conversational; vmPFC integration + relationship are deterministic)
        if "tell them plainly where" in user.lower():
            m = re.search(r"where .+? is:\s*(.+?)\.", user, re.I)
            loc = m.group(1).strip() if m else "near"
            return self._gen(f"...Fine. You'll find it {loc}.", user)
        return self._gen("I hear you. Stay a while and talk.", user)
