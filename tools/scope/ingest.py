#!/usr/bin/env python3
"""
Nova Phase 5.4 — Scope Ingestion

Reads scope definitions (domains, wildcards, URLs) from stdin
and emits raw.jsonl targets for Nova pipeline.
"""

import sys
import json
import re

def normalize_target(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Remove wildcard
    domain = line.replace("*.", "")

    return {
        "host": domain,
        "path": "/",
        "method": "GET"
    }

def main():
    for line in sys.stdin:
        target = normalize_target(line)
        if target:
            print(json.dumps(target))

if __name__ == "__main__":
    main()
