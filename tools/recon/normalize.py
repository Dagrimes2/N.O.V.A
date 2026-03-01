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
- source
"""

import json
import sys
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any

DEFAULT_SOURCE = "unknown"

def normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    # Source tagging (external tools should set this; otherwise default)
    source = record.get("source", DEFAULT_SOURCE)

    # URL parsing
    url = record.get("url") or record.get("uri")
    host = record.get("host")
    path = record.get("path")

    params = {}
    if url:
        parsed = urlparse(url)
        host = host or parsed.hostname
        path = path or parsed.path or "/"
        params = {k: (v[0] if len(v) == 1 else v) for k, v in parse_qs(parsed.query).items()}

    method = (record.get("method") or record.get("verb") or "GET").upper()

    headers = {}
    raw_headers = record.get("headers") or {}
    if isinstance(raw_headers, dict):
        headers = {k.lower(): str(v) for k, v in raw_headers.items()}

    status = record.get("status") or record.get("status_code") or record.get("code")
    length = record.get("length") or record.get("size") or record.get("content_length")

    return {
        "host": host,
        "path": path or "/",
        "method": method,
        "params": params or {},
        "headers": headers,
        "status": status,
        "length": length,
        "source": source,
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
        print(json.dumps(normalize_record(record)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
