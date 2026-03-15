#!/usr/bin/env python3
"""
N.O.V.A Salience-Based Attention System

Topics gain salience from research, news, Travis messages, and dreams.
Salience decays over time based on each topic's individual decay rate.
The attention system feeds task selection — Nova works on what actually matters.

Boost amounts by source:
  research  +0.15    news    +0.12
  travis    +0.25    dream   +0.10

Storage: memory/attention.json
"""
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE           = Path.home() / "Nova"
ATTENTION_FILE = BASE / "memory/attention.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg          # noqa: F401 — available for future use
except Exception:
    pass

_DEFAULT_DECAY_RATE = 0.05   # salience lost per hour at max


# ── Persistence ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    if ATTENTION_FILE.exists():
        try:
            return json.loads(ATTENTION_FILE.read_text())
        except Exception:
            pass
    return {
        "topics":     {},
        "last_decay": _now_iso(),
    }


def _save(data: dict) -> None:
    ATTENTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    ATTENTION_FILE.write_text(json.dumps(data, indent=2))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _slug(topic: str) -> str:
    """Convert topic label to a filesystem-safe slug."""
    s = topic.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "unknown"


def _hours_since(iso_ts: str) -> float:
    """Return hours elapsed since an ISO timestamp string."""
    try:
        past = datetime.fromisoformat(iso_ts)
        now  = datetime.now(timezone.utc)
        # Make past tz-aware if it isn't
        if past.tzinfo is None:
            past = past.replace(tzinfo=timezone.utc)
        delta = now - past
        return delta.total_seconds() / 3600.0
    except Exception:
        return 0.0


# ── Public API ─────────────────────────────────────────────────────────────────

def boost(topic: str, amount: float = 0.2, source: str = "research") -> float:
    """
    Increase salience for topic. Salience is capped at 1.0.
    Creates the topic entry if it doesn't exist.
    Returns new salience value.
    """
    data  = _load()
    slug  = _slug(topic)
    label = topic.strip()

    topics = data.setdefault("topics", {})
    if slug not in topics:
        topics[slug] = {
            "label":        label,
            "salience":     0.0,
            "last_boosted": _now_iso(),
            "boost_count":  0,
            "sources":      [],
            "decay_rate":   _DEFAULT_DECAY_RATE,
        }

    entry = topics[slug]
    entry["salience"]    = round(min(1.0, entry["salience"] + amount), 4)
    entry["last_boosted"] = _now_iso()
    entry["boost_count"]  = entry.get("boost_count", 0) + 1
    # Track unique sources
    if source not in entry["sources"]:
        entry["sources"].append(source)

    _save(data)
    return entry["salience"]


def decay_all() -> int:
    """
    Apply time-based decay to all topics.
    decay = decay_rate * hours_since_last_decay
    Topics with salience < 0.01 are removed.
    Updates 'last_decay' timestamp.
    Returns count of topics remaining.
    """
    data    = _load()
    topics  = data.get("topics", {})
    last_ts = data.get("last_decay", _now_iso())
    hours   = _hours_since(last_ts)

    if hours < 0.001:
        return len(topics)

    to_delete = []
    for slug, entry in topics.items():
        rate  = entry.get("decay_rate", _DEFAULT_DECAY_RATE)
        decay = rate * hours
        new_salience = max(0.0, entry["salience"] - decay)
        entry["salience"] = round(new_salience, 4)
        if entry["salience"] < 0.01:
            to_delete.append(slug)

    for slug in to_delete:
        del topics[slug]

    data["last_decay"] = _now_iso()
    _save(data)
    return len(topics)


def top_topics(n: int = 5, min_salience: float = 0.1) -> list:
    """Return top n topics by salience, filtered to >= min_salience."""
    data   = _load()
    topics = data.get("topics", {})

    eligible = [
        {"slug": slug, **entry}
        for slug, entry in topics.items()
        if entry.get("salience", 0.0) >= min_salience
    ]
    eligible.sort(key=lambda t: t["salience"], reverse=True)
    return eligible[:n]


def get_salience(topic: str) -> float:
    """Return current salience for topic (0.0 if unknown)."""
    data   = _load()
    slug   = _slug(topic)
    entry  = data.get("topics", {}).get(slug, {})
    return entry.get("salience", 0.0)


def to_prompt_context(n: int = 4) -> str:
    """
    Return compact attention context for LLM injection.
    Example: "Attention: security/ssrf (0.82), philosophy (0.61), solana (0.44)"
    Returns "" if no salient topics above threshold.
    """
    top = top_topics(n=n, min_salience=0.1)
    if not top:
        return ""

    parts = []
    for t in top:
        label    = t.get("label", t.get("slug", "?"))
        salience = t.get("salience", 0.0)
        parts.append(f"{label} ({salience:.2f})")

    return "Attention: " + ", ".join(parts)


def status() -> None:
    """Print all topics with salience bars, decay rate, last decay time."""
    data   = _load()
    topics = data.get("topics", {})

    G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"
    C = "\033[36m"; B = "\033[1m"; NC = "\033[0m"; DIM = "\033[2m"

    print(f"\n{B}N.O.V.A Attention System{NC}")
    print(f"  Last decay : {DIM}{data.get('last_decay', 'never')[:19]}{NC}")
    print(f"  Topics     : {len(topics)}\n")

    if not topics:
        print(f"  {DIM}(no active topics){NC}\n")
        return

    sorted_topics = sorted(topics.items(), key=lambda x: x[1].get("salience", 0), reverse=True)

    for slug, entry in sorted_topics:
        sal   = entry.get("salience", 0.0)
        label = entry.get("label", slug)
        rate  = entry.get("decay_rate", _DEFAULT_DECAY_RATE)
        srcs  = ", ".join(entry.get("sources", []))
        boosts = entry.get("boost_count", 0)

        # Colour by salience level
        if sal >= 0.6:
            col = G
        elif sal >= 0.35:
            col = Y
        else:
            col = R

        bar_len = int(sal * 24)
        bar     = "█" * bar_len + "░" * (24 - bar_len)

        print(f"  {col}{bar}{NC} {sal:.3f}  {B}{label}{NC}")
        print(f"         {DIM}decay={rate}/h  boosts={boosts}  sources=[{srcs}]{NC}")
        print(f"         {DIM}last boosted: {entry.get('last_boosted','?')[:19]}{NC}")
        print()


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "status"

    if cmd == "status":
        status()
    elif cmd == "top":
        n = int(args[1]) if len(args) >= 2 else 5
        top = top_topics(n=n)
        if not top:
            print("No salient topics.")
        else:
            for t in top:
                print(f"  {t['salience']:.3f}  {t['label']}")
    elif cmd == "boost" and len(args) >= 2:
        topic  = args[1]
        amount = float(args[2]) if len(args) >= 3 else 0.2
        source = args[3] if len(args) >= 4 else "manual"
        new_sal = boost(topic, amount, source)
        print(f"Boosted '{topic}' by {amount} (source={source}). Salience: {new_sal:.3f}")
    elif cmd == "decay":
        remaining = decay_all()
        print(f"Decay applied. {remaining} topics remaining.")
    elif cmd == "context":
        n = int(args[1]) if len(args) >= 2 else 4
        ctx = to_prompt_context(n=n)
        print(ctx if ctx else "(no salient topics)")
    elif cmd == "salience" and len(args) >= 2:
        topic = " ".join(args[1:])
        print(f"{topic}: {get_salience(topic):.4f}")
    else:
        print("Usage: nova attention [status|top [N]|boost <topic> [amount] [source]|"
              "decay|context [N]|salience <topic>]")


if __name__ == "__main__":
    main()
