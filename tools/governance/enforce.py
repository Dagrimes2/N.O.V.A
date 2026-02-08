#!/usr/bin/env python3
import json, sys

BLOCK_IF_NO_CONFIRM = {"READY", "READY_CHAIN"}

for line in sys.stdin:
    r = json.loads(line)

    intent = r.get("intent", {}).get("mode")
    status = r.get("submission_status")

    if status in BLOCK_IF_NO_CONFIRM and intent != "report":
        r["submission_status"] = "HOLD"
        r["hold_reason"] = "Intent not set to report mode"

    print(json.dumps(r))
