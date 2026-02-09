#!/usr/bin/env python3
import sys, json, os

STORE = os.path.expanduser("~/Nova/eki/store.jsonl")

def main():
    query = (sys.argv[1] if len(sys.argv) > 1 else "").lower().strip()
    if not os.path.exists(STORE):
        print("EKI store missing:", STORE)
        sys.exit(1)

    with open(STORE, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line:
                continue
            obj = json.loads(line)
            blob = json.dumps(obj).lower()
            if not query or query in blob:
                print(json.dumps(obj))

if __name__ == "__main__":
    main()
