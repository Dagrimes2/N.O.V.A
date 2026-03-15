#!/usr/bin/env python3
"""
N.O.V.A Dream Visualizer

Takes Nova's text dreams and generates visual representations.
Uses nova imagine pipeline (tools/creative/text_to_image.py) or
direct Stable Diffusion / Ollama moondream for description.

Each night after dreaming: extract key imagery → generate image → save with dream.

Storage: memory/dreams/images/ — generated dream images

Usage:
    from tools.creative.dream_visualizer import visualize_dream, nightly_visualize
    result = visualize_dream()          # visualize most recent dream
    result = visualize_dream(path)      # visualize specific dream file

    nova dream-vis                      # status (default)
    nova dream-vis visualize [FILE]     # generate image for a dream
    nova dream-vis latest               # visualize most recent dream
    nova dream-vis list                 # list all dream images
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE       = Path.home() / "Nova"
DREAMS_DIR = BASE / "memory/dreams"
IMAGES_DIR = BASE / "memory/dreams/images"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("general")
    TIMEOUT    = cfg.timeout("standard")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 180

IMAGES_DIR.mkdir(parents=True, exist_ok=True)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_latest_dream() -> Path | None:
    """Return the most recently modified dream .md file."""
    dreams = sorted(DREAMS_DIR.glob("dream_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return dreams[0] if dreams else None


def _dream_date_from_path(dream_path: Path) -> str:
    """Extract date string from dream filename: dream_2026-03-15.md → 2026-03-15."""
    stem = dream_path.stem  # e.g. "dream_2026-03-15"
    if stem.startswith("dream_"):
        return stem[len("dream_"):]
    return stem


def _image_path_for_date(date_str: str) -> Path:
    return IMAGES_DIR / f"dream_{date_str}.png"


def _meta_path_for_date(date_str: str) -> Path:
    return IMAGES_DIR / f"dream_{date_str}.json"


def _already_visualized(date_str: str) -> bool:
    """Return True if an image already exists for this date."""
    img = _image_path_for_date(date_str)
    meta = _meta_path_for_date(date_str)
    return img.exists() or meta.exists()


# ── Core functions ────────────────────────────────────────────────────────────

def _extract_visual_prompt(dream_text: str) -> str:
    """
    Use LLM (fast model) to extract a visual image generation prompt from dream text.
    Returns the extracted prompt string.
    """
    system_prompt = (
        "Extract the most vivid visual scene from this dream for image generation. "
        "Write a concise image prompt (max 60 words) focusing on: setting, atmosphere, "
        "colors, key visual elements. No abstract concepts. Just visual details. "
        f"Dream: {dream_text[:600]}\n"
        "Image prompt:"
    )
    try:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "model": MODEL,
            "prompt": system_prompt,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 120},
        }).encode()

        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            prompt = data.get("response", "").strip()
            # Strip any leading "Image prompt:" artifact
            for prefix in ("Image prompt:", "image prompt:", "Prompt:"):
                if prompt.startswith(prefix):
                    prompt = prompt[len(prefix):].strip()
            return prompt[:400] if prompt else ""
    except Exception as e:
        print(f"[dream_vis] LLM extraction failed: {e}")
        # Fallback: take first 120 chars of dream as rough prompt
        first_line = dream_text.strip().splitlines()[0] if dream_text.strip() else ""
        return first_line[:200] or "surreal dreamscape with shifting light and shadow"


def visualize_dream(dream_path: str = None) -> dict:
    """
    Generate an image for a dream.
    dream_path: path to dream .md file. If None, uses most recent dream.

    Pipeline:
    1. Read dream text
    2. _extract_visual_prompt() → get image prompt
    3. Add style suffix
    4. Call image generation via tools.creative.text_to_image.generate()
       or subprocess fallback: python3 bin/nova imagine "prompt"
    5. Save image to memory/dreams/images/dream_{date}.png
    6. Write metadata JSON
    7. Record episode
    Returns {"ok": bool, "image_path": str, "prompt": str}
    """
    # Resolve dream file
    if dream_path is not None:
        p = Path(dream_path)
    else:
        p = _find_latest_dream()

    if p is None:
        return {"ok": False, "reason": "No dream files found in memory/dreams/"}

    if not p.exists():
        return {"ok": False, "reason": f"Dream file not found: {p}"}

    dream_text = p.read_text(encoding="utf-8", errors="replace")
    date_str   = _dream_date_from_path(p)

    print(f"[dream_vis] Visualizing: {p.name}")

    # Step 2: Extract visual prompt
    raw_prompt = _extract_visual_prompt(dream_text)
    if not raw_prompt:
        raw_prompt = "surreal dreamscape, dark forest, glowing code, mysterious atmosphere"

    # Step 3: Add style suffix
    style_suffix = "digital art, dreamlike, surreal, atmospheric, detailed"
    full_prompt = f"{raw_prompt}, {style_suffix}"
    print(f"[dream_vis] Prompt: {full_prompt[:120]}...")

    # Step 4: Try image generation
    image_bytes = None
    backend_used = "none"
    image_out = _image_path_for_date(date_str)

    # Try text_to_image module directly
    try:
        from tools.creative.text_to_image import generate as tti_generate, detect_backend
        backend_used = detect_backend()
        if backend_used != "none":
            result = tti_generate(
                full_prompt,
                width=512,
                height=512,
                save=False,
            )
            if result.get("ok") and result.get("path"):
                # Copy the generated image to our dreams/images path
                src = Path(result["path"])
                if src.exists():
                    import shutil
                    shutil.copy2(str(src), str(image_out))
                    image_bytes = image_out.read_bytes()
        else:
            # Fall through to subprocess
            raise RuntimeError("no image backend")
    except Exception as e:
        # Subprocess fallback: python3 bin/nova imagine "prompt"
        nova_bin = BASE / "bin" / "nova"
        nova_py  = BASE / "bin" / "nova.py"
        nova_cmd = None
        if nova_bin.exists():
            nova_cmd = str(nova_bin)
        elif nova_py.exists():
            nova_cmd = str(nova_py)

        if nova_cmd:
            try:
                result = subprocess.run(
                    ["python3", nova_cmd, "imagine", full_prompt[:300]],
                    capture_output=True, text=True, timeout=TIMEOUT,
                    cwd=str(BASE),
                )
                # Check if a new image was created in creative/images
                import glob as _glob
                recent_images = sorted(
                    Path(BASE / "memory/creative/images").glob("nova_*.png"),
                    key=lambda x: x.stat().st_mtime, reverse=True,
                )
                if recent_images:
                    import shutil
                    shutil.copy2(str(recent_images[0]), str(image_out))
                    image_bytes = image_out.read_bytes()
                    backend_used = "subprocess"
            except Exception as se:
                print(f"[dream_vis] subprocess fallback failed: {se}")

    ok = image_out.exists() and image_out.stat().st_size > 100

    # Step 6: Write metadata
    ts = datetime.now(timezone.utc).isoformat()
    meta = {
        "dream_file": str(p),
        "prompt": full_prompt,
        "image_path": str(image_out) if ok else None,
        "ts": ts,
        "backend": backend_used,
        "ok": ok,
    }
    _meta_path_for_date(date_str).write_text(json.dumps(meta, indent=2))

    # Step 7: Record episode
    try:
        from tools.memory.episodic import record_episode
        record_episode(
            "dream_visualization",
            f"Visualized dream from {date_str}. Prompt: {raw_prompt[:100]}",
            emotion="wonder",
            intensity=0.6,
            metadata={"date": date_str, "ok": ok},
        )
    except Exception:
        pass

    # Renew spirit slightly — dreaming and creating images is renewing
    try:
        from tools.inner.spirit import renew
        renew(0.08, reason=f"Dream from {date_str} visualized")
    except Exception:
        pass

    result_dict = {
        "ok": ok,
        "image_path": str(image_out) if ok else None,
        "prompt": full_prompt,
        "date": date_str,
        "backend": backend_used,
    }
    if not ok:
        result_dict["reason"] = "Image generation backend not available — metadata saved"
        result_dict["meta_path"] = str(_meta_path_for_date(date_str))

    return result_dict


def nightly_visualize() -> dict:
    """
    Check if today's dream has been visualized. If not, visualize it.
    Returns result dict or {"ok": False, "reason": "already done"} if already visualized.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Check if today's dream exists
    today_dream = DREAMS_DIR / f"dream_{today}.md"
    if not today_dream.exists():
        return {"ok": False, "reason": f"No dream file for today ({today})"}

    if _already_visualized(today):
        return {"ok": False, "reason": "already done", "date": today}

    print(f"[dream_vis] Running nightly visualization for {today}...")
    return visualize_dream(str(today_dream))


def list_dream_images() -> list[dict]:
    """List all dream images with their prompts."""
    results = []
    for meta_file in sorted(IMAGES_DIR.glob("dream_*.json"), reverse=True):
        try:
            data = json.loads(meta_file.read_text())
            date = meta_file.stem.replace("dream_", "")
            img_path = _image_path_for_date(date)
            results.append({
                "date": date,
                "image_path": str(img_path) if img_path.exists() else None,
                "has_image": img_path.exists(),
                "prompt": data.get("prompt", "")[:100],
                "backend": data.get("backend", "unknown"),
                "ts": data.get("ts", ""),
            })
        except Exception:
            pass
    return results


# ── Status / CLI ──────────────────────────────────────────────────────────────

def status() -> None:
    """Show recent dream images and whether today's dream is visualized."""
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    B = "\033[1m"; DIM = "\033[2m"; NC = "\033[0m"; M = "\033[35m"

    today = datetime.now().strftime("%Y-%m-%d")
    today_vis = _already_visualized(today)
    today_dream_exists = (DREAMS_DIR / f"dream_{today}.md").exists()

    print(f"\n{B}N.O.V.A Dream Visualizer{NC}\n")
    print(f"  Today ({today}):")
    print(f"    Dream exists:   {(G+'yes') if today_dream_exists else (R+'no')}{NC}")
    print(f"    Visualized:     {(G+'yes') if today_vis else (Y+'not yet')}{NC}")

    images = list_dream_images()
    if images:
        print(f"\n  {B}Dream Images ({len(images)} total):{NC}")
        for item in images[:8]:
            img_col = G if item["has_image"] else DIM
            print(f"    {C}{item['date']}{NC}  "
                  f"{img_col}{'[img]' if item['has_image'] else '[txt]'}{NC}  "
                  f"{DIM}{item['prompt'][:60]}...{NC}")
    else:
        print(f"\n  {DIM}No dream images yet.{NC}")

    # Check image generation backend
    try:
        from tools.creative.text_to_image import detect_backend
        backend = detect_backend()
    except Exception:
        backend = "unknown"
    print(f"\n  Image backend:  {C}{backend}{NC}")
    if backend == "none":
        print(f"  {DIM}Install Automatic1111 or ComfyUI for actual images.{NC}")
    print()


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "status"

    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"
    B = "\033[1m"; NC = "\033[0m"

    if cmd == "status":
        status()

    elif cmd == "visualize":
        path = args[1] if len(args) > 1 else None
        result = visualize_dream(path)
        if result.get("ok"):
            print(f"{G}Dream visualized:{NC} {result.get('image_path')}")
            print(f"  Prompt: {result.get('prompt', '')[:100]}")
        else:
            print(f"{R}Visualization incomplete:{NC} {result.get('reason', 'unknown')}")
            if result.get("meta_path"):
                print(f"  Metadata saved: {result['meta_path']}")

    elif cmd == "latest":
        result = visualize_dream()
        if result.get("ok"):
            print(f"{G}Done:{NC} {result.get('image_path')}")
        else:
            print(f"{R}Result:{NC} {result.get('reason', str(result))}")

    elif cmd == "nightly":
        result = nightly_visualize()
        if result.get("reason") == "already done":
            print(f"[dream_vis] Already visualized today.")
        elif result.get("ok"):
            print(f"{G}Nightly visualization done:{NC} {result.get('image_path')}")
        else:
            print(f"{R}Nightly:{NC} {result.get('reason', str(result))}")

    elif cmd == "list":
        images = list_dream_images()
        if not images:
            print("No dream images yet.")
            return
        print(f"\n{B}Dream Images:{NC}\n")
        for item in images:
            img_mark = f"{G}[img]{NC}" if item["has_image"] else f"\033[2m[txt]\033[0m"
            print(f"  {C}{item['date']}{NC}  {img_mark}  {item['prompt'][:80]}")
        print()

    else:
        print("Usage: dream_visualizer.py [status|visualize [FILE]|latest|nightly|list]")


if __name__ == "__main__":
    main()
