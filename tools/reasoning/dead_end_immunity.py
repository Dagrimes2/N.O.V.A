#!/usr/bin/env python3
import sys, json, os

DEAD_END_FILE = os.path.expanduser("~/Nova/memory/dead_ends/dead_ends.json")

def load_dead_ends():
    path = os.path.expanduser("~/Nova/memory/dead_ends/dead_ends.json")
    if not os.path.exists(path):
        return {}

    with open(path, "r") as f:
        data = json.load(f)

    # Support both legacy and current formats
    if isinstance(data, dict):
        return data.get("entries", {})
    return {}


def is_dead_end(record, dead_ends):
    for d in dead_ends:
        if (
            d["host"] == record.get("host")
            and d["path"] == record.get("path")
            and set(d.get("signals", [])) == set(record.get("signals", []))
        ):
            return True, d
    return False, None

def main():
    dead_ends = load_dead_ends()

    for line in sys.stdin:
        r = json.loads(line)

        hit, entry = is_dead_end(r, dead_ends)
        if hit:
            r["immunity"] = {
                "status": "dead_end",
                "reason": entry.get("notes", "Previously confirmed dead end"),
                "confidence_cap": 0.15
            }
            r["confidence"] = min(r.get("confidence", 0), 0.15)
        else:
            r["immunity"] = { "status": "clear" }

        print(json.dumps(r))

if __name__ == "__main__":
    main()
