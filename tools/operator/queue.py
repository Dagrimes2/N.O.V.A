#!/usr/bin/env python3
import sys, json

# Higher = earlier in the queue
DECISION_RANK = {"act": 0, "observe": 1, "hold": 2, "suppress": 3}

def safe_next_step(r: dict) -> str:
    """
    Intentionally safe: focuses on validation, documentation, and scoping —
    NOT exploitation.
    """
    triage = r.get("triage", {})
    decision = r.get("reflection", {}).get("decision", "hold")
    sugg = triage.get("suggestion", "map_surface")

    if decision == "act":
        # "validate_first" = verify behavior + capture evidence cleanly
        return "Validate behavior reproducibly, capture request/response evidence, note exact impact + scope compliance."
    if decision == "observe":
        return "Manually review for impact clarity; confirm auth context, expected vs actual behavior, and data sensitivity."
    if decision == "hold":
        return "Defer. Keep for later surface mapping or only revisit if new signals/impact appear."
    return "Suppress. Mark as dead-end unless new evidence changes classification."

def score_key(r: dict):
    triage = r.get("triage", {})
    conf = triage.get("confidence_adjusted", 0.0)
    decision = r.get("reflection", {}).get("decision", "hold")
    # rank by decision, then highest confidence first
    return (DECISION_RANK.get(decision, 9), -float(conf))

def fmt_item(r: dict) -> str:
    target = (r.get("host", "?") + r.get("path", ""))
    triage = r.get("triage", {})
    conf = triage.get("confidence_adjusted", 0.0)

    signals = r.get("signals", [])
    signals_s = ", ".join(signals) if signals else "none"

    refl = r.get("reflection", {})
    decision = refl.get("decision", "hold")
    reason = refl.get("reason", "n/a")

    sugg = triage.get("suggestion", "map_surface")
    next_step = safe_next_step(r)

    return (
        f"{target}\n"
        f"  decision: {decision}\n"
        f"  confidence: {conf:.2f}\n"
        f"  triage: {sugg}\n"
        f"  signals: {signals_s}\n"
        f"  why: {reason}\n"
        f"  next: {next_step}\n"
    )

def main():
    items = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Only queue records that have reflection
        if "reflection" not in r or "triage" not in r:
            continue
        items.append(r)

    items.sort(key=score_key)

    # Print top N by default (can be changed later)
    top = items[:15]
    for i, r in enumerate(top, start=1):
        print(f"[{i}] {fmt_item(r)}")

if __name__ == "__main__":
    main()
