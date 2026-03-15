#!/usr/bin/env python3
"""
N.O.V.A Outcome Tracker

Records what Nova acted on, and what actually happened.
This is how she learns from experience — not just pattern matching,
but real feedback loops: what worked, what was noise, what surprised her.

Outcomes feed into Bayesian confidence (signal_weights.json) and
episodic memory (episodes.jsonl) automatically.

Storage: memory/outcomes/outcomes.jsonl
         memory/learning/signal_weights.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE         = Path.home() / "Nova"
OUTCOMES_DIR = BASE / "memory/outcomes"
OUTCOMES_FILE= OUTCOMES_DIR / "outcomes.jsonl"
WEIGHTS_FILE = BASE / "memory/learning/signal_weights.json"

OUTCOMES_DIR.mkdir(parents=True, exist_ok=True)
(BASE / "memory/learning").mkdir(parents=True, exist_ok=True)

VALID_OUTCOMES = {
    "confirmed":    +1,   # real vulnerability confirmed
    "false_positive": -1, # noise, wasted time
    "partial":      +0.5, # real but lower impact than expected
    "informational": 0,   # interesting but not exploitable
    "pending":       None, # acted but no result yet
}


# ── Signal weight store ───────────────────────────────────────────────────────

def _load_weights() -> dict:
    if WEIGHTS_FILE.exists():
        try:
            return json.loads(WEIGHTS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_weights(weights: dict):
    WEIGHTS_FILE.write_text(json.dumps(weights, indent=2))


def get_signal_confidence(signal: str) -> float:
    """
    Return learned P(real | signal) using Laplace smoothing.
    New signals start at 0.5 (neutral — no bias).
    """
    w = _load_weights()
    entry = w.get(signal, {"confirmed": 0, "total": 0})
    confirmed = entry.get("confirmed", 0)
    total     = entry.get("total", 0)
    # Laplace smoothed: (confirmed + 1) / (total + 2)
    return round((confirmed + 1) / (total + 2), 4)


def get_all_weights() -> dict[str, float]:
    """Return confidence for every tracked signal."""
    w = _load_weights()
    return {
        sig: round((e.get("confirmed", 0) + 1) / (e.get("total", 0) + 2), 4)
        for sig, e in w.items()
    }


def _update_weights(signals: list[str], outcome_value: float):
    """Bayesian update: bump confirmed and total counts per signal."""
    if outcome_value is None:
        return
    w = _load_weights()
    for sig in signals:
        if sig not in w:
            w[sig] = {"confirmed": 0, "total": 0}
        w[sig]["total"] += 1
        if outcome_value > 0:
            w[sig]["confirmed"] += outcome_value  # partial = +0.5
    _save_weights(w)


# ── Episodic memory bridge ────────────────────────────────────────────────────

def _reinforce_instinct(signals: list[str], outcome: str):
    """Propagate outcome to instinct layer — closes the feedback loop."""
    try:
        from tools.inner.instinct import reinforce
        reinforce(signals, outcome)
    except Exception:
        pass


def _record_episode(outcome_id: str, host: str, signals: list, outcome: str,
                    confidence: float, note: str):
    """Push significant outcomes into episodic memory."""
    if outcome not in ("confirmed", "false_positive"):
        return
    try:
        _nova_root = str(BASE)
        if _nova_root not in sys.path:
            sys.path.insert(0, _nova_root)
        from tools.learning.episodic_memory import record_episode
        emotion = "pride" if outcome == "confirmed" else "disappointment"
        intensity = min(1.0, confidence + 0.2)
        record_episode(
            event_type = "outcome_" + outcome,
            summary    = f"{'Confirmed' if outcome=='confirmed' else 'False positive'}: {host} — signals {signals}",
            emotion    = emotion,
            intensity  = intensity,
            metadata   = {"outcome_id": outcome_id, "host": host,
                          "signals": signals, "note": note},
        )
    except Exception:
        pass


# ── Core API ──────────────────────────────────────────────────────────────────

def record_action(finding: dict) -> str:
    """
    Call this when Nova decides to 'act' on a finding.
    Returns an outcome_id to reference later when marking the result.
    """
    ts  = datetime.now(timezone.utc).isoformat()
    uid = f"out_{ts[:19].replace(':','-').replace('T','_')}"
    entry = {
        "outcome_id": uid,
        "host":       finding.get("host", ""),
        "path":       finding.get("path", ""),
        "signals":    finding.get("signals", []),
        "confidence": finding.get("confidence", 0),
        "hypothesis": (finding.get("hypotheses") or [{}])[0].get("title", ""),
        "acted_at":   ts,
        "outcome":    "pending",
        "note":       "",
    }
    with open(OUTCOMES_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return uid


def mark_outcome(outcome_id: str, outcome: str, note: str = "") -> bool:
    """
    Mark an outcome as confirmed / false_positive / partial / informational.
    Updates signal weights and episodic memory.
    Returns True if the outcome_id was found and updated.
    """
    if outcome not in VALID_OUTCOMES:
        print(f"[outcomes] Invalid outcome: {outcome}. Valid: {list(VALID_OUTCOMES)}")
        return False

    if not OUTCOMES_FILE.exists():
        return False

    lines = OUTCOMES_FILE.read_text().splitlines()
    updated = False
    host = ""
    signals = []
    confidence = 0.0

    new_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if entry.get("outcome_id") == outcome_id:
                entry["outcome"]    = outcome
                entry["note"]       = note
                entry["resolved_at"]= datetime.now(timezone.utc).isoformat()
                host       = entry.get("host", "")
                signals    = entry.get("signals", [])
                confidence = entry.get("confidence", 0)
                updated    = True
            new_lines.append(json.dumps(entry))
        except Exception:
            new_lines.append(line)

    if updated:
        OUTCOMES_FILE.write_text("\n".join(new_lines) + "\n")
        value = VALID_OUTCOMES[outcome]
        _update_weights(signals, value)
        _reinforce_instinct(signals, outcome)
        _record_episode(outcome_id, host, signals, outcome, confidence, note)

    return updated


def recent_outcomes(n: int = 10) -> list[dict]:
    """Return the n most recent outcomes (newest first)."""
    if not OUTCOMES_FILE.exists():
        return []
    lines = [l.strip() for l in OUTCOMES_FILE.read_text().splitlines() if l.strip()]
    results = []
    for line in reversed(lines):
        try:
            results.append(json.loads(line))
        except Exception:
            pass
        if len(results) >= n:
            break
    return results


def learning_stats() -> dict:
    """Summary of what Nova has learned so far."""
    if not OUTCOMES_FILE.exists():
        return {"total": 0, "confirmed": 0, "false_positives": 0, "pending": 0,
                "accuracy": None, "top_signals": []}

    counts = {"confirmed": 0, "false_positive": 0, "partial": 0,
              "informational": 0, "pending": 0}
    for entry in recent_outcomes(n=10000):
        o = entry.get("outcome", "pending")
        counts[o] = counts.get(o, 0) + 1

    total    = sum(counts.values())
    resolved = counts["confirmed"] + counts["false_positive"] + counts["partial"]
    accuracy = None
    if resolved > 0:
        accuracy = round((counts["confirmed"] + counts["partial"] * 0.5) / resolved, 3)

    # Top 5 signals by learned confidence
    weights = get_all_weights()
    top = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total":         total,
        "confirmed":     counts["confirmed"],
        "false_positives": counts["false_positive"],
        "partial":       counts["partial"],
        "pending":       counts["pending"],
        "accuracy":      accuracy,
        "top_signals":   [{"signal": s, "confidence": c} for s, c in top],
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Outcome Tracker")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("stats", help="Show learning statistics")

    r = sub.add_parser("recent", help="Show recent outcomes")
    r.add_argument("--n", type=int, default=10)

    m = sub.add_parser("mark", help="Mark an outcome")
    m.add_argument("outcome_id")
    m.add_argument("outcome", choices=list(VALID_OUTCOMES))
    m.add_argument("--note", default="")

    w = sub.add_parser("weights", help="Show learned signal weights")

    args = p.parse_args()

    G  = "\033[32m"; R = "\033[31m"; Y = "\033[33m"
    C  = "\033[36m"; W = "\033[97m"; DIM= "\033[2m"; NC = "\033[0m"; B="\033[1m"

    if args.cmd == "stats":
        s = learning_stats()
        print(f"\n{B}N.O.V.A Learning Stats{NC}")
        print(f"  Total outcomes tracked: {W}{s['total']}{NC}")
        acc = f"{s['accuracy']:.1%}" if s['accuracy'] is not None else "n/a"
        print(f"  Accuracy (confirmed+partial): {G}{acc}{NC}")
        print(f"  Confirmed: {G}{s['confirmed']}{NC}  "
              f"False positives: {R}{s['false_positives']}{NC}  "
              f"Pending: {Y}{s['pending']}{NC}")
        if s["top_signals"]:
            print(f"\n  {B}Top signals by learned confidence:{NC}")
            for entry in s["top_signals"]:
                bar = "█" * int(entry["confidence"] * 20)
                print(f"    {C}{entry['signal']:30s}{NC} {G}{bar}{NC} {entry['confidence']:.3f}")

    elif args.cmd == "recent":
        outcomes = recent_outcomes(args.n)
        print(f"\n{B}Recent Outcomes{NC}")
        for o in outcomes:
            oc = o.get("outcome", "pending")
            col = G if oc == "confirmed" else (R if oc == "false_positive" else Y)
            print(f"  {col}[{oc:15s}]{NC}  {W}{o.get('host','')}{o.get('path','')}{NC}")
            print(f"    {DIM}signals: {o.get('signals',[])}  confidence: {o.get('confidence',0):.2f}{NC}")
            if o.get("note"):
                print(f"    note: {o['note']}")

    elif args.cmd == "mark":
        ok = mark_outcome(args.outcome_id, args.outcome, args.note)
        if ok:
            print(f"{G}Marked {args.outcome_id} as {args.outcome}{NC}")
        else:
            print(f"{R}outcome_id not found: {args.outcome_id}{NC}")
            sys.exit(1)

    elif args.cmd == "weights":
        weights = get_all_weights()
        if not weights:
            print(f"{DIM}No signal weights learned yet.{NC}")
            return
        print(f"\n{B}Learned Signal Weights{NC}")
        for sig, conf in sorted(weights.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * int(conf * 20)
            col = G if conf > 0.6 else (Y if conf > 0.4 else R)
            print(f"  {C}{sig:35s}{NC} {col}{bar}{NC} {conf:.3f}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
