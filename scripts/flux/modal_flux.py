"""Render Mindlock character portraits with FLUX.2-klein-4B on Modal (BFL lane / Tiny Titan ≤4B).

    .venv/bin/python -m modal run scripts/flux/modal_flux.py     # -> scripts/flux/out/*.png

First run downloads klein-4B (~13GB) into a Modal Volume; later runs hit the cache.
"""
import modal

app = modal.App("mindlock-flux")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .pip_install(
        "torch",
        "transformers",
        "accelerate",
        "sentencepiece",
        "protobuf",
        "safetensors",
        "pillow",
        "huggingface_hub",
        "git+https://github.com/huggingface/diffusers.git",
    )
)

MODEL = "black-forest-labs/FLUX.2-klein-4B"
CACHE = "/cache"
vol = modal.Volume.from_name("mindlock-hf-cache", create_if_missing=True)

STYLE = (
    "mndlck style, oil-painting character portrait, head-and-shoulders, chiaroscuro "
    "candle-light, desaturated muted palette, 19th-century asylum, weathered painterly "
    "brushwork, dark vignette background, somber, cinematic"
)

def _stable_seed(slug: str) -> int:
    return 100 + (sum(ord(c) for c in slug) % 100000)


@app.function(gpu="L4", image=image, volumes={CACHE: vol}, timeout=1800)
def generate(prompts: dict) -> dict:
    """prompts: {slug: subject_prompt}. The shared STYLE anchor is prepended here so the whole
    roster stays one cohesive painterly cast. Returns {slug: png-bytes}."""
    import io
    import os

    import torch

    os.environ["HF_HOME"] = CACHE
    from diffusers import Flux2KleinPipeline

    pipe = Flux2KleinPipeline.from_pretrained(MODEL, torch_dtype=torch.bfloat16, cache_dir=CACHE)
    pipe.enable_model_cpu_offload()

    out = {}
    for slug, desc in prompts.items():
        prompt = f"{STYLE}. {desc}"
        img = pipe(
            prompt=prompt,
            height=1024,
            width=1024,
            guidance_scale=1.0,
            num_inference_steps=6,
            generator=torch.Generator("cpu").manual_seed(_stable_seed(slug)),
        ).images[0]
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out[slug] = buf.getvalue()
        print(f"rendered {slug} ({len(out[slug])} bytes)")
    return out


@app.local_entrypoint()
def main(slug: str = ""):
    """Render portraits for roster members missing one (or just --slug X). Writes the PNG into
    each member's sprite dir and flips its portrait flag."""
    import os
    import sys

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(root, "src"))
    from mindlock import roster

    if slug:
        e = roster.load_entry(slug)
        todo = [e] if e else []
    else:
        todo = roster.pending("portrait")
    if not todo:
        print("no pending portraits — roster portraits are up to date.")
        return

    # Lead with an explicit sex + age so the portrait's gender matches the character's (the
    # subject prompt alone — "Kaelin ... his gaze" — let FLUX guess wrong and render a woman).
    def _subject(e):
        sex = "man" if str(e.get("gender", "")).lower() == "male" else "woman"
        age = e.get("age") or ""
        lead = f"a {age}-year-old {sex}".replace("a -year-old", "a")
        return f"{lead}. {e['portrait_prompt']}"

    prompts = {e["slug"]: _subject(e) for e in todo}
    print(f"rendering {len(prompts)} portrait(s): {', '.join(prompts)}")
    for s, data in generate.remote(prompts).items():
        path = roster.portrait_path(s)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        roster.mark(s, "portrait", True)
        print(f"wrote {os.path.relpath(path, root)} ({len(data)} bytes) ✓")
