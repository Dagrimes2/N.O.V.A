#!/usr/bin/env python3
import json, sys, datetime

LOG = "core/audit.log"

for line in sys.stdin:
    r = json.loads(line)
    with open(LOG, "a") as f:
        f.write(f"{datetime.datetime.utcnow().isoformat()} | {r.get('host')}{r.get('path')} | {r.get('submission_status')}\n")
    print(json.dumps(r))
