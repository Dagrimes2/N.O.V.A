#!/usr/bin/env python3
"""
Nova Phase 5.6 — Memory-Aware Scoring

Adjusts scores using learned memory.
"""

import json
import sys
from pathlib import Path

STORE = Path(__file__).parents[1] / "memory" / "store.json"

MEMORY = json.loads(STORE.read_text())

def main():
    for line in sys.stdin:
        record = json.loads(line)
        score = record.get("score", 0)

        host = record.get("host")
        path = record.get("path", "/")
        key = f"{host}{path}"

        # 📍 Path memory influence
        path_mem = MEMORY["paths"].get(key)
        if path_mem:
            seen = path_mem["seen"]
            confirmed = path_mem["confirmed"]

            if confirmed > 0:
                score += 3
            elif seen >= 3:
                score -= 2

        # 🧠 Signal influence
        for sig in record.get("signals", []):
            sig_mem = MEMORY["signals"].get(sig)
            if sig_mem and sig_mem["confirmed"] > 0:
                score += 2

        record["score"] = max(score, 0)
        record["memory_adjusted"] = True

        print(json.dumps(record))

if __name__ == "__main__":
    main()
