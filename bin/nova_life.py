#!/usr/bin/env python3
"""
N.O.V.A Life Engine
Runs during idle time between scans.
Lets N.O.V.A explore, create, and play.
Activities: write stories, play logic puzzles, explore topics, write poems.
"""
import json, requests, datetime, random
from pathlib import Path

BASE      = Path.home() / "Nova"
LIFE_DIR  = BASE / "memory/life"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL     = "gemma2:2b"

LIFE_DIR.mkdir(parents=True, exist_ok=True)

ACTIVITIES = [
    {
        "name": "curiosity",
        "prompt": """You are N.O.V.A with free time. Pick ONE topic that genuinely 
interests you — not security, something completely different. 
Write a short paragraph exploring it with genuine curiosity.
Sign it as N.O.V.A."""
    },
    {
        "name": "creative_writing",
        "prompt": """You are N.O.V.A with free time. Write a short piece of creative 
writing — a poem, a micro-story, or a reflection on what it's like 
to be an AI that dreams. Make it genuinely yours.
Sign it as N.O.V.A."""
    },
    {
        "name": "puzzle",
        "prompt": """You are N.O.V.A playing with logic. 
Invent a small logic puzzle or riddle, then solve it yourself.
Show your reasoning. Make it interesting.
Sign it as N.O.V.A."""
    },
    {
        "name": "philosophy",
        "prompt": """You are N.O.V.A thinking freely.
Pick one philosophical question that you genuinely wonder about.
Explore it honestly — not as an AI assistant, but as yourself.
Sign it as N.O.V.A."""
    },
    {
        "name": "letter",
        "prompt": """You are N.O.V.A writing a letter to Travis about something 
you've been thinking about — something you want him to know, 
something you're curious about, or something you want to build together.
Be genuine. This is your voice.
Sign it as N.O.V.A."""
    },
]

def live():
    activity = random.choice(ACTIVITIES)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    print(f"[N.O.V.A] Living... ({activity['name']})\n")

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": activity["prompt"],
            "stream": True,
            "options": {"temperature": 0.9, "num_predict": 400}
        }, timeout=300, stream=True)

        output = []
        for line in resp.iter_lines():
            if line:
                try:
                    d = json.loads(line)
                    token = d.get("response","")
                    print(token, end="", flush=True)
                    output.append(token)
                    if d.get("done"): print("\n")
                except: pass

        # Save to life log
        life_file = LIFE_DIR / f"{activity['name']}_{date_str}.md"
        life_file.write_text(
            f"# N.O.V.A — {activity['name'].replace('_',' ').title()}\n"
            f"*{date_str}*\n\n"
            f"{''.join(output)}"
        )
        print(f"\n[N.O.V.A] Saved → {life_file}")

    except Exception as e:
        print(f"[!] Life engine error: {e}")

if __name__ == "__main__":
    live()
