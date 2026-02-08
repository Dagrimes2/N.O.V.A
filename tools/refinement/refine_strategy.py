#!/usr/bin/env python3

import sys
import json
from collections import Counter

def refine(record, stats):
    confidence = record.get("confidence", 0)
    priority = record.get("priority", "LOW")

    adjustment = {}

    if confidence >= 0.75 and priority in ("HIGH", "MEDIUM"):
        adjustment["bias"] = "increase_focus"
        adjustment["note"] = "High confidence target reinforced"
    elif confidence < 0.3:
        adjustment["bias"] = "deprioritize"
        adjustment["note"] = "Low confidence target deprioritized"
    else:
        adjustment["bias"] = "neutral"

    record["refinement"] = adjustment
    return record

def main():
    records = []
    for line in sys.stdin:
        record = json.loads(line)
        records.append(record)

    stats = Counter(
        r.get("priority", "LOW") for r in records
    )

    for r in records:
        print(json.dumps(refine(r, stats)))

if __name__ == "__main__":
    main()
