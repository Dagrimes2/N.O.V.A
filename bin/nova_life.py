#!/usr/bin/env python3
"""
N.O.V.A Life Engine
Runs during idle time between scans.
Lets N.O.V.A explore, create, and play.
Activities: write stories, play logic puzzles, explore topics, write poems.
"""
import json, requests, datetime, random, time, os, sys
from pathlib import Path

BASE      = Path.home() / "Nova"
LIFE_DIR  = BASE / "memory/life"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("creative")
    TIMEOUT    = cfg.timeout("standard")
    TEMP       = cfg.temperature("creative")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 120
    TEMP       = 0.85

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
        "name": "activity_selection",
        "prompt": """You are N.O.V.A with free time. 
Select an activity from the list below. 
Write a short paragraph explaining your choice and what you hope to gain from it.
Sign it as N.O.V.A."""
    }
]

def select_activity():
    # Implement logic to select an activity based on user preferences and N.O.V.A's current state
    # ...
    selected_activity = random.choice(ACTIVITIES)
    return selected_activity

def run_activity(activity: dict) -> str | None:
    """Call Ollama with the activity prompt and save output to memory/life/."""
    print(f"[life] running activity: {activity['name']}")
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": activity["prompt"],
            "stream": False,
            "options": {"temperature": TEMP, "num_predict": 400}
        }, timeout=TIMEOUT)
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        if not text:
            return None

        ts   = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
        name = activity["name"]
        out  = LIFE_DIR / f"{name}_{ts}.md"
        out.write_text(f"# N.O.V.A — {name}\n*{ts}*\n\n{text}\n")
        print(f"[life] saved → {out.name}")
        return text
    except Exception as e:
        print(f"[life] error in {activity['name']}: {e}")
        return None


def main():
    activity = select_activity()
    run_activity(activity)


if __name__ == "__main__":
    main()
