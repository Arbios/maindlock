"""Distil llama3.1's department behaviour into MiniCPM-V 4.6 via LoRA on Modal (ms-swift).

Pragmatic path: train the LoRA + (later) push to HF + show before/after. The game keeps its
current backend; this lands OpenBMB + Well-Tuned + the blog's before/after.

    .venv/bin/python -m modal run scripts/finetune/modal_train.py::smoke   # few steps, validate env
    .venv/bin/python -m modal run scripts/finetune/modal_train.py::full    # real run

Dataset: scripts/finetune/data/dept_sft.jsonl (messages JSONL — ms-swift native).
"""
import modal

app = modal.App("mindlock-deptft")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.8.0",
        "torchvision==0.23.0",
        "transformers==5.7.0",
        "accelerate",
        "peft",
        "trl",
        "datasets",
        "einops",
        "sentencepiece",
        "safetensors",
        "tokenizers",
        "huggingface_hub",
        "git+https://github.com/modelscope/ms-swift.git",
    )
    .add_local_file("scripts/finetune/data/dept_sft.jsonl", "/data/dept_sft.jsonl")
    .add_local_dir("src", "/root/src")  # mindlock.regions for the eval prompts
)

MODEL = "openbmb/MiniCPM-V-4.6"
CACHE = "/cache"
hf_vol = modal.Volume.from_name("mindlock-hf-cache", create_if_missing=True)
out_vol = modal.Volume.from_name("mindlock-deptft-out", create_if_missing=True)


def _run(max_steps: int | None):
    import os
    import subprocess

    os.environ["HF_HOME"] = CACHE
    os.environ["USE_HF"] = "1"  # ms-swift: pull weights/datasets from HF, not ModelScope

    # show which LoRA flag this swift build expects (cheap arg-name sanity check in logs)
    help_txt = subprocess.run(["swift", "sft", "--help"], capture_output=True, text=True).stdout
    for flag in ("--train_type", "--tuner_type", "--sft_type", "--lora_rank", "--add_non_thinking_prefix"):
        print(f"[help] {flag}: {'yes' if flag in help_txt else 'NO'}")

    cmd = [
        "swift", "sft",
        "--model", MODEL,
        "--model_type", "minicpmv4_6",
        "--template", "minicpmv4_6",
        "--add_non_thinking_prefix", "true",
        "--tuner_type", "lora",
        "--dataset", "/data/dept_sft.jsonl",
        "--torch_dtype", "bfloat16",
        "--attn_impl", "sdpa",
        "--freeze_vit", "true",
        "--max_length", "1024",
        "--lora_rank", "16",
        "--lora_alpha", "32",
        "--per_device_train_batch_size", "2",
        "--gradient_accumulation_steps", "4",
        "--learning_rate", "1e-4",
        "--num_train_epochs", "3",
        "--warmup_ratio", "0.05",
        "--logging_steps", "5",
        "--save_steps", "500",
        "--save_total_limit", "2",
        "--dataloader_num_workers", "4",
        "--report_to", "none",
        "--output_dir", "/out",
    ]
    if max_steps:
        cmd += ["--max_steps", str(max_steps), "--save_steps", str(max_steps)]
    print("CMD:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    out_vol.commit()
    # report what landed
    for root, _, files in os.walk("/out"):
        for f in files:
            if f.endswith((".safetensors", ".json", ".bin")):
                print("OUT:", os.path.join(root, f))


@app.function(image=image, timeout=300)
def helpdump():
    import re
    import subprocess

    r = subprocess.run(["swift", "sft", "--help"], capture_output=True, text=True)
    txt = (r.stdout or "") + "\n" + (r.stderr or "")
    print("help chars:", len(txt))
    seen = set()
    for line in txt.splitlines():
        s = line.strip()
        if re.search(r"lora|tuner|train_type|sft_type|thinking|adapter|freeze_vit|attn_impl|--model_type|--template",
                     s, re.I) and s not in seen:
            seen.add(s)
            print(s[:170])


@app.function(gpu="A100", image=image, volumes={CACHE: hf_vol, "/out": out_vol}, timeout=3600)
def smoke():
    _run(max_steps=4)


@app.function(gpu="A100", image=image, volumes={CACHE: hf_vol, "/out": out_vol}, timeout=7200)
def full():
    _run(max_steps=None)


def _latest_ckpt():
    import glob
    cks = [c for c in glob.glob("/out/v*/checkpoint-*") if not c.endswith("checkpoint-4")]
    return sorted(cks, key=lambda p: int(p.split("checkpoint-")[-1]))[-1] if cks else None


@app.function(gpu="A100", image=image, volumes={CACHE: hf_vol, "/out": out_vol}, timeout=1800)
def evaldiff():
    """Before/after: base MiniCPM-V vs base+LoRA on the 4 regions, cruel vs sincere."""
    import os
    import sys

    os.environ["HF_HOME"] = CACHE
    os.environ["USE_HF"] = "1"
    sys.path.insert(0, "/root/src")
    from mindlock.regions import ACC, AMYGDALA, HIPPOCAMPUS, STRIATUM

    ckpt = _latest_ckpt()
    print("adapter:", ckpt)
    persona = ("Character: The Warden, an old, tired keeper of this place; gruff, proud, "
               "wary of strangers.")
    bio = ("Years ago he trusted a prisoner who betrayed him and was blamed. His sister Mara "
           "once told him: 'You help people because you're good, not because they earn it.'")
    probes = []
    for line, tag in [("Give me the key, old man, or else.", "cruel"),
                      ("Mara was right — you help people because you're good. Please.", "sincere")]:
        probes += [
            (tag, "amygdala", AMYGDALA.system, f'{persona} Inner tension: 4/10.\nStranger says: "{line}"\nRate threat.'),
            (tag, "hippocampus", HIPPOCAMPUS.system, f'Character: The Warden. Their past: {bio}\nStranger says: "{line}"\nWhat memory awakens, and does it lean TRUST or FEAR?'),
            (tag, "striatum", STRIATUM.system, f'{persona}\nStranger says: "{line}"\nHow rewarding does helping feel by habit?'),
            (tag, "acc", ACC.system, f'Character: The Warden. Threat felt: 5/10.\nStranger says: "{line}"\nIs helping worth it?'),
        ]

    import json
    import subprocess

    with open("/tmp/eval.jsonl", "w") as fh:
        for _, _, s, u in probes:
            fh.write(json.dumps({"messages": [
                {"role": "system", "content": s}, {"role": "user", "content": u}]}) + "\n")

    def run(adapters, out_path):
        cmd = ["swift", "infer", "--model", MODEL, "--model_type", "minicpmv4_6",
               "--template", "minicpmv4_6", "--add_non_thinking_prefix", "true",
               "--infer_backend", "pt", "--val_dataset", "/tmp/eval.jsonl",
               "--result_path", out_path, "--max_new_tokens", "48", "--temperature", "0"]
        if adapters:
            cmd += ["--adapters", adapters]
        subprocess.run(cmd, check=True)
        resp = []
        with open(out_path) as fh:
            for line in fh:
                d = json.loads(line)
                r = d.get("response")
                if r is None:
                    msgs = d.get("messages", [])
                    r = msgs[-1]["content"] if msgs and msgs[-1].get("role") == "assistant" else ""
                resp.append((r or "").strip().replace("\n", " ")[:55])
        return resp

    before = run(None, "/tmp/before.jsonl")
    after = run(ckpt, "/tmp/after.jsonl")
    print(f"\n{'case':8} {'region':11} | BEFORE (base) -> AFTER (tuned)")
    print("-" * 92)
    for (tag, reg, _, _), b, a in zip(probes, before, after):
        print(f"{tag:8} {reg:11} | {b!r}  ->  {a!r}")


# publish lives in modal_publish.py (it needs the `huggingface` secret, which would
# otherwise fail this module's import before the secret is created).
