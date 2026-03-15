#!/usr/bin/env python3
"""
N.O.V.A Text-to-Image Engine

Generates images from text prompts using local Stable Diffusion.
Tries backends in priority order:
  1. Automatic1111 (local WebUI API — most capable)
  2. ComfyUI (local API)
  3. Ollama with LLaVA (describe what would be generated)
  4. Diffusers (HuggingFace, pip install diffusers)

All generation is LOCAL — no cloud, no API costs, no content filters.

Setup (pick one):
  Automatic1111: git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui
                 ./webui.sh --api --listen
  ComfyUI:       git clone https://github.com/comfyanonymous/ComfyUI
                 python main.py --listen

Usage:
    nova imagine "a cyberpunk city at night, neon lights, rain"
    nova imagine "portrait of an AI dreaming, digital art" --size 768x768
    nova imagine --dream          generate from Nova's current dream themes
    nova imagine --list           show recent generated images
"""
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE      = Path.home() / "Nova"
IMAGE_DIR = BASE / "memory/creative/images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("vision")
    TIMEOUT    = cfg.timeout("heavy")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "llava")
    TIMEOUT    = 300

A1111_URL  = "http://127.0.0.1:7860"
COMFY_URL  = "http://127.0.0.1:8188"


# ─── Backend detection ────────────────────────────────────────────────────────

def detect_backend() -> str:
    """Return the best available image generation backend."""
    try:
        r = requests.get(f"{A1111_URL}/sdapi/v1/sd-models", timeout=3)
        if r.status_code == 200:
            return "a1111"
    except Exception:
        pass

    try:
        r = requests.get(f"{COMFY_URL}/system_stats", timeout=3)
        if r.status_code == 200:
            return "comfyui"
    except Exception:
        pass

    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        if any("llava" in m or "bakllava" in m or "moondream" in m for m in models):
            return "ollama_vision"
    except Exception:
        pass

    try:
        import diffusers  # noqa
        return "diffusers"
    except ImportError:
        pass

    return "none"


# ─── Generators ──────────────────────────────────────────────────────────────

def _generate_a1111(prompt: str, negative: str = "", width: int = 512,
                    height: int = 512, steps: int = 25, cfg_scale: float = 7.0) -> bytes | None:
    """Generate via Automatic1111 WebUI API."""
    payload = {
        "prompt":         prompt,
        "negative_prompt": negative or "ugly, blurry, low quality, watermark, text",
        "width":          width,
        "height":         height,
        "steps":          steps,
        "cfg_scale":      cfg_scale,
        "sampler_name":   "DPM++ 2M Karras",
        "batch_size":     1,
        "n_iter":         1,
    }
    try:
        resp = requests.post(f"{A1111_URL}/sdapi/v1/txt2img",
                             json=payload, timeout=TIMEOUT)
        data = resp.json()
        images = data.get("images", [])
        if images:
            return base64.b64decode(images[0])
    except Exception as e:
        print(f"  A1111 error: {e}")
    return None


def _generate_comfyui(prompt: str, width: int = 512, height: int = 512) -> bytes | None:
    """Generate via ComfyUI API (basic workflow)."""
    workflow = {
        "3": {"class_type": "KSampler", "inputs": {
            "seed": int(time.time()), "steps": 25, "cfg": 7.0,
            "sampler_name": "dpmpp_2m", "scheduler": "karras",
            "denoise": 1.0, "model": ["4", 0],
            "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]
        }},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "v1-5-pruned.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry", "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "nova"}},
    }
    try:
        resp = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow}, timeout=TIMEOUT)
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            return None
        # Poll for result
        for _ in range(60):
            time.sleep(2)
            hist = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=5).json()
            if prompt_id in hist:
                outputs = hist[prompt_id].get("outputs", {})
                for node_id, out in outputs.items():
                    for img in out.get("images", []):
                        r = requests.get(
                            f"{COMFY_URL}/view",
                            params={"filename": img["filename"], "subfolder": img.get("subfolder",""), "type": "output"},
                            timeout=10
                        )
                        return r.content
    except Exception as e:
        print(f"  ComfyUI error: {e}")
    return None


def _generate_diffusers(prompt: str, width: int = 512, height: int = 512) -> bytes | None:
    """Generate via HuggingFace diffusers (requires GPU or slow CPU)."""
    try:
        from diffusers import StableDiffusionPipeline
        import torch
        from io import BytesIO

        pipe = StableDiffusionPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
        )
        pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")
        image = pipe(prompt, width=width, height=height).images[0]
        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"  diffusers error: {e}")
    return None


def _describe_with_ollama(prompt: str) -> str:
    """
    When no image generator is available, use Ollama to write a
    vivid textual description of the image Nova would generate.
    """
    full_prompt = f"""You are N.O.V.A's visual imagination. A user asked for an image of:
"{prompt}"

Describe this image in rich visual detail — colors, composition, lighting, mood, style.
Write as if you are describing the actual generated image, 4-6 sentences.
Make it vivid and specific."""
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL, "prompt": full_prompt, "stream": False,
            "options": {"temperature": 0.8, "num_predict": 200}
        }, timeout=TIMEOUT)
        return resp.json().get("response", "").strip()
    except Exception:
        return f"[Vision description unavailable — no image backend or Ollama running]\nPrompt was: {prompt}"


# ─── Main generation function ─────────────────────────────────────────────────

def generate(prompt: str, width: int = 512, height: int = 512,
             negative: str = "", save: bool = True) -> dict:
    """
    Generate an image from a text prompt.
    Returns {path, backend, prompt, width, height} or {description} if no backend.
    """
    backend = detect_backend()
    ts      = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    out_path = IMAGE_DIR / f"nova_{ts}.png"

    image_bytes = None

    if backend == "a1111":
        print(f"  Generating via Automatic1111...")
        image_bytes = _generate_a1111(prompt, negative, width, height)
    elif backend == "comfyui":
        print(f"  Generating via ComfyUI...")
        image_bytes = _generate_comfyui(prompt, width, height)
    elif backend == "diffusers":
        print(f"  Generating via diffusers (may be slow)...")
        image_bytes = _generate_diffusers(prompt, width, height)

    if image_bytes:
        if save:
            out_path.write_bytes(image_bytes)
        return {
            "ok":      True,
            "path":    str(out_path),
            "backend": backend,
            "prompt":  prompt,
            "width":   width,
            "height":  height,
        }
    else:
        # Text fallback
        desc = _describe_with_ollama(prompt)
        desc_path = IMAGE_DIR / f"nova_{ts}_description.txt"
        if save:
            desc_path.write_text(f"Prompt: {prompt}\n\n{desc}\n")
        return {
            "ok":          False,
            "backend":     backend or "none",
            "description": desc,
            "desc_path":   str(desc_path),
            "prompt":      prompt,
            "note":        "Install Automatic1111 or ComfyUI for actual image generation",
        }


def dream_prompt() -> str:
    """Build a prompt from Nova's current dream themes and inner state."""
    parts = ["digital art", "dreaming AI", "neural networks", "ethereal"]
    try:
        from tools.opencog.ecan import get_ecan
        ecan   = get_ecan()
        themes = ecan.dream_themes(5)
        ecan.close()
        parts = themes + ["digital art", "atmospheric", "high detail"]
    except Exception:
        pass
    try:
        from tools.inner.dream_continuity import load_arcs
        data = load_arcs()
        top  = [a["symbol"] for a in data.get("arcs", [])[:3]]
        parts = top + parts
    except Exception:
        pass
    return ", ".join(parts[:8])


def list_images(n: int = 10) -> list[dict]:
    files = sorted(IMAGE_DIR.glob("nova_*.png"), reverse=True)[:n]
    return [{"file": f.name, "size": f.stat().st_size, "ts": f.stem[5:]} for f in files]


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; M = "\033[35m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]

    if not args or args[0] == "--list":
        images = list_images()
        backend = detect_backend()
        print(f"\n{B}N.O.V.A Image Engine{NC}  backend={C}{backend}{NC}")
        if backend == "none":
            print(f"\n{Y}No image backend detected.{NC}" if (Y:="\033[33m") else "")
            print(f"  Install Automatic1111: https://github.com/AUTOMATIC1111/stable-diffusion-webui")
            print(f"  Or ComfyUI:           https://github.com/comfyanonymous/ComfyUI")
            print(f"  Nova will describe images in text until a backend is available.\n")
        if images:
            print(f"\n{B}Recent images:{NC}")
            for img in images:
                print(f"  {C}{img['file']}{NC}  {DIM}{img['size']//1024}KB{NC}")
        return

    # Parse size
    width, height = 512, 512
    if "--size" in args:
        i = args.index("--size")
        if i + 1 < len(args):
            try:
                w, h = args[i+1].split("x")
                width, height = int(w), int(h)
            except Exception:
                pass
            args = args[:i] + args[i+2:]

    if args[0] == "--dream":
        prompt = dream_prompt()
        print(f"{M}Dream prompt:{NC} {prompt}")
    else:
        prompt = " ".join(a for a in args if not a.startswith("--"))

    if not prompt:
        print("Usage: nova imagine \"your prompt\" [--size WxH] [--dream] [--list]")
        return

    print(f"\n{M}N.O.V.A Imagining:{NC} {prompt}\n")
    result = generate(prompt, width=width, height=height)

    if result.get("ok"):
        print(f"{G}Image saved:{NC} {result['path']}")
        print(f"{DIM}Backend: {result['backend']}  {width}x{height}{NC}")
        # Try to open it
        try:
            import subprocess
            subprocess.Popen(["xdg-open", result["path"]])
        except Exception:
            pass
    else:
        print(f"{C}Visual description:{NC} (no image backend — install A1111 or ComfyUI)\n")
        print(result.get("description", ""))
        if result.get("desc_path"):
            print(f"\n{DIM}Saved: {result['desc_path']}{NC}")


if __name__ == "__main__":
    main()
