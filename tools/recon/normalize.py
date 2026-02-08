#!/usr/bin/env python3
"""
Nova Phase 4 — Recon Normalizer

Reads heterogeneous JSONL recon data from stdin and emits a normalized schema.

Output fields:
- host
- path
- method
- params
- headers
- status
- length
"""

import json
import sys
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any


def normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    # URL parsing
    url = record.get("url") or record.get("uri")
    host = record.get("host")
    path = record.get("path")

    params = {}
    if url:
        parsed = urlparse(url)
        host = host or parsed.hostname
        path = path or parsed.path or "/"
        params = {
            k: v[0] if len(v) == 1 else v
            for k, v in parse_qs(parsed.query).items()
        }

    # Method
    method = (
        record.get("method")
        or record.get("verb")
        or "GET"
    ).upper()

    # Headers
    headers = {}
    raw_headers = record.get("headers") or {}
    if isinstance(raw_headers, dict):
        headers = {k.lower(): str(v) for k, v in raw_headers.items()}

    # Status & length (safe, optional)
    status = (
        record.get("status")
        or record.get("status_code")
        or record.get("code")
    )

    length = (
        record.get("length")
        or record.get("size")
        or record.get("content_length")
    )

    return {
        "host": host,
        "path": path or "/",
        "method": method,
        "params": params or {},
        "headers": headers,
        "status": status,
        "length": length,
    }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        normalized = normalize_record(record)
        print(json.dumps(normalized))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
