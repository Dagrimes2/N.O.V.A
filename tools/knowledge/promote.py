#!/usr/bin/env python3
import json
import sys
import os
import time
import hashlib
from pathlib import Path

BASE = Path.home() / "Nova"
QUEUE_DIR = BASE / "knowledge" / "queue"

def fingerprint(entry):
    base = f"{entry.get('host')}|{entry.get('path')}|{sorted(entry.get('signals', []))}"
    return hashlib.sha256(base.encode()).hexdigest()

def already_exists(fp):
    for f in QUEUE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if data.get("fingerprint") == fp:
                return True
        except:
            continue
    return False

def main():
    os.makedirs(QUEUE_DIR, exist_ok=True)

    for line in sys.stdin:
        r = json.loads(line)

        fp = fingerprint(r)

        if already_exists(fp):
            print(json.dumps(r))
            continue

        promote = {
            "timestamp": time.time(),
            "host": r.get("host"),
            "path": r.get("path"),
            "confidence": r.get("triage", {}).get("confidence_adjusted", 0),
            "decision": r.get("reflection", {}).get("decision"),
            "reason": r.get("reflection", {}).get("reason"),
            "source": r.get("source"),
            "fingerprint": fp,
            "raw": r,
            "accepted": False,
            "status": "awaiting_human_review"
        }

        fname = f"{int(time.time()*1000)}.json"
        with open(QUEUE_DIR / fname, "w") as f:
            json.dump(promote, f, indent=2)

        r["knowledge_promotion"] = {
            "accepted": False,
            "queued": True,
            "fingerprint": fp
        }

        print(json.dumps(r))

if __name__ == "__main__":
    main()
