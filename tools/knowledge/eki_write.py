#!/usr/bin/env python3
import sys, json

EKI_PATH = "eki/store.jsonl"

def main():
    for line in sys.stdin:
        r = json.loads(line)
        promo = r.get("knowledge_promotion", {})

        if not promo.get("accepted"):
            continue

        entry = {
            "hash": promo["hash"],
            "target": r.get("host") + r.get("path"),
            "meta_reason": r.get("meta_reason"),
            "confidence": r.get("confidence"),
            "signals": r.get("signals"),
            "source": "nova",
            "mode": "read_only"
        }

        with open(EKI_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")

if __name__ == "__main__":
    main()
