#!/usr/bin/env python3
import sys, json, time
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"https"}

def safe_url(u: str) -> bool:
    try:
        p = urlparse(u)
        return (p.scheme in ALLOWED_SCHEMES) and bool(p.netloc)
    except Exception:
        return False

def main():
    """
    This tool does NOT fetch by default.
    It only annotates "external_intel" requests and requires human unlock later.
    """
    for line in sys.stdin:
        r = json.loads(line)

        url = (r.get("external_intel") or {}).get("url")
        r.setdefault("external_intel", {})
        r["external_intel"]["requested_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if not url or not safe_url(url):
            r["external_intel"]["status"] = "rejected"
            r["external_intel"]["reason"] = "invalid_or_missing_url"
        else:
            r["external_intel"]["status"] = "pending_human_unlock"
            r["external_intel"]["reason"] = "phase9_quarantine"

        print(json.dumps(r))

if __name__ == "__main__":
    main()
