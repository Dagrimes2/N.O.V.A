#!/usr/bin/env python3
import sys, json
from collections import defaultdict

SECTIONS = ["act", "observe", "hold", "suppress"]

def render_item(r: dict) -> str:
    target = r.get("host", "?") + r.get("path", "")
    triage = r.get("triage", {})
    refl = r.get("reflection", {})

    conf = triage.get("confidence_adjusted", 0.0)
    signals = ", ".join(r.get("signals", [])) or "none"
    reason = refl.get("reason", "n/a")
    suggestion = triage.get("suggestion", "map_surface")

    return (
        f"- **{target}**\n"
        f"  - confidence: `{conf:.2f}`\n"
        f"  - triage: `{suggestion}`\n"
        f"  - signals: `{signals}`\n"
        f"  - why: {reason}\n"
    )

def main():
    buckets = defaultdict(list)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue

        decision = r.get("reflection", {}).get("decision")
        if decision in SECTIONS:
            buckets[decision].append(r)

    print("# 🧠 Nova Operator Brief\n")

    for section in SECTIONS:
        items = buckets.get(section, [])
        if not items:
            continue

        print(f"## {section.upper()}\n")
        for r in items:
            print(render_item(r))

if __name__ == "__main__":
    main()
