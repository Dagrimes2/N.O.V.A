#!/usr/bin/env python3

import sys
import json
import yaml
import datetime
from pathlib import Path

POLICY_PATH = Path.home() / "Nova/core/dead_end_policy.yaml"
DEAD_ENDS_PATH = Path.home() / "Nova/memory/dead_ends/dead_ends.json"

def load_policy():
    with open(POLICY_PATH) as f:
        return yaml.safe_load(f)

def load_dead_ends():
    if DEAD_ENDS_PATH.exists():
        with open(DEAD_ENDS_PATH) as f:
            return json.load(f)
    return {"entries": []}

def save_dead_ends(data):
    DEAD_ENDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEAD_ENDS_PATH, "w") as f:
        json.dump(data, f, indent=2)

def should_suggest_dead_end(record, policy):
    attempts = record.get("attempts", 0)
    confidence = record.get("confidence", 1.0)

    thresholds = policy["thresholds"]

    if attempts < thresholds["min_attempts"]:
        return False

    if confidence >= thresholds["min_confidence_below"]:
        return False

    return True

def promote_dead_end(record, policy):
    now = datetime.datetime.now(datetime.UTC)
    revisit = now + datetime.timedelta(
        hours=policy["cooldown"]["allow_revisit_after_hours"]
    )

    return {
        "target": f"{record.get('host')}{record.get('path')}",
        "promoted_at": now.isoformat(),
        "reason": "Confidence consistently below threshold with repeated attempts",
        "evidence": {
            "attempts": record.get("attempts"),
            "confidence": record.get("confidence"),
            "signals": record.get("signals", []),
            "status": record.get("status")
        },
        "revisit_after": revisit.isoformat(),
        "override_allowed": True
    }

def main():
    policy = load_policy()
    dead_ends = load_dead_ends()

    for line in sys.stdin:
        record = json.loads(line)

        record.setdefault("dead_end", {"status": "clear"})

        if not policy["auto_promote"]["enabled"]:
            print(json.dumps(record))
            continue

        if should_suggest_dead_end(record, policy):
            entry = promote_dead_end(record, policy)
            dead_ends["entries"].append(entry)
            record["dead_end"]["status"] = "promoted"
            record["dead_end"]["reason"] = entry["reason"]
        else:
            record["dead_end"]["status"] = "clear"

        print(json.dumps(record))

    save_dead_ends(dead_ends)

if __name__ == "__main__":
    main()
