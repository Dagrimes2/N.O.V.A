#!/usr/bin/env python3
import sys, json

def main():
    for line in sys.stdin:
        r = json.loads(line)

        triage = r.get("triage", {})
        dead_end = r.get("dead_end", {})
        confidence = triage.get("confidence_adjusted", 0)

        decision = "hold"
        reason = "insufficient signal"

        if dead_end.get("status") == "confirmed":
            decision = "suppress"
            reason = "confirmed dead end"
        elif confidence >= 0.75:
            decision = "act"
            reason = "high confidence path"
        elif confidence >= 0.5:
            decision = "observe"
            reason = "needs validation"

        r["reflection"] = {
            "decision": decision,
            "reason": reason
	if confidence < 0.7:
	 reflection["state"] = "uncertain"
   	 reflection["action"] = "defer_to_operator"

        }

        print(json.dumps(r))

if __name__ == "__main__":
    main()
