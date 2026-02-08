#!/usr/bin/env python3
import json
import sys

def poc_for_record(r):
    host = r["host"]
    path = r["path"]
    method = r["method"]
    status = r.get("status", "unknown")

    steps = []

    steps.append(f"1. Navigate to `{host}{path}` using an unauthenticated session.")
    steps.append(f"2. Send a {method} request to the endpoint.")
    steps.append(f"3. Observe the HTTP response status: `{status}`.")

    for pb in r.get("playbooks", []):
        for cmd in pb.get("commands", []):
            steps.append(f"- `{cmd}`")

    return {
        "title": f"Potential access control issue at {host}{path}",
        "steps": steps,
        "expected": "Access should be denied or properly authorized.",
        "actual": "The endpoint responds in a way that suggests insufficient access control.",
        "impact": r.get("note", "")
    }

def main():
    for line in sys.stdin:
        r = json.loads(line)

        if r.get("submission_status") not in ("REVIEW", "READY", "READY_CHAIN"):
            continue

        poc = poc_for_record(r)
        r["poc"] = poc
        print(json.dumps(r))

if __name__ == "__main__":
    main()
