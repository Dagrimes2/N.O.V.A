#!/usr/bin/env python3
import sys, json, os, hashlib

SNAPSHOT = os.path.expanduser("~/Nova/memory/snapshots/last.json")

def hash_target(r):
    s = r["host"] + r["path"] + str(r.get("triage", {}).get("confidence_adjusted"))
    return hashlib.sha256(s.encode()).hexdigest()

def load_prev():
    if not os.path.exists(SNAPSHOT):
        return {}
    with open(SNAPSHOT) as f:
        return json.load(f)

def save_now(data):
    with open(SNAPSHOT, "w") as f:
        json.dump(data, f, indent=2)

def main():
    prev = load_prev()
    current = {}
    changes = []

    for line in sys.stdin:
        r = json.loads(line)
        key = r["host"] + r["path"]
        h = hash_target(r)
        current[key] = h

        if prev.get(key) != h:
            changes.append(key)

    save_now(current)

    for c in changes:
        print(f"[Δ] {c}")

if __name__ == "__main__":
    main()
