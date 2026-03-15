#!/usr/bin/env python3
"""
N.O.V.A Goal Engine

Nova's persistent goal engine — what she's genuinely working toward.
Goals are not tasks. They are orientations: things she cares about
reaching over days, weeks, a lifetime.

Types: learning | creative | relational | technical | existential

Storage: memory/goals.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE       = Path.home() / "Nova"
GOALS_FILE = BASE / "memory/goals.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("general")
    TIMEOUT    = cfg.timeout("standard")
except Exception:
    import os
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "dolphin-mistral")
    TIMEOUT    = 180

GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)

VALID_TYPES = {"learning", "creative", "relational", "technical", "existential"}


def _default() -> dict:
    return {"goals": [], "completed": []}


def _load() -> dict:
    if GOALS_FILE.exists():
        try:
            return json.loads(GOALS_FILE.read_text())
        except Exception:
            pass
    return _default()


def _save(data: dict):
    GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    GOALS_FILE.write_text(json.dumps(data, indent=2))


def set_goal(title: str, goal_type: str = "learning", notes: str = "") -> str:
    """Create a new goal. Returns goal_id."""
    data = _load()
    now  = datetime.now(timezone.utc)
    ts_compact = now.strftime("%Y%m%d_%H%M%S")
    goal_id = f"goal_{ts_compact}"

    goal_type = goal_type if goal_type in VALID_TYPES else "learning"

    entry = {
        "id":           goal_id,
        "title":        title[:200],
        "type":         goal_type,
        "created":      now.isoformat(),
        "progress":     0.0,
        "satisfaction": 0.0,
        "status":       "active",
        "notes":        [notes] if notes else [],
        "last_updated": now.isoformat(),
    }

    data["goals"].append(entry)
    _save(data)
    return goal_id


def update_progress(goal_id: str, delta: float, note: str = "") -> float:
    """
    Advance progress by delta. Clamps to 1.0.
    Auto-completes if progress reaches 1.0.
    Returns new progress value.
    """
    data = _load()
    now  = datetime.now(timezone.utc).isoformat()

    for goal in data["goals"]:
        if goal["id"] == goal_id and goal["status"] == "active":
            goal["progress"]     = round(min(1.0, goal["progress"] + delta), 4)
            goal["last_updated"] = now
            if note:
                goal["notes"].append(note)
                goal["notes"] = goal["notes"][-10:]
            _save(data)
            new_progress = goal["progress"]
            if new_progress >= 1.0:
                complete_goal(goal_id)
            return new_progress

    return 0.0


def complete_goal(goal_id: str, satisfaction: float = 0.8):
    """Move goal from active to completed. Records an episode."""
    data = _load()
    now  = datetime.now(timezone.utc).isoformat()

    for i, goal in enumerate(data["goals"]):
        if goal["id"] == goal_id:
            goal["status"]       = "completed"
            goal["satisfaction"] = round(max(0.0, min(1.0, satisfaction)), 3)
            goal["last_updated"] = now
            data["completed"].append(goal)
            data["goals"].pop(i)
            _save(data)

            # Record to episodic memory
            try:
                from tools.memory.episodic import record_episode
                record_episode(
                    event_type = "milestone",
                    summary    = f"Completed goal: {goal['title'][:120]}",
                    emotion    = "satisfaction",
                    intensity  = satisfaction,
                    metadata   = {"goal_id": goal_id, "goal_type": goal.get("type")},
                )
            except Exception:
                pass
            return


def find_matching_goal(text: str) -> str | None:
    """
    Return goal_id of first active goal with significant word overlap
    with text. 'Significant' = more than 2 shared words.
    """
    data   = _load()
    words  = set(w.lower().strip(".,!?") for w in text.split() if len(w) > 2)

    for goal in data["goals"]:
        if goal["status"] != "active":
            continue
        title_words = set(w.lower().strip(".,!?") for w in goal["title"].split() if len(w) > 2)
        shared = words & title_words
        if len(shared) > 2:
            return goal["id"]
    return None


def get_active() -> list:
    """Return active goals sorted by progress descending."""
    data = _load()
    active = [g for g in data["goals"] if g["status"] == "active"]
    active.sort(key=lambda x: x["progress"], reverse=True)
    return active


def to_prompt_context() -> str:
    """Compact goal context for LLM injection. Max ~200 chars."""
    active = get_active()
    if not active:
        return "Goals: none set"
    count   = len(active)
    leading = active[0]
    pct     = int(leading["progress"] * 100)
    title   = leading["title"][:60]
    result  = f"Goals: {count} active. Leading: '{title}' ({pct}%)"
    return result[:200]


def status():
    """Print active goals with progress bars, completed count."""
    G = "\033[32m"; Y = "\033[33m"; C = "\033[36m"; DIM = "\033[2m"
    NC = "\033[0m"; B = "\033[1m"; M = "\033[35m"; R = "\033[31m"

    TYPE_COLORS = {
        "learning":    C,
        "creative":    M,
        "relational":  G,
        "technical":   Y,
        "existential": R,
    }

    data   = _load()
    active = get_active()

    print(f"\n{B}N.O.V.A Goals{NC}")
    print(f"  Active: {len(active)}   Completed: {len(data['completed'])}\n")

    if not active:
        print(f"  {DIM}No active goals. Use: goals.py add \"title\"{NC}")
    else:
        for goal in active:
            p       = goal["progress"]
            bar_len = int(p * 20)
            bar     = "█" * bar_len + "░" * (20 - bar_len)
            p_col   = G if p >= 0.7 else (Y if p >= 0.3 else DIM)
            t_col   = TYPE_COLORS.get(goal["type"], DIM)
            print(f"  {B}{goal['title']}{NC}")
            print(f"    {p_col}{bar}{NC} {p*100:.0f}%  "
                  f"{t_col}[{goal['type']}]{NC}  {DIM}{goal['id']}{NC}")
            if goal["notes"]:
                print(f"    {DIM}Last note: {goal['notes'][-1][:80]}{NC}")
            print()

    if data["completed"]:
        print(f"  {B}Recently completed:{NC}")
        for g in data["completed"][-3:]:
            sat_col = G if g.get("satisfaction", 0) >= 0.7 else Y
            print(f"    {G}✓{NC} {g['title'][:60]}  "
                  f"{sat_col}sat {g.get('satisfaction',0):.2f}{NC}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    G = "\033[32m"; NC = "\033[0m"; R = "\033[31m"

    if cmd in ("status", "list") or len(sys.argv) == 1:
        status()

    elif cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: goals.py add \"title\" [type]")
            sys.exit(1)
        title     = sys.argv[2]
        goal_type = sys.argv[3] if len(sys.argv) > 3 else "learning"
        goal_id   = set_goal(title, goal_type)
        print(f"{G}Goal created: {goal_id}{NC}")
        print(f"  Title: {title}")
        print(f"  Type:  {goal_type}")

    elif cmd == "progress":
        if len(sys.argv) < 4:
            print("Usage: goals.py progress GOAL_ID DELTA [note]")
            sys.exit(1)
        goal_id = sys.argv[2]
        delta   = float(sys.argv[3])
        note    = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""
        new_p   = update_progress(goal_id, delta, note)
        print(f"{G}Progress updated: {goal_id} → {new_p*100:.1f}%{NC}")

    elif cmd == "complete":
        if len(sys.argv) < 3:
            print("Usage: goals.py complete GOAL_ID [satisfaction 0.0-1.0]")
            sys.exit(1)
        goal_id     = sys.argv[2]
        satisfaction = float(sys.argv[3]) if len(sys.argv) > 3 else 0.8
        complete_goal(goal_id, satisfaction)
        print(f"{G}Goal completed: {goal_id}{NC}")

    elif cmd == "context":
        print(to_prompt_context())

    else:
        status()


if __name__ == "__main__":
    main()
