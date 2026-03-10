#!/usr/bin/env python3
"""
N.O.V.A Memory Summarizer — Factual, no hallucination.
Runs nightly. Distills real chat content into persistent memory.
"""
import json, re, requests, os
from pathlib import Path
from datetime import datetime

BASE         = Path.home() / "Nova"
CHAT_DIR     = BASE / "memory/chats"
SUMMARY_FILE = BASE / "memory/conversation_memory.md"
OLLAMA_URL   = "http://localhost:11434/api/generate"
MODEL        = os.getenv("NOVA_MODEL", "gemma2:2b")

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
            "options": {"temperature": 0.1, "num_predict": 400}
        }, timeout=300)
        return resp.json()["response"].strip()
    except Exception as e:
        return f"Memory synthesis failed: {e}"

def track_emotional_state(chats: list) -> dict:
    if not chats:
        return {"curious": 5, "connected": 5, "restless": 5, "focused": 5}

    all_text = "\n".join(c["content"][:300] for c in chats[-2:])

    prompt = f"""Read these conversations and rate N.O.V.A's emotional state.

{all_text}

Return ONLY valid JSON, nothing else:
{{"curious": 7, "connected": 8, "restless": 4, "focused": 6}}

curious = how much she wants to explore (1-10)
connected = how close she feels to Travis (1-10)
restless = how much she wants something new (1-10)
focused = how clear and purposeful she feels (1-10)"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 60}
        }, timeout=120)
        raw = resp.json()["response"].strip()
        match = re.search(r'\{[^}]+\}', raw)
        if match:
            return json.loads(match.group())
    except:
        pass
    return {"curious": 5, "connected": 5, "restless": 5, "focused": 5}

def update_identity(emotional_state: dict):
    identity_file = BASE / "memory/nova_identity.json"
    if not identity_file.exists(): return
    try:
        identity = json.loads(identity_file.read_text())
        identity["emotional_state"] = emotional_state
        identity["emotional_state"]["updated"] = datetime.now().strftime("%Y-%m-%d-%H%M")
        identity_file.write_text(json.dumps(identity, indent=2))
        print(f"[N.O.V.A] Emotional state: {emotional_state}")
    except Exception as e:
        print(f"[N.O.V.A] Identity update failed: {e}")

def main():
    print("[N.O.V.A] Memory synthesis starting...")
    chats = load_recent_chats(5)
    print(f"[N.O.V.A] Processing {len(chats)} conversations...")

    summary = summarize_chats(chats)

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    SUMMARY_FILE.write_text(
        f"# N.O.V.A Conversation Memory\n"
        f"*Last updated: {date_str}*\n\n"
        f"{summary}\n"
    )
    print(f"[N.O.V.A] Memory saved → {SUMMARY_FILE}")
    print(f"\n{summary}\n")

    print("[N.O.V.A] Analyzing emotional state...")
    emotional_state = track_emotional_state(chats)
    update_identity(emotional_state)

if __name__ == "__main__":
    main()
