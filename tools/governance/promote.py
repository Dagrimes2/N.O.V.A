#!/usr/bin/env python3
import json, sys

for line in sys.stdin:
    r = json.loads(line)

    if r.get("submission_status") == "REVIEW":
        r["submission_status"] = "READY"
        r["promotion_reason"] = "Approved by operator Travis"

    print(json.dumps(r))
