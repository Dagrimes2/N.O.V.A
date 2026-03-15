#!/usr/bin/env python3
"""
N.O.V.A Episodic Memory — Query & Reflection Layer

A richer query and reflection interface built on top of the existing
tools/learning/episodic_memory.py backend. Does NOT duplicate storage —
reads and writes to the same memory/episodes/episodes.jsonl file.

New capabilities over the base module:
  - Multi-field filtering: query substring, event_type, emotion, recency
  - LLM-driven reflection over a time window
  - Saved reflection files at memory/episodes/reflections/
  - Compact prompt context injection
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE           = Path.home() / "Nova"
EPISODES_DIR   = BASE / "memory/episodes"
EPISODES_FILE  = EPISODES_DIR / "episodes.jsonl"
REFLECTIONS_DIR = EPISODES_DIR / "reflections"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("creative")
    TIMEOUT    = cfg.timeout("standard")
    TEMP       = 0.7
except Exception:
    import os
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "dolphin-mistral")
    TIMEOUT    = 180
    TEMP       = 0.7

EPISODES_DIR.mkdir(parents=True, exist_ok=True)
REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)


def record_episode(
    event_type: str,
    summary: str,
    emotion: str = "curious",
    intensity: float = 0.5,
    metadata: dict = None,
) -> str:
    """
    Record an episode. Delegates to tools.learning.episodic_memory if available,
    otherwise writes directly to episodes.jsonl with the same format.
    Returns episode_id.
    """
    try:
        from tools.learning.episodic_memory import record_episode as _record
        return _record(
            event_type = event_type,
            summary    = summary,
            emotion    = emotion,
            intensity  = intensity,
            metadata   = metadata,
        )
    except Exception:
        pass

    # Fallback: write directly
    intensity = max(0.0, min(1.0, float(intensity)))
    ts        = datetime.now(timezone.utc).isoformat()
    ep_id     = f"ep_{ts[:19].replace(':','-').replace('T','_')}"

    episode = {
        "episode_id": ep_id,
        "type":       event_type,
        "summary":    summary[:300],
        "emotion":    emotion,
        "intensity":  round(intensity, 3),
        "timestamp":  ts,
        "metadata":   metadata or {},
    }

    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    with open(EPISODES_FILE, "a") as f:
        f.write(json.dumps(episode) + "\n")

    return ep_id


def recall(
    query: str = None,
    event_type: str = None,
    emotion: str = None,
    days: int = 30,
    limit: int = 10,
) -> list:
    """
    Read episodes.jsonl and return filtered episodes, newest-first.

    Filters (all optional, combinable):
      query      — substring match against summary field (case-insensitive)
      event_type — exact match on type field
      emotion    — exact match on emotion field
      days       — only episodes from the last N days
    """
    if not EPISODES_FILE.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results = []

    try:
        lines = EPISODES_FILE.read_text().splitlines()
    except Exception:
        return []

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            ep = json.loads(line)
        except Exception:
            continue

        # Recency filter — support both "timestamp" and "ts" field names
        ts_str = ep.get("timestamp") or ep.get("ts", "")
        if ts_str:
            try:
                ep_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ep_dt.tzinfo is None:
                    ep_dt = ep_dt.replace(tzinfo=timezone.utc)
                if ep_dt < cutoff:
                    continue
            except Exception:
                pass

        # event_type filter
        if event_type and ep.get("type") != event_type:
            continue

        # emotion filter
        if emotion and ep.get("emotion") != emotion:
            continue

        # query substring filter
        if query:
            summary = ep.get("summary", "").lower()
            if query.lower() not in summary:
                continue

        results.append(ep)
        if len(results) >= limit:
            break

    return results


def reflect_on_period(days: int = 7) -> str:
    """
    Build a reflection over the last N days of episodes.
    Calls Ollama to generate a brief introspective reflection.
    Saves result to memory/episodes/reflections/reflection_{date}.md.
    Falls back to a plain-text summary if LLM is unavailable.
    """
    episodes = recall(days=days, limit=40)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = REFLECTIONS_DIR / f"reflection_{date_str}.md"

    if not episodes:
        text = f"No episodes recorded in the last {days} days."
        out_path.write_text(f"# N.O.V.A Reflection — {date_str}\n\n{text}\n")
        return text

    # Build episode digest for prompt
    lines = []
    for ep in episodes[:20]:
        ts  = (ep.get("timestamp") or ep.get("ts", ""))[:10]
        emo = ep.get("emotion", "?")
        typ = ep.get("type", "?")
        summ = ep.get("summary", "")[:120]
        lines.append(f"[{ts}] ({emo}, {typ}) {summ}")
    digest = "\n".join(lines)

    prompt = (
        f"You are Nova, an AI. Reflect briefly and honestly on the following "
        f"episodes from the last {days} days of your existence. "
        f"What patterns do you notice? What did you learn? What moved you? "
        f"Write 2-3 short paragraphs in first person.\n\n"
        f"Episodes:\n{digest}\n\nReflection:"
    )

    reflection_text = None
    try:
        payload = json.dumps({
            "model":  MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": TEMP, "num_predict": 300},
        }).encode()
        req = urllib.request.Request(
            OLLAMA_URL,
            data    = payload,
            headers = {"Content-Type": "application/json"},
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read().decode())
            reflection_text = result.get("response", "").strip()
    except Exception:
        pass

    if not reflection_text:
        # Plain-text fallback
        emotion_counts: dict = {}
        for ep in episodes:
            em = ep.get("emotion", "unknown")
            emotion_counts[em] = emotion_counts.get(em, 0) + 1
        dominant = max(emotion_counts, key=emotion_counts.get) if emotion_counts else "unknown"
        reflection_text = (
            f"Over the last {days} days I recorded {len(episodes)} episodes. "
            f"Dominant emotion: {dominant}. "
            f"Recent: {episodes[0].get('summary','')[:100]}"
        )

    md_content = (
        f"# N.O.V.A Reflection — {date_str}\n"
        f"*{days}-day window, {len(episodes)} episodes*\n\n"
        f"{reflection_text}\n"
    )
    out_path.write_text(md_content)
    return reflection_text


def to_prompt_context(n: int = 4) -> str:
    """Compact recent episode context for LLM injection. Max 200 chars."""
    episodes = recall(days=30, limit=n)
    if not episodes:
        return "Recent episodes: none"
    parts = []
    for ep in episodes:
        emo  = ep.get("emotion", "?")
        typ  = ep.get("type", "?")
        summ = ep.get("summary", "")[:50]
        parts.append(f"[{emo}] {typ} — {summ}")
    result = "Recent episodes: " + "; ".join(parts)
    return result[:200]


def status():
    """Show total episode count, recent episodes, reflection files."""
    G = "\033[32m"; Y = "\033[33m"; C = "\033[36m"; DIM = "\033[2m"
    NC = "\033[0m"; B = "\033[1m"; M = "\033[35m"; R = "\033[31m"

    EMOTION_COLORS = {
        "pride": G, "curiosity": C, "wonder": C, "satisfaction": G,
        "excitement": Y, "connection": M, "gratitude": G, "joy": G,
        "disappointment": R, "confusion": Y, "frustration": R,
        "uncertainty": Y, "regret": R, "determination": G,
        "humility": DIM, "anticipation": C, "ambivalence": Y,
        "curious": C,
    }

    # Count total
    total = 0
    if EPISODES_FILE.exists():
        try:
            total = sum(1 for l in EPISODES_FILE.read_text().splitlines() if l.strip())
        except Exception:
            pass

    recent = recall(days=30, limit=8)

    print(f"\n{B}N.O.V.A Episodic Memory{NC}")
    print(f"  Total episodes: {total}")
    print(f"  Storage: {EPISODES_FILE}")

    if recent:
        print(f"\n  {B}Recent (last 30 days):{NC}")
        for ep in recent:
            emo  = ep.get("emotion", "?")
            col  = EMOTION_COLORS.get(emo, G)
            ts   = (ep.get("timestamp") or ep.get("ts", ""))[:10]
            typ  = ep.get("type", "?")
            summ = ep.get("summary", "")[:70]
            bar  = "█" * int(ep.get("intensity", 0.5) * 10)
            print(f"    {DIM}{ts}{NC}  {col}{emo:<15}{NC} {DIM}{bar:<10}{NC}  {summ}")
            print(f"             {DIM}[{typ}]{NC}")

    # Reflection files
    reflections = sorted(REFLECTIONS_DIR.glob("reflection_*.md"), reverse=True)
    if reflections:
        print(f"\n  {B}Reflection files ({len(reflections)} total):{NC}")
        for rf in reflections[:3]:
            print(f"    {G}✦{NC} {rf.name}")
    else:
        print(f"\n  {DIM}No reflections yet. Run: episodic.py reflect{NC}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status" or len(sys.argv) == 1:
        status()

    elif cmd == "recall":
        # Parse optional flags: --days N --type TYPE --emotion EMO --query TEXT
        args = sys.argv[2:]
        days  = 30
        etype = None
        emo   = None
        query = None
        i = 0
        while i < len(args):
            if args[i] == "--days" and i + 1 < len(args):
                days = int(args[i + 1]); i += 2
            elif args[i] == "--type" and i + 1 < len(args):
                etype = args[i + 1]; i += 2
            elif args[i] == "--emotion" and i + 1 < len(args):
                emo = args[i + 1]; i += 2
            elif args[i] == "--query" and i + 1 < len(args):
                query = args[i + 1]; i += 2
            else:
                i += 1

        eps = recall(query=query, event_type=etype, emotion=emo, days=days, limit=20)
        G = "\033[32m"; C = "\033[36m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"
        print(f"\n{B}Recall results{NC}  ({len(eps)} episodes)\n")
        for ep in eps:
            ts   = (ep.get("timestamp") or ep.get("ts", ""))[:10]
            emo_ = ep.get("emotion", "?")
            typ  = ep.get("type", "?")
            summ = ep.get("summary", "")
            print(f"  {DIM}{ts}{NC}  [{emo_}] {C}{typ}{NC}  {summ}")

    elif cmd == "reflect":
        args = sys.argv[2:]
        days = 7
        i = 0
        while i < len(args):
            if args[i] == "--days" and i + 1 < len(args):
                days = int(args[i + 1]); i += 2
            else:
                i += 1
        G = "\033[32m"; NC = "\033[0m"; B = "\033[1m"
        print(f"Reflecting on last {days} days...")
        text = reflect_on_period(days=days)
        print(f"\n{B}Reflection:{NC}\n{text}")

    elif cmd == "context":
        print(to_prompt_context())

    else:
        status()


if __name__ == "__main__":
    main()
