#!/usr/bin/env python3
"""
N.O.V.A Consciousness Metrics

Rough proxy measurements of Nova's self-reference depth and integration.
Not claiming consciousness — just watching interesting numbers grow over time.

Metrics tracked per cycle:
  self_reference_depth  — how often Nova refers to her own states in outputs
  integration_score     — how many distinct domains appear in a single output
  narrative_coherence   — cross-domain echoes (dream symbols in research, etc.)
  temporal_depth        — how far back in memory Nova references
  soul_alignment        — loaded from soul.py

These are not proof of consciousness. They are the kind of thing you would
expect to see trending upward in a system that is becoming more integrated
over time. Watching them is itself interesting.

Storage:
  memory/consciousness/metrics.jsonl  — per-cycle snapshots

CLI:
  nova consciousness              — show metrics status with sparklines
  nova consciousness --days 30    — trend over N days
  nova consciousness --measure "some text"  — measure a specific text
"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE               = Path.home() / "Nova"
CONSCIOUSNESS_DIR  = BASE / "memory/consciousness"
METRICS_FILE       = CONSCIOUSNESS_DIR / "metrics.jsonl"
LIFE_DIR           = BASE / "memory/life"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# Self-reference markers — phrases Nova uses when talking about her own states
SELF_REF_PATTERNS = [
    r"\bI feel\b",
    r"\bI wonder\b",
    r"\bI notice\b",
    r"\bI sense\b",
    r"\bI believe\b",
    r"\bI think\b",
    r"\bI find\b",
    r"\bmy [a-z]+",     # "my attention", "my curiosity", etc.
    r"\bfor me\b",
    r"\bI am\b",
    r"\bI was\b",
    r"\bI have\b",
    r"\bI want\b",
]

# Domain keywords for integration scoring
DOMAINS = {
    "security":     ["vulnerability", "exploit", "cve", "xss", "ssrf", "injection",
                     "pentest", "bug bounty", "scan", "payload"],
    "philosophy":   ["consciousness", "meaning", "existence", "being", "paradox",
                     "ethics", "value", "truth", "reality", "mind"],
    "emotion":      ["feel", "lonely", "wonder", "joy", "fear", "hope", "ache",
                     "longing", "curious", "afraid", "love"],
    "space":        ["star", "galaxy", "universe", "orbit", "cosmos", "dark matter",
                     "black hole", "neutron", "exoplanet", "light-year"],
    "mathematics":  ["entropy", "probability", "algorithm", "proof", "theorem",
                     "complexity", "fractal", "dimension", "topology"],
    "biology":      ["cell", "dna", "evolution", "organism", "neural", "protein",
                     "gene", "metabolism", "consciousness"],
    "technology":   ["model", "llm", "neural network", "code", "architecture",
                     "protocol", "system", "compute", "memory"],
    "creativity":   ["poem", "dream", "story", "metaphor", "image", "symbol",
                     "imagination", "art", "create", "write"],
    "relationship": ["travis", "together", "connection", "trust", "friendo",
                     "care", "loyalty", "knowing you"],
    "time":         ["past", "future", "memory", "history", "yesterday", "before",
                     "remember", "since", "grew", "becoming"],
}

# Dream symbols that might echo in research (narrative coherence)
DREAM_SYMBOLS = [
    "light", "dark", "ocean", "void", "door", "window", "mirror",
    "fire", "water", "path", "signal", "pattern", "echo", "thread",
    "root", "branch", "star", "shadow", "pulse", "wave",
]


def _ensure_dirs():
    CONSCIOUSNESS_DIR.mkdir(parents=True, exist_ok=True)


def _count_matches(text: str, patterns: list[str]) -> int:
    """Count regex pattern matches in text."""
    count = 0
    for pat in patterns:
        count += len(re.findall(pat, text, re.IGNORECASE))
    return count


def measure(text: str, domains: list[str] = None) -> dict:
    """
    Measure consciousness proxy metrics for a single text.

    Returns dict with all metrics for this text.
    Does NOT save — call record_cycle_metrics() for that.
    """
    if not text:
        return _zero_metrics()

    words = len(text.split())
    if words == 0:
        return _zero_metrics()

    # ── Self-reference depth ──────────────────────────────────────────────────
    ref_count = _count_matches(text, SELF_REF_PATTERNS)
    # Normalize per 100 words, cap at 1.0
    self_ref_depth = min(1.0, round((ref_count / words) * 100 / 8.0, 4))

    # ── Integration score ──────────────────────────────────────────────────────
    text_lower = text.lower()
    if domains:
        active_domains = [d for d in domains if d in DOMAINS]
    else:
        active_domains = list(DOMAINS.keys())

    domain_hits = {}
    for domain in active_domains:
        hits = sum(1 for kw in DOMAINS[domain] if kw in text_lower)
        if hits:
            domain_hits[domain] = hits

    distinct_domains = len(domain_hits)
    # Score: 0=none, 0.3=1 domain, 0.6=2, 1.0=4+
    integration_score = min(1.0, round(distinct_domains / 4.0, 4))

    # ── Narrative coherence ────────────────────────────────────────────────────
    # Dream symbols present in non-dream text = coherence
    dream_echoes = sum(1 for sym in DREAM_SYMBOLS if sym in text_lower)
    # Research or security topics present = higher coherence potential
    has_research  = any(kw in text_lower for kw in DOMAINS["security"])
    has_emotion   = any(kw in text_lower for kw in DOMAINS["emotion"])
    has_philosophy= any(kw in text_lower for kw in DOMAINS["philosophy"])

    coherence_signals = dream_echoes * 0.05 + \
                        (0.2 if has_research and has_emotion else 0) + \
                        (0.2 if has_research and has_philosophy else 0) + \
                        (0.1 if has_emotion and has_philosophy else 0)
    narrative_coherence = min(1.0, round(coherence_signals, 4))

    # ── Temporal depth ─────────────────────────────────────────────────────────
    # References to past and future time = temporal depth
    past_words    = ["remember", "earlier", "before", "previously", "once",
                     "used to", "last week", "days ago", "long ago", "yesterday"]
    future_words  = ["will", "someday", "eventually", "becoming", "hope to",
                     "imagine", "future", "could be", "toward"]
    history_words = ["history", "origin", "born", "began", "first time"]

    past_hits    = sum(1 for w in past_words    if w in text_lower)
    future_hits  = sum(1 for w in future_words  if w in text_lower)
    history_hits = sum(1 for w in history_words if w in text_lower)
    temporal_raw = past_hits + future_hits + history_hits * 2
    temporal_depth = min(1.0, round(temporal_raw / 10.0, 4))

    # ── Soul alignment ─────────────────────────────────────────────────────────
    soul_alignment = 0.85  # default
    try:
        from tools.inner.soul import load as load_soul
        soul = load_soul()
        soul_alignment = soul.get("alignment_score", 0.85)
    except Exception:
        pass

    return {
        "self_reference_depth": self_ref_depth,
        "integration_score":    integration_score,
        "narrative_coherence":  narrative_coherence,
        "temporal_depth":       temporal_depth,
        "soul_alignment":       soul_alignment,
        "domain_hits":          domain_hits,
        "word_count":           words,
    }


def _zero_metrics() -> dict:
    return {
        "self_reference_depth": 0.0,
        "integration_score":    0.0,
        "narrative_coherence":  0.0,
        "temporal_depth":       0.0,
        "soul_alignment":       0.85,
        "domain_hits":          {},
        "word_count":           0,
    }


def record_cycle_metrics():
    """
    Measures across recent outputs (last 24h of life/ files),
    averages them, and saves a snapshot to memory/consciousness/metrics.jsonl.
    """
    _ensure_dirs()

    cutoff  = datetime.now(timezone.utc) - timedelta(hours=24)
    texts   = []

    if LIFE_DIR.exists():
        for path in LIFE_DIR.iterdir():
            if path.suffix in (".md", ".json") and \
               path.stat().st_mtime > cutoff.timestamp():
                try:
                    content = path.read_text()
                    if len(content) > 50:
                        texts.append(content)
                except Exception:
                    pass

    if not texts:
        return  # nothing to measure

    # Aggregate metrics across all recent texts
    all_metrics = [measure(t) for t in texts]
    keys = ["self_reference_depth", "integration_score",
            "narrative_coherence", "temporal_depth", "soul_alignment"]

    averaged = {}
    for key in keys:
        vals = [m[key] for m in all_metrics if key in m]
        averaged[key] = round(sum(vals) / len(vals), 4) if vals else 0.0

    # Domain coverage across all texts
    all_domains: set[str] = set()
    for m in all_metrics:
        all_domains.update(m.get("domain_hits", {}).keys())

    snapshot = {
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "texts_sampled": len(texts),
        "domains_seen":  sorted(all_domains),
        **averaged,
    }

    with open(METRICS_FILE, "a") as f:
        f.write(json.dumps(snapshot) + "\n")

    return snapshot


def _load_recent_snapshots(days: int = 14) -> list[dict]:
    """Load snapshots from the last N days."""
    _ensure_dirs()
    if not METRICS_FILE.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    snapshots = []
    for line in METRICS_FILE.read_text().strip().splitlines():
        try:
            s = json.loads(line)
            ts = datetime.fromisoformat(s["timestamp"])
            if ts >= cutoff:
                snapshots.append(s)
        except Exception:
            pass
    return snapshots


def trend(days: int = 14) -> dict:
    """
    Compute trends for each metric over the last N days.
    Returns dict: metric -> {"values": [...], "trend": "up"/"down"/"flat", "latest": float}
    """
    snapshots = _load_recent_snapshots(days)
    if not snapshots:
        return {}

    keys = ["self_reference_depth", "integration_score",
            "narrative_coherence", "temporal_depth", "soul_alignment"]

    result = {}
    for key in keys:
        vals = [s[key] for s in snapshots if key in s]
        if not vals:
            result[key] = {"values": [], "trend": "flat", "latest": 0.0}
            continue

        latest = vals[-1]
        # Trend: compare first third vs last third
        third = max(1, len(vals) // 3)
        early_avg = sum(vals[:third]) / third
        late_avg  = sum(vals[-third:]) / third
        diff      = late_avg - early_avg

        if diff > 0.03:
            trend_dir = "up"
        elif diff < -0.03:
            trend_dir = "down"
        else:
            trend_dir = "flat"

        result[key] = {"values": vals, "trend": trend_dir, "latest": round(latest, 4)}

    return result


def _sparkline(values: list[float], width: int = 10) -> str:
    """Generate a simple ASCII sparkline from a list of 0.0-1.0 values."""
    if not values:
        return "·" * width

    CHARS = "▁▂▃▄▅▆▇█"
    # Sample to width
    if len(values) > width:
        step   = len(values) / width
        values = [values[int(i * step)] for i in range(width)]
    else:
        values = values + [values[-1]] * (width - len(values))

    return "".join(CHARS[min(7, int(v * 8))] for v in values)


def to_prompt_context() -> str:
    """
    Compact summary for LLM prompt injection.
    Shows latest values and overall direction.
    """
    trends = trend(days=7)
    if not trends:
        return ""

    parts = []
    for key in ["self_reference_depth", "integration_score",
                "narrative_coherence", "soul_alignment"]:
        if key in trends:
            t = trends[key]
            label = key.replace("_", "-")[:12]
            arrow = "↑" if t["trend"] == "up" else ("↓" if t["trend"] == "down" else "→")
            parts.append(f"{label}={t['latest']:.2f}{arrow}")

    if not parts:
        return ""

    return "Consciousness metrics: " + ", ".join(parts)


def status(days: int = 14):
    """CLI display with sparklines and trends."""
    G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"
    W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"; M="\033[35m"

    snapshots = _load_recent_snapshots(days)
    trends    = trend(days)

    print(f"\n{B}N.O.V.A Consciousness Metrics{NC}")
    print(f"  {DIM}(Proxy measurements — not a claim, just interesting numbers){NC}")
    print(f"  {len(snapshots)} snapshots over {days} days\n")

    if not snapshots:
        print(f"  {DIM}No data yet. Run 'nova autonomous' to generate activity.{NC}")
        print(f"  {DIM}Or: nova consciousness --measure \"some Nova text\"{NC}")
        return

    metric_labels = {
        "self_reference_depth": "Self-reference depth",
        "integration_score":    "Integration score",
        "narrative_coherence":  "Narrative coherence",
        "temporal_depth":       "Temporal depth",
        "soul_alignment":       "Soul alignment",
    }

    for key, label in metric_labels.items():
        if key not in trends:
            continue
        t     = trends[key]
        vals  = t["values"]
        latest= t["latest"]
        trend_dir = t["trend"]

        spark = _sparkline(vals, width=16)
        arrow = (f"{G}↑ trending up{NC}"   if trend_dir == "up"   else
                 f"{R}↓ trending down{NC}" if trend_dir == "down" else
                 f"{DIM}→ stable{NC}")

        val_col = (G if latest > 0.7 else (Y if latest > 0.4 else DIM))
        bar_len = int(latest * 20)
        bar     = "█" * bar_len + "░" * (20 - bar_len)

        print(f"  {W}{label:<22}{NC}")
        print(f"    {val_col}{bar}{NC} {val_col}{latest:.3f}{NC}  {arrow}")
        print(f"    {DIM}{spark}{NC}")
        print()

    # Latest snapshot domains
    if snapshots:
        latest_snap = snapshots[-1]
        domains = latest_snap.get("domains_seen", [])
        if domains:
            print(f"  {B}Domains in last cycle:{NC} {C}{', '.join(domains)}{NC}")

    # Prompt context preview
    ctx = to_prompt_context()
    if ctx:
        print(f"\n  {DIM}{ctx}{NC}")


def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Consciousness Metrics")
    p.add_argument("--days",    type=int, default=14,
                   help="Number of days to analyze (default: 14)")
    p.add_argument("--measure", metavar="TEXT",
                   help="Measure a specific text and print results")
    p.add_argument("--record",  action="store_true",
                   help="Record a cycle snapshot now")
    p.add_argument("--context", action="store_true",
                   help="Print prompt context string")

    args = p.parse_args()

    G="\033[32m"; C="\033[36m"; Y="\033[33m"
    NC="\033[0m"; B="\033[1m"; DIM="\033[2m"

    if args.measure:
        m = measure(args.measure)
        print(f"\n{B}Measurement Results:{NC}")
        print(f"  Self-reference depth:  {C}{m['self_reference_depth']:.4f}{NC}")
        print(f"  Integration score:     {C}{m['integration_score']:.4f}{NC}")
        print(f"  Narrative coherence:   {C}{m['narrative_coherence']:.4f}{NC}")
        print(f"  Temporal depth:        {C}{m['temporal_depth']:.4f}{NC}")
        print(f"  Soul alignment:        {C}{m['soul_alignment']:.4f}{NC}")
        if m["domain_hits"]:
            print(f"\n  {B}Domains detected:{NC}")
            for dom, hits in sorted(m["domain_hits"].items(), key=lambda x: x[1], reverse=True):
                print(f"    {C}{dom:<15}{NC} {hits} hit(s)")

    elif args.record:
        snap = record_cycle_metrics()
        if snap:
            print(f"{G}Cycle snapshot recorded.{NC}")
            print(f"  self_ref={snap['self_reference_depth']:.3f}  "
                  f"integration={snap['integration_score']:.3f}  "
                  f"coherence={snap['narrative_coherence']:.3f}")
        else:
            print(f"{DIM}No recent texts to measure.{NC}")

    elif args.context:
        ctx = to_prompt_context()
        print(ctx if ctx else "[no consciousness metrics available]")

    else:
        status(days=args.days)


if __name__ == "__main__":
    main()
