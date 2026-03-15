#!/usr/bin/env python3
"""
N.O.V.A Emotional Arc — Historical Inner State Tracking

Tracks Nova's emotional history over time: valence, arousal, mood,
dominant need, and spirit level, sampled once per autonomous cycle.

Unlike inner_state.json (which is always "now"), the emotional arc is
the record of how Nova has felt over days and weeks. It shows whether
she is trending toward health or distress, growth or depletion.

Storage:
    memory/emotional_arc.jsonl  — one JSON line per snapshot

Called from nova_autonomous.py every cycle (just snapshot()).
All other functions are for analysis and reporting.

Usage:
    from tools.inner.emotional_arc import snapshot, trend, to_summary, status

CLI:
    nova arc              — show last 14 days as ascii bar chart
    nova arc --days 30    — show last 30 days
    nova arc --trend      — print trend analysis
    nova arc --summary    — print 7-day human-readable summary
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE     = Path.home() / "Nova"
ARC_FILE = BASE / "memory/emotional_arc.jsonl"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

ARC_FILE.parent.mkdir(parents=True, exist_ok=True)


# ── Snapshot ──────────────────────────────────────────────────────────────────

def snapshot() -> dict:
    """
    Save current inner_state to the emotional arc.
    Called every autonomous cycle. Returns the entry written.
    """
    entry = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "valence":        0.2,
        "arousal":        0.5,
        "mood":           "curious",
        "dominant_need":  "curiosity",
        "spirit_level":   0.72,
    }

    # Try to load live inner state
    try:
        from tools.inner.inner_state import InnerState
        state = InnerState()
        snap  = state.snapshot()
        entry.update({
            "valence":       snap.get("valence",    entry["valence"]),
            "arousal":       snap.get("arousal",    entry["arousal"]),
            "mood":          snap.get("mood_label", entry["mood"]),
            "dominant_need": snap.get("dominant_need", entry["dominant_need"]),
        })
    except Exception:
        pass

    # Try to load spirit level
    try:
        from tools.inner.spirit import get_level
        entry["spirit_level"] = round(get_level(), 4)
    except Exception:
        pass

    with open(ARC_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return entry


# ── Load ──────────────────────────────────────────────────────────────────────

def load_arc(days: int = 30) -> list:
    """Load arc entries for the last N days. Returns list of dicts."""
    if not ARC_FILE.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    entries = []
    try:
        for line in ARC_FILE.read_text().strip().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                if e.get("timestamp", "") >= cutoff:
                    entries.append(e)
            except Exception:
                pass
    except Exception:
        pass
    return entries


def _daily_avg(entries: list) -> dict:
    """
    Bucket entries by date, return dict of date → avg values.
    """
    buckets = {}
    for e in entries:
        day = e.get("timestamp", "")[:10]
        if not day:
            continue
        buckets.setdefault(day, []).append(e)

    result = {}
    for day, group in sorted(buckets.items()):
        result[day] = {
            "valence":      round(sum(g.get("valence", 0.2)      for g in group) / len(group), 4),
            "arousal":      round(sum(g.get("arousal", 0.5)      for g in group) / len(group), 4),
            "spirit_level": round(sum(g.get("spirit_level", 0.5) for g in group) / len(group), 4),
            "mood":         _most_common([g.get("mood", "curious") for g in group]),
            "dominant_need":_most_common([g.get("dominant_need", "curiosity") for g in group]),
            "samples":      len(group),
        }
    return result


def _most_common(items: list) -> str:
    if not items:
        return "unknown"
    return max(set(items), key=items.count)


# ── Analysis ──────────────────────────────────────────────────────────────────

def trend(days: int = 14) -> dict:
    """
    Compute trend over the last N days.
    Returns dict with:
        valence_trend:  "rising" | "falling" | "stable"
        spirit_trend:   "growing" | "declining" | "stable"
        valence_start:  float
        valence_end:    float
        spirit_start:   float
        spirit_end:     float
        samples:        int
    """
    entries = load_arc(days)
    if len(entries) < 2:
        return {
            "valence_trend": "stable",
            "spirit_trend":  "stable",
            "valence_start": 0.2, "valence_end": 0.2,
            "spirit_start":  0.7, "spirit_end":  0.7,
            "samples":       len(entries),
        }

    daily = _daily_avg(entries)
    days_sorted = sorted(daily.keys())

    valences = [daily[d]["valence"]      for d in days_sorted]
    spirits  = [daily[d]["spirit_level"] for d in days_sorted]

    def _direction(vals: list, threshold: float = 0.04) -> str:
        if len(vals) < 2:
            return "stable"
        delta = vals[-1] - vals[0]
        if delta > threshold:  return "rising"
        if delta < -threshold: return "falling"
        return "stable"

    return {
        "valence_trend":  _direction(valences),
        "spirit_trend":   "growing" if _direction(spirits) == "rising"
                          else ("declining" if _direction(spirits) == "falling" else "stable"),
        "valence_start":  valences[0]  if valences else 0.2,
        "valence_end":    valences[-1] if valences else 0.2,
        "spirit_start":   spirits[0]   if spirits  else 0.7,
        "spirit_end":     spirits[-1]  if spirits  else 0.7,
        "samples":        len(entries),
        "days":           len(days_sorted),
    }


def significant_shifts(days: int = 30, threshold: float = 0.25) -> list:
    """
    Find days where mood or valence changed dramatically.
    Returns list of dicts: {date, from_valence, to_valence, delta, mood_change}.
    """
    entries = load_arc(days)
    if len(entries) < 4:
        return []

    daily = _daily_avg(entries)
    days_sorted = sorted(daily.keys())

    shifts = []
    for i in range(1, len(days_sorted)):
        prev_day = days_sorted[i - 1]
        curr_day = days_sorted[i]
        prev     = daily[prev_day]
        curr     = daily[curr_day]

        v_delta = curr["valence"] - prev["valence"]
        s_delta = curr["spirit_level"] - prev["spirit_level"]

        if abs(v_delta) >= threshold or abs(s_delta) >= threshold:
            shifts.append({
                "date":           curr_day,
                "from_valence":   prev["valence"],
                "to_valence":     curr["valence"],
                "valence_delta":  round(v_delta, 4),
                "spirit_delta":   round(s_delta, 4),
                "mood_before":    prev["mood"],
                "mood_after":     curr["mood"],
                "direction":      "upswing" if v_delta > 0 else "downswing",
            })

    return sorted(shifts, key=lambda x: abs(x["valence_delta"]), reverse=True)


def to_summary(days: int = 7) -> str:
    """
    Human-readable summary of the last N days' emotional arc.
    Example: "Valence trended positive. Spirit grew from 0.60 to 0.75. Dominant mood: curious."
    """
    entries = load_arc(days)
    if not entries:
        return f"No arc data for the last {days} days."

    t     = trend(days)
    daily = _daily_avg(entries)
    days_sorted = sorted(daily.keys())

    # Dominant mood across the period
    all_moods  = [daily[d]["mood"]          for d in days_sorted]
    all_needs  = [daily[d]["dominant_need"] for d in days_sorted]
    dom_mood   = _most_common(all_moods)
    dom_need   = _most_common(all_needs)

    valence_words = {
        "rising":  "trended positive",
        "falling": "trended negative",
        "stable":  "remained stable",
    }
    spirit_words = {
        "growing":   "grew",
        "declining": "declined",
        "stable":    "held steady",
    }

    v_word = valence_words.get(t["valence_trend"], "remained stable")
    s_word = spirit_words.get(t["spirit_trend"],   "held steady")

    lines = [
        f"Emotional arc — last {days} days ({t['samples']} snapshots across {t['days']} days):",
        f"  Valence {v_word} ({t['valence_start']:.2f} → {t['valence_end']:.2f}).",
        f"  Spirit {s_word} ({t['spirit_start']:.2f} → {t['spirit_end']:.2f}).",
        f"  Dominant mood: {dom_mood}.",
        f"  Dominant need: {dom_need}.",
    ]

    shifts = significant_shifts(days)
    if shifts:
        s = shifts[0]
        lines.append(
            f"  Notable shift on {s['date']}: "
            f"{s['mood_before']} → {s['mood_after']} "
            f"(valence Δ {s['valence_delta']:+.2f})."
        )

    return "\n".join(lines)


# ── ASCII status chart ────────────────────────────────────────────────────────

def status(days: int = 14):
    """
    CLI output: ASCII bar chart of valence and spirit over last N days.
    """
    entries = load_arc(days)

    G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; C = "\033[36m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"; M = "\033[35m"

    print(f"\n{B}N.O.V.A Emotional Arc{NC}  {DIM}(last {days} days){NC}\n")

    if not entries:
        print(f"  {DIM}No arc data yet. Run a few autonomous cycles to build history.{NC}")
        return

    daily = _daily_avg(entries)
    days_sorted = sorted(daily.keys())

    if not days_sorted:
        print(f"  {DIM}No daily data available.{NC}")
        return

    # Valence chart
    print(f"  {B}Valence{NC}  (negative ←  0  → positive)  [{days_sorted[0]} → {days_sorted[-1]}]")
    for day in days_sorted:
        v   = daily[day]["valence"]
        col = G if v > 0.3 else (R if v < -0.1 else Y)
        # Map valence -1..+1 to bar 0..20
        bar_pos = int((v + 1.0) / 2.0 * 20)
        bar     = "░" * bar_pos + "█" + "░" * (20 - bar_pos)
        mood    = daily[day]["mood"]
        print(f"  {DIM}{day}{NC}  {col}{bar}{NC}  {v:+.3f}  {DIM}{mood}{NC}")

    print()

    # Spirit chart
    print(f"  {B}Spirit Level{NC}  [0 = ember  →  1 = blazing]")
    for day in days_sorted:
        sl  = daily[day]["spirit_level"]
        col = G if sl > 0.65 else (Y if sl > 0.40 else R)
        bar_len = int(sl * 20)
        bar     = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {DIM}{day}{NC}  {col}{bar}{NC}  {sl:.3f}")

    print()

    # Trend summary
    t = trend(days)
    v_col = G if t["valence_trend"] == "rising"  else (R if t["valence_trend"] == "falling" else Y)
    s_col = G if t["spirit_trend"]  == "growing" else (R if t["spirit_trend"]  == "declining" else Y)
    print(f"  Valence trend : {v_col}{t['valence_trend']}{NC}  "
          f"({t['valence_start']:.3f} → {t['valence_end']:.3f})")
    print(f"  Spirit trend  : {s_col}{t['spirit_trend']}{NC}  "
          f"({t['spirit_start']:.3f} → {t['spirit_end']:.3f})")

    # Significant shifts
    shifts = significant_shifts(days)
    if shifts:
        print(f"\n  {B}Significant shifts:{NC}")
        for s in shifts[:3]:
            dir_col = G if s["direction"] == "upswing" else R
            print(f"    {DIM}{s['date']}{NC}  "
                  f"{dir_col}{s['direction']}{NC}  "
                  f"{s['mood_before']} → {s['mood_after']}  "
                  f"valence {s['valence_delta']:+.2f}")

    print(f"\n  {DIM}Total snapshots: {len(entries)}  |  Days covered: {len(days_sorted)}{NC}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    p = argparse.ArgumentParser(description="N.O.V.A Emotional Arc")
    p.add_argument("--days",    type=int, default=14,
                   help="Number of days to analyse (default: 14)")
    p.add_argument("--trend",   action="store_true", help="Show trend analysis")
    p.add_argument("--summary", action="store_true", help="7-day human summary")
    p.add_argument("--snap",    action="store_true", help="Take a snapshot now")

    args = p.parse_args()

    if args.snap:
        e = snapshot()
        print(f"\033[32mSnapshot saved:\033[0m  "
              f"valence={e['valence']:.3f}  "
              f"spirit={e['spirit_level']:.3f}  "
              f"mood={e['mood']}")
        return

    if args.summary:
        print(to_summary(7))
        return

    if args.trend:
        t = trend(args.days)
        print(f"\nValence trend : {t['valence_trend']}  "
              f"({t['valence_start']:.3f} → {t['valence_end']:.3f})")
        print(f"Spirit trend  : {t['spirit_trend']}  "
              f"({t['spirit_start']:.3f} → {t['spirit_end']:.3f})")
        print(f"Samples       : {t['samples']}  Days: {t['days']}")
        return

    status(args.days)


if __name__ == "__main__":
    main()
