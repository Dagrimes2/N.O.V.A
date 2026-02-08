#!/usr/bin/env python3
import json
import sys
from collections import defaultdict

CHAIN_RULES = [
    {
        "name": "Auth Bypass → IDOR",
        "requires": {"auth-path", "numeric-id"},
        "impact": "Unauthorized access to other users' data"
    },
    {
        "name": "403 Bypass → Admin Access",
        "requires": {"auth-path", "error-403"},
        "impact": "Potential administrative access without authentication"
    },
    {
        "name": "Login Error → Account Manipulation",
        "requires": {"method-post", "error-500"},
        "impact": "Account takeover or authentication logic bypass"
    }
]

def main():
    records = []
    by_host = defaultdict(list)

    for line in sys.stdin:
        r = json.loads(line)
        records.append(r)
        by_host[r["host"]].append(r)

    for host, items in by_host.items():
        all_signals = set()
        for r in items:
            all_signals |= set(r.get("signals", []))

        for rule in CHAIN_RULES:
            if rule["requires"].issubset(all_signals):
                chain = {
                    "host": host,
                    "chain": rule["name"],
                    "impact": rule["impact"],
                    "signals": list(rule["requires"]),
                    "severity": "HIGH",
                    "submission_status": "READY_CHAIN"
                }
                print(json.dumps(chain))

if __name__ == "__main__":
    main()
