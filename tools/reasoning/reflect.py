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
        state = "stable"
        action = "none"

        if dead_end.get("status") == "confirmed":
            decision = "suppress"
            reason = "confirmed dead end"
            state = "resolved"
        elif confidence >= 0.75:
            decision = "act"
            reason = "high confidence path"
        elif confidence >= 0.5:
            decision = "observe"
            reason = "needs validation"
            state = "uncertain"
            action = "defer_to_operator"
        else:
            state = "uncertain"
            action = "defer_to_operator"

        r["reflection"] = {
            "decision": decision,
            "reason": reason,
            "state": state,
            "action": action
        }

        print(json.dumps(r))

if __name__ == "__main__":
    main()
