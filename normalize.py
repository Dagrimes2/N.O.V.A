#!/usr/bin/env python3
"""Normalize heterogeneous JSONL recon data into a compact schema.

Reads JSON objects from stdin (one per line) and writes normalized JSONL to stdout
with fields:

- host
- path
- method
- params
- headers
- status
- length

Designed for bug bounty recon pipelines where input sources vary widely.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import parse_qs, urlparse

URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def iter_jsonl(stream: Iterable[str]) -> Iterable[Dict[str, Any]]:
    """Yield JSON objects from a text stream containing JSONL."""
    for lineno, raw_line in enumerate(stream, 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            print(
                f"[normalize.py] skipping invalid JSON at line {lineno}: {exc}",
                file=sys.stderr,
            )
            continue
        if not isinstance(obj, dict):
            print(
                f"[normalize.py] skipping non-object JSON at line {lineno}",
                file=sys.stderr,
            )
            continue
        yield obj


def first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    return None


def normalize_headers(headers: Any) -> Dict[str, str]:
    """Convert header structures to a lowercase-keyed dict of strings."""
    out: Dict[str, str] = {}
    if isinstance(headers, dict):
        for key, value in headers.items():
            if key is None:
                continue
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            elif value is None:
                value = ""
            out[str(key).lower()] = str(value)
    elif isinstance(headers, list):
        for item in headers:
            if isinstance(item, dict):
                name = first_non_none(item.get("name"), item.get("key"), item.get("header"))
                value = first_non_none(item.get("value"), item.get("val"))
                if name is not None:
                    out[str(name).lower()] = "" if value is None else str(value)
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                key, value = item
                out[str(key).lower()] = "" if value is None else str(value)
    return out


def normalize_params(params: Any) -> Dict[str, Any]:
    """Convert params/query structures to a stable dict."""
    if params is None:
        return {}

    if isinstance(params, dict):
        return params

    if isinstance(params, str):
        parsed = parse_qs(params, keep_blank_values=True)
        return {
            key: values[0] if len(values) == 1 else values
            for key, values in parsed.items()
        }

    if isinstance(params, list):
        out: Dict[str, Any] = {}
        for item in params:
            if isinstance(item, dict):
                key = first_non_none(item.get("name"), item.get("key"), item.get("param"))
                value = first_non_none(item.get("value"), item.get("val"), "")
                if key is not None:
                    out[str(key)] = value
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                key, value = item
                out[str(key)] = value
        return out

    return {}


def extract_url_parts(record: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    url = first_non_none(record.get("url"), record.get("uri"), record.get("target"))
    if not isinstance(url, str) or not URL_RE.search(url):
        return None, None, {}

    parsed = urlparse(url)
    host = parsed.netloc or None
    path = parsed.path or "/"
    query_params = normalize_params(parsed.query)
    return host, path, query_params


def normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    host_from_url, path_from_url, query_params = extract_url_parts(record)

    host = first_non_none(
        record.get("host"),
        record.get("hostname"),
        record.get("target"),
        record.get("domain"),
        record.get("domain"),
        host_from_url,
    )

    path = first_non_none(
        record.get("path"),
        record.get("endpoint"),
        record.get("route"),
        path_from_url,
        "/",
    )

    method = first_non_none(record.get("method"), record.get("verb"), "GET")
    if method is None:
        method = "GET"
    method = str(method).upper()

    params = normalize_params(
        first_non_none(
            record.get("params"),
            record.get("parameters"),
            record.get("query"),
            record.get("query_params"),
            query_params,
        )
    )

    headers = normalize_headers(
        first_non_none(record.get("headers"), record.get("request_headers"), {})
    )

    status = to_int(
        first_non_none(
            record.get("status"),
            record.get("status_code"),
            record.get("code"),
            record.get("response_status"),
        )
    )

    length = to_int(
        first_non_none(
            record.get("length"),
            record.get("content_length"),
            record.get("response_length"),
            record.get("size"),
        )
    )

    return {
        "host": None if host is None else str(host),
        "path": None if path is None else str(path),
        "method": method,
        "params": params,
        "headers": headers,
        "status": status,
        "length": length,
    }


def main() -> int:
    for record in iter_jsonl(sys.stdin):
        out = normalize_record(record)
        sys.stdout.write(json.dumps(out, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
