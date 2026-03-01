#!/usr/bin/env python3
import sys, json

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        r = json.loads(line)
    except json.JSONDecodeError:
        continue

    r["source"] = r.get("source", "external")
    r["external_tool"] = "clawdbot_stub"
    print(json.dumps(r))
