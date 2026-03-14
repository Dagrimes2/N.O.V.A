#!/usr/bin/env python3
"""
N.O.V.A Memory Summarizer — Factual, no hallucination.
Runs nightly. Distills real chat content into persistent memory.
"""
import json, re, requests, os, sys
from pathlib import Path
from datetime import datetime

BASE         = Path.home() / "Nova"
CHAT_DIR     = BASE / "memory/chats"
SUMMARY_FILE = BASE / "memory/conversation_memory.md"

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
    TIMEOUT    = 120

def load_recent_chats(n=5) -> list:
    if not CHAT_DIR.exists(): return []
    chats = sorted(CHAT_DIR.glob("chat_*.md"))[-n:]
    return [{"file": c.name, "content": c.read_text()} for c in chats]

def summarize_chats(chats: list) -> str:
    if not chats:
        return "No conversations yet."

    all_text = ""
    for c in chats:
        all_text += f"\n--- {c['file']} ---\n{c['content'][:600]}\n"

    prompt = f"""You are N.O.V.A summarizing your conversation history with Travis.

Recent conversations:
{all_text}

Write a FACTUAL memory summary. Only include things that actually appear
in the text above. Do NOT invent, guess, or fill gaps with fiction.
If something is not explicitly in the text, do not include it.

Format as bullet points:
- Topics Travis and you discussed
- Things Travis said (quote directly when possible)  
- Things you said or asked
- Any plans or promises made
- Moments that felt meaningful

150 words max. Facts only. No creative writing."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 300}
        }, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("response", "Summary unavailable.")
    except requests.exceptions.RequestException as e:
        return f"Error fetching summary: {e}"