"""Publish the trained department LoRA to the Hugging Face Hub (Well-Tuned + OpenBMB).

Needs a Modal secret named `huggingface` with HF_TOKEN (write). Create it first:
    .venv/bin/modal secret create huggingface HF_TOKEN=hf_xxx
Then:
    .venv/bin/python -m modal run scripts/finetune/modal_publish.py
"""
import modal

app = modal.App("mindlock-deptft-publish")
image = modal.Image.debian_slim(python_version="3.11").pip_install("huggingface_hub")
out_vol = modal.Volume.from_name("mindlock-deptft-out")


def _latest_ckpt():
    import glob

    cks = [c for c in glob.glob("/out/v*/checkpoint-*") if not c.endswith("checkpoint-4")]
    return sorted(cks, key=lambda p: int(p.split("checkpoint-")[-1]))[-1] if cks else None


@app.function(image=image, volumes={"/out": out_vol}, timeout=1800,
              secrets=[modal.Secret.from_name("huggingface")])
def publish(repo: str = ""):
    import os

    from huggingface_hub import HfApi, whoami

    token = os.environ["HF_TOKEN"]
    user = whoami(token=token)["name"]
    repo_id = repo or f"{user}/mindlock-minicpmv46-departments-lora"
    ckpt = _latest_ckpt()
    print("publishing", ckpt, "->", repo_id)
    api = HfApi(token=token)
    api.create_repo(repo_id, exist_ok=True, private=False, repo_type="model")
    api.upload_folder(folder_path=ckpt, repo_id=repo_id)
    print("done:", f"https://huggingface.co/{repo_id}")
