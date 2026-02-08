#!/usr/bin/env python3
import sys, json

MIN_CONF = 0.75

def main():
    for line in sys.stdin:
        r = json.loads(line)

        status = r.get("submission_status")
        confidence = r.get("triage", {}).get("confidence_adjusted", 0)
        decision = r.get("reflection", {}).get("decision")

        if status == "READY" and decision == "act" and confidence >= MIN_CONF:
            print(json.dumps({
                "target": r["host"] + r["path"],
                "confidence": confidence,
                "signals": r.get("signals", []),
                "why": r.get("reflection", {}).get("why"),
                "next": r.get("reflection", {}).get("next")
            }))
