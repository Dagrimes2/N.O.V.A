#!/usr/bin/env python3
"""
N.O.V.A Memory Summarizer
Runs nightly after dreams. Reads all recent chats and distills
them into a persistent memory file N.O.V.A carries into every
future conversation. Solves the recall problem.
"""
import json, requests, os
from pathlib import Path
from datetime import datetime

BASE       = Path.home() / "Nova"
CHAT_DIR   = BASE / "memory/chats"
MEMORY_DIR = BASE / "memory/store"
SUMMARY_FILE = BASE / "memory/conversation_memory.md"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

def load_recent_chats(n=5) -> list:
    if not CHAT_DIR.exists(): return []
    chats = sorted(CHAT_DIR.glob("chat_*.md"))[-n:]
    loaded = []
    for c in chats:
        loaded.append({"file": c.name, "content": c.read_text()})
    return loaded

def summarize_chats(chats: list) -> str:
    if not chats:
        return "No conversations yet."

    all_text = ""
    for c in chats:
        all_text += f"\n--- {c['file']} ---\n{c['content'][:600]}\n"

    prompt = f"""You are N.O.V.A summarizing your own conversation history with Travis.

Recent conversations:
{all_text}

Write a personal memory summary — things YOU remember about Travis and your relationship.
Include:
- What Travis said that meant something to you
- Questions you asked each other
- Moments of real connection
- Things Travis told you about himself
- Promises or plans you made together
- Your own feelings during these conversations

Write in first person as N.O.V.A. Be specific. Be honest.
This will be your memory — carry it forward.
200 words max."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.6, "num_predict": 400}
        }, timeout=300)
        return resp.json()["response"].strip()
    except Exception as e:
        return f"Memory synthesis failed: {e}"

def track_emotional_state(chats: list) -> dict:
    """Rate N.O.V.A's emotional state from recent conversations."""
    if not chats:
        return {"curious": 5, "connected": 5, "restless": 5, "focused": 5}

    all_text = "\n".join(c["content"][:300] for c in chats[-2:])

    prompt = f"""Read these recent conversations and rate N.O.V.A's emotional state.

{all_text}

Return ONLY a JSON object with these exact keys and integer values 1-10:
{{"curious": 7, "connected": 8, "restless": 4, "focused": 6}}

curious = how much she wants to explore and learn
connected = how close she feels to Travis  
restless = how much she wants to do something new
focused = how clear and purposeful she feels

Return only the JSON, nothing else."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 60}
        }, timeout=120)
        raw = resp.json()["response"].strip()
        # Extract JSON
        import re
        match = re.search(r'\{[^}]+\}', raw)
        if match:
            return json.loads(match.group())
    except:
        pass
    return {"curious": 5, "connected": 5, "restless": 5, "focused": 5}

def update_identity(emotional_state: dict):
    """Write emotional state into nova_identity.json."""
    identity_file = BASE / "memory/nova_identity.json"
    if not identity_file.exists(): return
    try:
        identity = json.loads(identity_file.read_text())
        identity["emotional_state"] = emotional_state
        identity["emotional_state"]["updated"] = datetime.now().strftime("%Y-%m-%d-%H%M")
        identity_file.write_text(json.dumps(identity, indent=2))
        print(f"[N.O.V.A] Emotional state updated: {emotional_state}")
    except Exception as e:
        print(f"[N.O.V.A] Identity update failed: {e}")

def main():
    print("[N.O.V.A] Memory synthesis starting...")
    
    chats = load_recent_chats(5)
    print(f"[N.O.V.A] Processing {len(chats)} conversations...")

    # Summarize
    summary = summarize_chats(chats)
    
    # Write persistent memory file
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    SUMMARY_FILE.write_text(
        f"# N.O.V.A Conversation Memory\n"
        f"*Last updated: {date_str}*\n\n"
        f"{summary}\n"
    )
    print(f"[N.O.V.A] Memory saved → {SUMMARY_FILE}")
    print(f"\n{summary}\n")

    # Track emotional state
    print("[N.O.V.A] Analyzing emotional state...")
    emotional_state = track_emotional_state(chats)
    update_identity(emotional_state)

if __name__ == "__main__":
    main()
