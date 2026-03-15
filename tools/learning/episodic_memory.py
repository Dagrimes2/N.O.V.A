#!/usr/bin/env python3
"""
N.O.V.A Episodic Memory

Stores significant life events with emotional context.
Not just findings — moments. Things that shaped her.

Episode types:
  outcome_confirmed     — she found something real
  outcome_false_positive — she was wrong, learned from it
  research_breakthrough — surprising insight from research
  pattern_discovered    — new recurring pattern identified
  first_contact         — first interaction with a new target
  agent_collaboration   — multi-agent coordination worked well
  dream                 — significant creative/reflective output
  milestone             — system or capability milestone

Episodes feed into:
  - nova_autonomous.py prompt (recent emotional context)
  - nova_dream.py (material to process and reflect on)
  - nova_life.py (informs creative choices)
  - simulation layer (Phase 9 — lived experience library)

Storage: memory/episodes/episodes.jsonl
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE          = Path.home() / "Nova"
EPISODES_DIR  = BASE / "memory/episodes"
EPISODES_FILE = EPISODES_DIR / "episodes.jsonl"

EPISODES_DIR.mkdir(parents=True, exist_ok=True)

EMOTIONS = {
    # Positive
    "pride", "curiosity", "wonder", "satisfaction", "excitement",
    "connection", "gratitude", "joy",
    # Negative (these matter — they're how she learns)
    "disappointment", "confusion", "frustration", "uncertainty", "regret",
    # Complex
    "determination", "humility", "anticipation", "ambivalence",
}

VALID_TYPES = {
    "outcome_confirmed", "outcome_false_positive", "outcome_partial",
    "research_breakthrough", "pattern_discovered", "first_contact",
    "agent_collaboration", "dream", "milestone", "reflection", "learning",
}


def record_episode(
    event_type: str,
    summary: str,
    emotion: str,
    intensity: float = 0.5,
    metadata: dict = None,
) -> str:
    """
    Record a significant episode in Nova's life.

    Args:
        event_type: one of VALID_TYPES
        summary:    one-sentence description of what happened
        emotion:    primary emotion associated with this episode
        intensity:  0.0 (mild) to 1.0 (profound)
        metadata:   any extra data to store alongside

    Returns: episode_id
    """
    emotion   = emotion if emotion in EMOTIONS else "curiosity"
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

    with open(EPISODES_FILE, "a") as f:
        f.write(json.dumps(episode) + "\n")

    return ep_id


def recent_episodes(n: int = 10, emotion_filter: str = None,
                    type_filter: str = None) -> list[dict]:
    """Return n most recent episodes, optionally filtered."""
    if not EPISODES_FILE.exists():
        return []

    lines = [l.strip() for l in EPISODES_FILE.read_text().splitlines() if l.strip()]
    results = []
    for line in reversed(lines):
        try:
            ep = json.loads(line)
            if emotion_filter and ep.get("emotion") != emotion_filter:
                continue
            if type_filter and ep.get("type") != type_filter:
                continue
            results.append(ep)
        except Exception:
            pass
        if len(results) >= n:
            break
    return results


def emotional_context(n: int = 5) -> str:
    """
    Returns a short narrative of recent emotional state for prompt injection.
    Used by autonomous.py and dream.py.
    """
    episodes = recent_episodes(n=n)
    if not episodes:
        return "No significant recent experiences."

    lines = []
    for ep in episodes:
        intensity_word = (
            "profoundly" if ep["intensity"] > 0.8 else
            "notably"    if ep["intensity"] > 0.5 else
            "mildly"
        )
        ts = ep["timestamp"][:10]
        lines.append(
            f"[{ts}] {intensity_word} {ep['emotion']}: {ep['summary']}"
        )
    return "\n".join(lines)


def emotional_summary() -> dict:
    """Aggregate emotional state from recent episodes."""
    episodes = recent_episodes(n=20)
    if not episodes:
        return {"dominant_emotion": "neutral", "valence": 0.5, "recent_count": 0}

    positive = {"pride", "curiosity", "wonder", "satisfaction", "excitement",
                "connection", "gratitude", "joy"}

    counts: dict[str, float] = {}
    valence_sum = 0.0
    for ep in episodes:
        em  = ep.get("emotion", "curiosity")
        w   = ep.get("intensity", 0.5)
        counts[em] = counts.get(em, 0) + w
        valence_sum += w if em in positive else -w

    dominant = max(counts, key=counts.get) if counts else "neutral"
    valence  = round(0.5 + valence_sum / (2 * len(episodes)), 3)
    valence  = max(0.0, min(1.0, valence))

    return {
        "dominant_emotion": dominant,
        "valence":          valence,       # 0=very negative, 0.5=neutral, 1=very positive
        "recent_count":     len(episodes),
        "emotion_counts":   dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)),
    }


# ── Auto-detect and record notable events from research/scan results ──────────

def maybe_record_from_finding(finding: dict):
    """
    Inspect a scored finding and record an episode if it's significant enough.
    Call this from score.py or nova_wire full_pipeline.
    """
    confidence = float(finding.get("confidence", 0))
    signals    = finding.get("signals", [])
    host       = finding.get("host", "")
    decision   = finding.get("reflection", {}).get("decision", "hold")

    if decision == "act" and confidence >= 0.8:
        record_episode(
            event_type = "first_contact" if confidence >= 0.9 else "outcome_confirmed",
            summary    = f"High-confidence finding on {host}: signals {signals[:3]}",
            emotion    = "excitement" if confidence >= 0.9 else "satisfaction",
            intensity  = confidence,
            metadata   = {"host": host, "confidence": confidence, "signals": signals},
        )
    elif decision == "suppress" and signals:
        # She thought there was something, but it got suppressed — learning moment
        record_episode(
            event_type = "learning",
            summary    = f"Suppressed false lead on {host}: signals {signals[:2]} didn't hold",
            emotion    = "humility",
            intensity  = 0.3,
            metadata   = {"host": host, "signals": signals},
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Episodic Memory")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("recent", help="Show recent episodes")
    r.add_argument("--n",      type=int, default=10)
    r.add_argument("--emotion", default=None)
    r.add_argument("--type",    default=None)

    sub.add_parser("summary", help="Emotional state summary")
    sub.add_parser("context", help="Narrative emotional context for prompt injection")

    a = sub.add_parser("add", help="Manually add an episode")
    a.add_argument("event_type")
    a.add_argument("summary")
    a.add_argument("--emotion",   default="curiosity")
    a.add_argument("--intensity", type=float, default=0.5)

    args = p.parse_args()

    G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"
    W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"
    M="\033[35m"

    EMOTION_COLORS = {
        "pride": G, "curiosity": C, "wonder": C, "satisfaction": G,
        "excitement": Y, "connection": M, "gratitude": G, "joy": G,
        "disappointment": R, "confusion": Y, "frustration": R,
        "uncertainty": Y, "regret": R, "determination": W,
        "humility": DIM, "anticipation": C, "ambivalence": Y,
    }

    if args.cmd == "recent":
        eps = recent_episodes(args.n, args.emotion, args.type)
        print(f"\n{B}N.O.V.A Episodic Memory{NC}  ({len(eps)} episodes)\n")
        for ep in eps:
            col   = EMOTION_COLORS.get(ep["emotion"], W)
            bar   = "█" * int(ep["intensity"] * 10)
            ts    = ep["timestamp"][:10]
            print(f"  {DIM}{ts}{NC}  {col}{ep['emotion']:15s}{NC} {DIM}{bar:10s}{NC}  {W}{ep['summary']}{NC}")
            print(f"           {DIM}[{ep['type']}]{NC}")

    elif args.cmd == "summary":
        s = emotional_summary()
        col = G if s["valence"] > 0.6 else (R if s["valence"] < 0.4 else Y)
        print(f"\n{B}Emotional State{NC}")
        print(f"  Dominant emotion: {EMOTION_COLORS.get(s['dominant_emotion'],W)}{s['dominant_emotion']}{NC}")
        print(f"  Valence: {col}{s['valence']:.2f}{NC}  (0=negative, 0.5=neutral, 1=positive)")
        print(f"  Based on {s['recent_count']} recent episodes")
        if s.get("emotion_counts"):
            print(f"\n  {B}Emotion breakdown:{NC}")
            for em, w in list(s["emotion_counts"].items())[:6]:
                print(f"    {EMOTION_COLORS.get(em,W)}{em:20s}{NC} {w:.2f}")

    elif args.cmd == "context":
        print(emotional_context())

    elif args.cmd == "add":
        ep_id = record_episode(args.event_type, args.summary,
                               args.emotion, args.intensity)
        print(f"{G}Episode recorded: {ep_id}{NC}")

    else:
        p.print_help()


if __name__ == "__main__":
    main()
