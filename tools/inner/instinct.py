#!/usr/bin/env python3
"""
N.O.V.A Instinct Layer

Pre-deliberation reflexes that fire before LLM reasoning.
Built from Bayesian signal weights — patterns Nova has confirmed enough
times that they no longer need full deliberation. She just *knows*.

Like a seasoned security researcher whose hands move before their
conscious mind finishes the thought.

How it works:
  1. Score a finding against learned instinct thresholds
  2. If confidence > INSTINCT_THRESHOLD → return instinct decision instantly
  3. If instinct and later deliberation disagree → log the tension
  4. Instincts strengthen with confirmations, weaken with false positives

Thresholds:
  > 0.85  — strong instinct: act immediately, skip full pipeline
  > 0.70  — weak instinct: lean toward act, still deliberate
  < 0.35  — suppression instinct: likely noise, skip
  else    — no instinct, full deliberation

Storage: memory/learning/instincts.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE           = Path.home() / "Nova"
INSTINCTS_FILE = BASE / "memory/learning/instincts.json"
TENSION_FILE   = BASE / "memory/learning/instinct_tensions.jsonl"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

INSTINCT_THRESHOLD_STRONG = 0.85
INSTINCT_THRESHOLD_WEAK   = 0.70
INSTINCT_SUPPRESS         = 0.35


def _load_instincts() -> dict:
    if INSTINCTS_FILE.exists():
        try:
            return json.loads(INSTINCTS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_instincts(data: dict):
    INSTINCTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    INSTINCTS_FILE.write_text(json.dumps(data, indent=2))


def _signal_key(signals: list[str]) -> str:
    """Canonical key for a signal combination."""
    return "|".join(sorted(signals))


# ── Core instinct scoring ─────────────────────────────────────────────────────

def instinct_score(signals: list[str], confidence: float = 0.0) -> dict:
    """
    Given signals and a base confidence, return instinct assessment.

    Returns:
        {
          "fires": bool,           # True if instinct is strong enough to act
          "direction": str,        # "act" | "suppress" | "observe" | "none"
          "strength": float,       # 0.0-1.0
          "source": str,           # "strong_instinct"|"weak_instinct"|"suppression"|"none"
          "signal_key": str,
        }
    """
    if not signals:
        return {"fires": False, "direction": "none", "strength": 0.0,
                "source": "none", "signal_key": ""}

    # Pull Bayesian weights for each signal
    try:
        from tools.learning.outcome_tracker import get_signal_confidence
        weights = [get_signal_confidence(s) for s in signals]
        learned = sum(weights) / len(weights)
    except Exception:
        learned = confidence  # fall back to raw confidence

    # Blend with raw confidence (80% learned, 20% raw)
    blended = 0.8 * learned + 0.2 * confidence
    blended = round(min(1.0, max(0.0, blended)), 4)

    # Check combo instinct (specific signal patterns we've learned)
    combo_key = _signal_key(signals)
    instincts  = _load_instincts()
    combo_data = instincts.get(combo_key, {})
    combo_conf = combo_data.get("confidence", blended)

    # Combo instinct overrides individual if we have enough data
    if combo_data.get("total", 0) >= 3:
        final = 0.6 * combo_conf + 0.4 * blended
    else:
        final = blended

    final = round(final, 4)

    if final >= INSTINCT_THRESHOLD_STRONG:
        return {"fires": True, "direction": "act", "strength": final,
                "source": "strong_instinct", "signal_key": combo_key}
    elif final >= INSTINCT_THRESHOLD_WEAK:
        return {"fires": True, "direction": "act", "strength": final,
                "source": "weak_instinct", "signal_key": combo_key}
    elif final <= INSTINCT_SUPPRESS:
        return {"fires": True, "direction": "suppress", "strength": 1.0 - final,
                "source": "suppression_instinct", "signal_key": combo_key}
    else:
        return {"fires": False, "direction": "none", "strength": final,
                "source": "none", "signal_key": combo_key}


def check_finding(finding: dict) -> Optional[dict]:
    """
    Check a finding against instincts. Returns instinct result if it fires,
    None if full deliberation is needed.

    This is the gate — call this BEFORE hypothesize/reflect.
    If it returns something, skip the LLM pipeline.
    """
    signals    = finding.get("signals", [])
    confidence = float(finding.get("confidence", 0))
    result     = instinct_score(signals, confidence)

    if result["fires"]:
        return {
            "decision":  result["direction"],
            "reason":    f"Instinct ({result['source']}, strength={result['strength']:.3f}): "
                         f"signals {signals} pattern is well-established",
            "state":     "instinctive",
            "action":    f"act on {finding.get('host','')}{finding.get('path','')}",
            "instinct":  result,
            "skipped_llm": True,
        }
    return None


# ── Reinforcement learning ────────────────────────────────────────────────────

def reinforce(signals: list[str], outcome: str):
    """
    Strengthen or weaken a signal combo instinct based on outcome.
    outcome: "confirmed" | "false_positive" | "partial"
    """
    combo_key = _signal_key(signals)
    instincts = _load_instincts()

    if combo_key not in instincts:
        instincts[combo_key] = {
            "signals":    signals,
            "confirmed":  0,
            "total":      0,
            "confidence": 0.5,
        }

    entry = instincts[combo_key]
    entry["total"] += 1

    if outcome == "confirmed":
        entry["confirmed"] += 1
        delta = +0.1
    elif outcome == "false_positive":
        delta = -0.15   # punish harder than reward — avoids false confidence
    elif outcome == "partial":
        entry["confirmed"] += 0.5
        delta = +0.03
    else:
        delta = 0.0

    entry["confidence"] = round(
        min(1.0, max(0.0, entry["confidence"] + delta)), 4
    )
    entry["last_updated"] = datetime.now(timezone.utc).isoformat()
    instincts[combo_key] = entry
    _save_instincts(instincts)


def log_tension(signals: list[str], instinct_dir: str, llm_dir: str,
                host: str = "", path: str = ""):
    """
    Log when instinct and LLM deliberation disagree.
    These are the most valuable learning moments.
    """
    TENSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts":           datetime.now(timezone.utc).isoformat(),
        "signals":      signals,
        "instinct":     instinct_dir,
        "deliberation": llm_dir,
        "host":         host,
        "path":         path,
        "resolved":     False,
    }
    with open(TENSION_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def all_instincts() -> list[dict]:
    """Return all learned instincts sorted by confidence."""
    data = _load_instincts()
    items = list(data.values())
    return sorted(items, key=lambda x: x.get("confidence", 0), reverse=True)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Instinct Layer")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("list", help="Show all learned instincts")

    c = sub.add_parser("check", help="Check signals against instincts")
    c.add_argument("signals", nargs="+")
    c.add_argument("--confidence", type=float, default=0.5)

    r = sub.add_parser("reinforce", help="Reinforce signal combo")
    r.add_argument("outcome", choices=["confirmed", "false_positive", "partial"])
    r.add_argument("signals", nargs="+")

    args = p.parse_args()

    G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"
    W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"

    if args.cmd == "list":
        instincts = all_instincts()
        if not instincts:
            print(f"{DIM}No instincts learned yet. They emerge from confirmed outcomes.{NC}")
            return
        print(f"\n{B}Learned Instincts ({len(instincts)}){NC}\n")
        for inst in instincts:
            conf = inst.get("confidence", 0)
            col = G if conf >= INSTINCT_THRESHOLD_STRONG else \
                  Y if conf >= INSTINCT_THRESHOLD_WEAK else \
                  R if conf <= INSTINCT_SUPPRESS else DIM
            bar = "█" * int(conf * 20)
            status = ("STRONG" if conf >= INSTINCT_THRESHOLD_STRONG else
                      "WEAK"   if conf >= INSTINCT_THRESHOLD_WEAK   else
                      "SUPPRESS" if conf <= INSTINCT_SUPPRESS        else "latent")
            print(f"  {col}[{status:8s}]{NC} {W}{', '.join(inst['signals'][:4])}{NC}")
            print(f"           {col}{bar}{NC} {conf:.3f}  "
                  f"({inst.get('confirmed',0)}/{inst.get('total',0)} confirmed)")

    elif args.cmd == "check":
        result = instinct_score(args.signals, args.confidence)
        col = G if result["direction"] == "act" else \
              R if result["direction"] == "suppress" else DIM
        fires = f"{G}FIRES{NC}" if result["fires"] else f"{DIM}no fire{NC}"
        print(f"\n{B}Instinct check:{NC} {fires}")
        print(f"  Signals:   {W}{args.signals}{NC}")
        print(f"  Direction: {col}{result['direction']}{NC}")
        print(f"  Strength:  {result['strength']:.4f}")
        print(f"  Source:    {DIM}{result['source']}{NC}")

    elif args.cmd == "reinforce":
        reinforce(args.signals, args.outcome)
        col = G if args.outcome == "confirmed" else R
        print(f"{col}Reinforced [{args.outcome}]:{NC} {args.signals}")

    else:
        p.print_help()


if __name__ == "__main__":
    main()
