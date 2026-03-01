#!/usr/bin/env python3
import json
import sys

def main():
    for line in sys.stdin:
        r = json.loads(line)

        r["quarantine"] = True  # top-level, explicit
        r["external_intel"] = {
            "accepted": False,
            "reason": "external source requires human validation",
            "source": r.get("source", "unknown")
        }

        print(json.dumps(r))

if __name__ == "__main__":
    main()

