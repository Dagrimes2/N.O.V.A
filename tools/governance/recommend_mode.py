#!/usr/bin/env python3
import json
import sys

def main():
    for line in sys.stdin:
        r = json.loads(line)

        confidence = r.get("confidence", 0)
        signals = len(r.get("signals", []))
        status = r.get("submission_status")

        recommendation = None
        reason = None

        if confidence >= 0.6 and signals >= 2 and status == "REVIEW":
            recommendation = "expansion"
            reason = "High confidence with multiple signals detected"

        if confidence >= 0.75 and status == "READY":
            recommendation = "submission"
            reason = "Strong confidence and ready for reporting"

        if recommendation:
            r["mode_recommendation"] = {
                "suggested": recommendation,
                "reason": reason
            }

        print(json.dumps(r))

if __name__ == "__main__":
    main()
