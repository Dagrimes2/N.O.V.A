#!/usr/bin/env python3
"""
N.O.V.A Model Router

Routes prompts to the best model for the task:
  code       → codellama:7b-instruct  (writing/reviewing Python)
  fast       → gemma2:2b              (quick decisions, classifications)
  creative   → dolphin-mistral        (letters, journal, dreams, stories)
  reasoning  → mistral:7b-instruct-q4_K_M  (analysis, planning)
  vision     → moondream:latest       (image description)
  default    → dolphin-mistral        (fallback for anything else)

Falls back to dolphin-mistral if the assigned model is unavailable.
"""
import base64
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE         = Path.home() / "Nova"
STATS_FILE   = BASE / "memory/router_stats.json"
FALLBACK     = "dolphin-mistral"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    TIMEOUT    = cfg.timeout("heavy")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    TIMEOUT    = 300

TASK_MODELS: dict[str, str] = {
    "code":      "codellama:7b-instruct",
    "fast":      "gemma2:2b",
    "creative":  "dolphin-mistral",
    "reasoning": "mistral:7b-instruct-q4_K_M",
    "vision":    "moondream:latest",
    "default":   "dolphin-mistral",
}

# ── Stats helpers ─────────────────────────────────────────────────────────────

def _load_stats() -> dict:
    if STATS_FILE.exists():
        try:
            return json.loads(STATS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_stats(stats: dict):
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, indent=2))


def _record(model: str, elapsed_ms: float, success: bool):
    stats = _load_stats()
    if model not in stats:
        stats[model] = {"calls": 0, "successes": 0, "avg_ms": 0.0}
    entry   = stats[model]
    prev    = entry["calls"]
    entry["calls"] += 1
    if success:
        entry["successes"] += 1
    # rolling average
    entry["avg_ms"] = round(
        (entry["avg_ms"] * prev + elapsed_ms) / entry["calls"], 1
    )
    _save_stats(stats)


# ── Ollama helpers ────────────────────────────────────────────────────────────

def _available_models() -> list[str]:
    """Query /api/tags to get running models. Returns empty list on failure."""
    tags_url = OLLAMA_URL.replace("/api/generate", "/api/tags")
    try:
        req = urllib.request.Request(
            tags_url,
            headers={"User-Agent": "NOVA-Router/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _ollama_generate(model: str, prompt: str, temperature: float,
                     max_tokens: int, images: list[str] = None) -> str:
    """
    Low-level call to Ollama /api/generate.
    Returns response text or raises on failure.
    """
    payload: dict = {
        "model":   model,
        "prompt":  prompt,
        "stream":  False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if images:
        payload["images"] = images

    body = json.dumps(payload).encode()
    req  = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent":   "NOVA-Router/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read())
    return data.get("response", "").strip()


# ── Public API ────────────────────────────────────────────────────────────────

def get_model(task_type: str = "default") -> str:
    """Return the model name for this task type."""
    return TASK_MODELS.get(task_type, TASK_MODELS["default"])


def generate(
    prompt: str,
    task_type: str = "default",
    temperature: float = 0.85,
    max_tokens: int = 400,
    image_path: str = None,
) -> str:
    """
    Generate text using the appropriate model.
    - Looks up model via get_model(task_type)
    - For vision tasks with image_path: reads image as base64, sends to moondream
      using Ollama's multimodal format: {"images": [base64_str]}
    - Records timing and success in router_stats.json
    - On failure: retries once with dolphin-mistral fallback
    - Returns response text or "" on failure
    """
    model  = get_model(task_type)
    images = None

    if task_type == "vision" and image_path:
        try:
            images = [base64.b64encode(Path(image_path).read_bytes()).decode()]
        except Exception:
            return ""

    t0 = time.time()
    try:
        text    = _ollama_generate(model, prompt, temperature, max_tokens, images)
        elapsed = (time.time() - t0) * 1000
        _record(model, elapsed, True)
        return text
    except Exception:
        _record(model, (time.time() - t0) * 1000, False)

    # Fallback — retry once with dolphin-mistral
    if model != FALLBACK:
        t1 = time.time()
        try:
            text    = _ollama_generate(FALLBACK, prompt, temperature, max_tokens)
            elapsed = (time.time() - t1) * 1000
            _record(FALLBACK, elapsed, True)
            return text
        except Exception:
            _record(FALLBACK, (time.time() - t1) * 1000, False)

    return ""


def generate_code(prompt: str, language: str = "python") -> str:
    """
    Specialized code generation. Wraps generate() with task_type="code".
    Adds language-specific system context to prompt.
    Strips markdown code fences from response (```python ... ```) before returning.
    """
    context = (
        f"You are an expert {language} programmer. "
        f"Write clean, well-commented {language} code. "
        "Return only the code itself, no explanation outside the code.\n\n"
    )
    full_prompt = context + prompt
    result = generate(full_prompt, task_type="code", temperature=0.2, max_tokens=800)

    # Strip markdown code fences
    lines = result.splitlines()
    cleaned: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def describe_image(
    image_path: str,
    question: str = "Describe this image in detail.",
) -> str:
    """Use moondream to describe an image. Returns description string."""
    return generate(question, task_type="vision", image_path=image_path,
                    temperature=0.3, max_tokens=300)


def status() -> None:
    """Print model routing table and usage stats."""
    G = "\033[32m"; C = "\033[36m"; Y = "\033[33m"; R = "\033[31m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    available = _available_models()
    stats     = _load_stats()

    print(f"\n{B}N.O.V.A Model Router{NC}")
    print(f"\n  {'Task':<12}  {'Model':<38}  {'Available'}")
    print(f"  {'-'*12}  {'-'*38}  {'-'*9}")

    for task, model in TASK_MODELS.items():
        # Partial match: moondream:latest vs moondream
        is_avail = any(model.split(":")[0] in a for a in available) if available else None
        if is_avail is None:
            avail_str = f"{DIM}unknown{NC}"
        elif is_avail:
            avail_str = f"{G}yes{NC}"
        else:
            avail_str = f"{R}no{NC}"
        print(f"  {C}{task:<12}{NC}  {model:<38}  {avail_str}")

    if stats:
        print(f"\n  {B}Usage Stats:{NC}")
        print(f"  {'Model':<38}  {'Calls':>6}  {'Success':>8}  {'Avg ms':>8}")
        print(f"  {'-'*38}  {'-'*6}  {'-'*8}  {'-'*8}")
        for model_name, s in sorted(stats.items()):
            calls    = s.get("calls", 0)
            succ     = s.get("successes", 0)
            avg      = s.get("avg_ms", 0.0)
            pct      = f"{succ/calls*100:.0f}%" if calls else "—"
            col      = G if (calls and succ / calls > 0.8) else (Y if calls else DIM)
            print(f"  {model_name:<38}  {calls:>6}  {col}{pct:>8}{NC}  {avg:>8.0f}")
    print()


def main():
    import argparse

    p   = argparse.ArgumentParser(description="N.O.V.A Model Router")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show routing table and stats (default)")
    sub.add_parser("models", help="List available Ollama models")

    t = sub.add_parser("test", help="Test a task type")
    t.add_argument("task_type", help="e.g. code, creative, reasoning, fast, vision")
    t.add_argument("prompt",    nargs="+")
    t.add_argument("--image",   default=None, dest="image_path",
                   help="Image path for vision tasks")

    args = p.parse_args()

    G = "\033[32m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"; R = "\033[31m"

    if args.cmd in (None, "status"):
        status()

    elif args.cmd == "models":
        models = _available_models()
        if models:
            print(f"\n{B}Available Ollama models:{NC}")
            for m in models:
                print(f"  {G}•{NC} {m}")
        else:
            print(f"{R}Could not reach Ollama or no models loaded.{NC}")
        print()

    elif args.cmd == "test":
        prompt = " ".join(args.prompt)
        task   = args.task_type
        model  = get_model(task)
        print(f"\n{B}Testing:{NC} task={task}  model={model}")
        print(f"{DIM}Prompt: {prompt[:80]}{NC}\n")
        if task == "code":
            result = generate_code(prompt)
        else:
            result = generate(prompt, task_type=task,
                              image_path=args.image_path)
        if result:
            print(result)
        else:
            print(f"{R}No response.{NC}")
        print()


if __name__ == "__main__":
    main()
