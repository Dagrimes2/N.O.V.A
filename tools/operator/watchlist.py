#!/usr/bin/env python3
import sys, json, os, datetime

WATCHLIST_PATH = os.path.expanduser("~/Nova/memory/watchlist/watchlist.json")

def load():
    if not os.path.exists(WATCHLIST_PATH):
        return {"targets": {}}
    with open(WATCHLIST_PATH) as f:
        return json.load(f)

def save(data):
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(data, f, indent=2)

def main():
    wl = load()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()


    for line in sys.stdin:
        r = json.loads(line)
        decision = r.get("reflection", {}).get("decision")
        if decision not in ("act", "observe"):
            continue

        key = r["host"] + r["path"]
        entry = wl["targets"].get(key, {})
        entry.update({
            "last_seen": now,
            "decision": decision,
            "confidence": r.get("triage", {}).get("confidence_adjusted"),
            "signals": r.get("signals", [])
        })
        wl["targets"][key] = entry

    save(wl)

if __name__ == "__main__":
    main()
