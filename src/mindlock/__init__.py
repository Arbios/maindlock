"""Mindlock — an escape room where each character's mind is a swarm of tiny (1B) models.

Vertical slice: one character, the six-region value-based decision cascade, honest
per-turn token accounting (the basis of the "1000 tokens = a life" mechanic), and a
visible decision flip (REFUSE -> HELP) driven by the vmPFC value integrator.

Fully offline. Default backend: local Ollama (llama.cpp under the hood); swappable.
"""

__all__ = ["__version__"]
__version__ = "0.0.1"
