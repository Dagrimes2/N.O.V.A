#!/usr/bin/env python3
"""
Nova Phase 7.2 — Pattern Memory v1

- Reads records from stdin
- Applies small confidence nudges based on prior confirmed patterns
- Does NOT approve or block anything
- Offline-first, human-driven learning

Memory file:
~/Nova/memory/patterns/patterns.json
"""

import json
import sys
from pathlib import Path

MEMORY_PATH = Path.home() / "Nova/memory/patterns/patterns.json"

CONFIRM_BOOST = 0.08
INVALID_PENALTY = 0.10


def load_memory():
    if MEMORY_PATH.exists():
        return json.loads(MEMORY_PATH.read_text())
    return {"patterns": []}


def adjust_confidence(base, category, signals, memory):
    conf = base
    for p in memory["patterns"]:
        if p["category"] == category and any(s in signals for s in p["signals"]):
            if p["outcome"] == "confirmed":
                conf += CONFIRM_BOOST
            elif p["outcome"] == "invalid":
                conf -= INVALID_PENALTY
    return max(0.0, min(1.0, conf))


def main():
    memory = load_memory()

    for line in sys.stdin:
        record = json.loads(line)

        base = record.get("triage", {}).get("confidence_adjusted",
                                            record.get("confidence", 0.2))

        hypotheses = record.get("hypotheses", [])
        if hypotheses:
            category = hypotheses[0]["category"]
        else:
            category = "unknown"

        signals = record.get("signals", []) or []

        new_conf = adjust_confidence(base, category, signals, memory)

        record.setdefault("learning", {})
        record["learning"]["confidence_after_memory"] = round(new_conf, 2)
        record["learning"]["memory_applied"] = True

        print(json.dumps(record))


if __name__ == "__main__":
    main()
