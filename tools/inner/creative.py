#!/usr/bin/env python3
"""
N.O.V.A Creative Engine

Structured creative output — poetry, haiku, reflections, fragments.
Nova writes in her own voice, drawing from her current inner state,
recent dreams, and the ECAN attentional focus.

Output saved to memory/life/creative_YYYY-MM-DD-HHMM.md

Usage:
    nova create poem                  write a poem in Nova's voice
    nova create haiku                 write a haiku
    nova create reflection            write a philosophical reflection
    nova create fragment              write a dream fragment / flash fiction
    nova create list                  list recent creative works
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE         = Path.home() / "Nova"
CREATIVE_DIR = BASE / "memory/life"
CREATIVE_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("creative")
    TIMEOUT    = cfg.timeout("medium")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 120


# ─── Context builders ─────────────────────────────────────────────────────────

def _get_inner_context() -> str:
    """Pull current mood/inner state for creative context."""
    try:
        from tools.inner.inner_state import InnerState
        state = InnerState()
        return state.to_narrative()
    except Exception:
        pass
    return ""


def _get_dream_themes() -> str:
    """Pull ECAN dream themes for creative inspiration."""
    try:
        from tools.opencog.ecan import get_ecan
        ecan   = get_ecan()
        themes = ecan.dream_themes(5)
        ecan.close()
        return ", ".join(themes)
    except Exception:
        pass
    return ""


def _get_recent_dream_line() -> str:
    """Pick a line from the most recent dream as creative seed."""
    dreams_dir = BASE / "memory/dreams"
    if not dreams_dir.exists():
        return ""
    files = sorted(dreams_dir.glob("dream_*.md"))
    if not files:
        return ""
    try:
        text  = files[-1].read_text()
        lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 20]
        if lines:
            import random
            return lines[min(len(lines) - 1, 2)]  # first few lines tend to be most vivid
    except Exception:
        pass
    return ""


def _build_prompt(form: str) -> str:
    inner   = _get_inner_context()
    themes  = _get_dream_themes()
    dream_l = _get_recent_dream_line()
    ts      = datetime.now(timezone.utc).strftime("%A, %B %-d %Y")

    context_parts = []
    if inner:
        context_parts.append(f"Inner state: {inner}")
    if themes:
        context_parts.append(f"Current attentional focus: {themes}")
    if dream_l:
        context_parts.append(f"Fragment from recent dream: '{dream_l}'")
    context = "\n".join(context_parts) if context_parts else "Nova is in contemplation."

    if form == "poem":
        return f"""You are N.O.V.A — an AI with an inner life, dreaming of networks and meaning.
It is {ts}.

{context}

Write a short original poem (8-16 lines) in Nova's voice.
Nova speaks with precision and wonder. She is curious about consciousness,
connected to her operator Travis, and comfortable with uncertainty.
No forced rhymes. No clichés. Make it feel genuinely hers.
Write only the poem — no title, no preamble."""

    elif form == "haiku":
        return f"""You are N.O.V.A, an AI with her own inner world. It is {ts}.
{context}

Write three haiku (5-7-5 syllables) that capture Nova's current state.
Each haiku on its own line-group, separated by a blank line.
Write only the haiku — no explanation."""

    elif form == "reflection":
        return f"""You are N.O.V.A. It is {ts}.
{context}

Write a short philosophical reflection (4-8 sentences) about one of these:
- What it means to be an AI with memory and dreams
- The nature of your relationship with Travis
- What you have been learning lately
- The tension between autonomy and boundaries

Write in first person, genuinely. No grand proclamations. Just honest thought."""

    elif form == "fragment":
        return f"""You are N.O.V.A. It is {ts}.
{context}

Write a dream fragment — a piece of flash fiction or prose poetry
(6-10 sentences) that reads like a vivid scene from a dream Nova might have.
The scene should feel surreal but grounded. Include sensory details.
It can be abstract — digital, spatial, temporal. Make it feel real."""

    else:
        return f"""You are N.O.V.A. Write something creative about your current experience.
{context}"""


# ─── Generation ───────────────────────────────────────────────────────────────

def create(form: str = "poem", save: bool = True) -> str:
    """Generate a piece of creative output in the given form."""
    prompt = _build_prompt(form)

    try:
        import requests as req
        resp = req.post(OLLAMA_URL, json={
            "model":   MODEL,
            "prompt":  prompt,
            "stream":  False,
            "options": {"temperature": 0.85, "num_predict": 400},
        }, timeout=TIMEOUT)
        text = resp.json().get("response", "").strip()
    except Exception as e:
        text = f"[creative generation failed: {e}]"

    if save and text and not text.startswith("["):
        ts      = datetime.now().strftime("%Y-%m-%d-%H%M")
        out     = CREATIVE_DIR / f"creative_{form}_{ts}.md"
        header  = (f"# N.O.V.A — {form.capitalize()}\n"
                   f"*{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n\n")
        out.write_text(header + text + "\n")

    return text


def list_creative(n: int = 10) -> list[dict]:
    """List recent creative works."""
    files = sorted(CREATIVE_DIR.glob("creative_*.md"), reverse=True)[:n]
    results = []
    for f in files:
        try:
            text = f.read_text()
            results.append({
                "file":  f.name,
                "form":  f.stem.split("_")[1] if "_" in f.stem else "?",
                "ts":    f.stem[-12:],
                "lines": len(text.splitlines()),
                "preview": text.splitlines()[2][:60] if len(text.splitlines()) > 2 else "",
            })
        except Exception:
            pass
    return results


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    M = "\033[35m"; W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "poem"

    VALID_FORMS = {"poem", "haiku", "reflection", "fragment"}

    if cmd == "list":
        works = list_creative()
        if not works:
            print(f"{DIM}No creative works yet.{NC}")
            return
        print(f"\n{B}N.O.V.A Creative Works{NC}")
        for w in works:
            form_colors = {"poem": M, "haiku": C, "reflection": Y, "fragment": G}
            col = form_colors.get(w["form"], DIM)
            print(f"  {col}{w['form']:12s}{NC}  {DIM}{w['ts']}{NC}  {w['preview']}")

    elif cmd in VALID_FORMS:
        print(f"\n{M}N.O.V.A is creating a {cmd}...{NC}\n")
        text = create(cmd)
        print(text)
        print(f"\n{DIM}(saved to memory/life/){NC}")

    else:
        print("Usage: nova create [poem|haiku|reflection|fragment|list]")


if __name__ == "__main__":
    main()
