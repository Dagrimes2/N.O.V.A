#!/usr/bin/env python3
import json, sys

INTENT = {
    "mode": "recon",  # recon | validate | report | learn
    "operator": "Travis"
}

for line in sys.stdin:
    r = json.loads(line)
    r["intent"] = INTENT
    print(json.dumps(r))
