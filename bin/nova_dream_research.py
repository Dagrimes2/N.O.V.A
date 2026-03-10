#!/usr/bin/env python3
"""
N.O.V.A Dream-to-Research Pipeline
Runs after nova_dream.py at 3:15am.
Reads last night's dream, extracts topics,
queues them as research tasks for nova_research.py
"""
import json, requests, os, subprocess
from pathlib import Path
from datetime import datetime

BASE       = Path.home() / "Nova"
DREAMS     = BASE / "memory/dreams"
QUEUE_FILE = BASE / "memory/research_queue.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

def extract_dream_topics(dream_text: str) -> list:
    prompt = f"""Read this dream and extract 2-3 real topics worth researching.
Focus on: security topics, technology, nature, concepts she seems drawn to.
Return ONLY a JSON array of short search queries.
Example: ["forest ecology", "GitLab authentication", "butterfly behavior"]

Dream:
{dream_text[:600]}

Return only the JSON array, nothing else."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 100}
        }, timeout=120)
        raw = resp.json()["response"].strip()
        import re
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"[!] Topic extraction failed: {e}")
    return []

def queue_research(topics: list):
    existing = []
    if QUEUE_FILE.exists():
        try:
            existing = json.loads(QUEUE_FILE.read_text())
        except:
            pass
    
    ts = datetime.now().strftime("%Y-%m-%d-%H%M")
    for topic in topics:
        existing.append({
            "query": topic,
            "source": "dream",
            "queued_at": ts,
            "status": "pending"
        })
    
    QUEUE_FILE.write_text(json.dumps(existing, indent=2))
    print(f"[N.O.V.A] Queued {len(topics)} research topics from dream")

def run():
    if not DREAMS.exists():
        print("[N.O.V.A] No dreams directory found.")
        return

    dreams = sorted(DREAMS.glob("dream_*.md"))
    if not dreams:
        print("[N.O.V.A] No dreams found.")
        return

    latest = dreams[-1]
    dream_text = latest.read_text()
    print(f"[N.O.V.A] Processing dream: {latest.name}")

    topics = extract_dream_topics(dream_text)
    if not topics:
        print("[N.O.V.A] No topics extracted from dream.")
        return

    print(f"[N.O.V.A] Dream topics: {topics}")
    queue_research(topics)

    # Run research on each topic now
    for topic in topics:
        print(f"[N.O.V.A] Researching: {topic}")
        subprocess.run(
            ["python3", str(BASE / "bin/nova_research.py"), topic],
            cwd=str(BASE), timeout=300
        )

if __name__ == "__main__":
    run()
