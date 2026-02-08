#!/usr/bin/env python3
import json
import yaml
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
CORE = BASE / "core"
MEMORY = BASE / "tools/memory/store.json"

READY_CONFIDENCE = 0.75

def load_program():
    with open(CORE / "active_program.yaml") as f:
        platform = yaml.safe_load(f)["platform"]
    with open(CORE / "programs" / f"{platform}.yaml") as f:
        return yaml.safe_load(f)

def load_memory():
    with open(MEMORY) as f:
        return json.load(f)

def main():
    program = load_program()
    memory = load_memory()

    for line in sys.stdin:
        r = json.loads(line)
        key = f"{r['host']}{r['path']}"
        mem = memory["paths"].get(key, {})

        confidence = r.get("confidence", 0)
        confirmed = mem.get("confirmed", 0)
        signals = set(r.get("signals", []))

        allowed = set(program.get("prioritize_signals", []))
        deprior = set(program.get("deprioritize_signals", []))

        verdict = "HOLD"

        if confidence >= READY_CONFIDENCE and signals & allowed:
            verdict = "READY"
        elif confidence >= 0.5 and not signals & deprior:
            verdict = "REVIEW"

        r["submission_status"] = verdict
        print(json.dumps(r))

if __name__ == "__main__":
    main()
