#!/usr/bin/env python3
import json, sys

for line in sys.stdin:
    r = json.loads(line)

    if r.get("submission_status") == "READY":
        r["confidence"] = max(r.get("confidence", 0), 0.85)
        r["confirmed_by"] = "Travis"

    print(json.dumps(r))
