#!/usr/bin/env python3
import sys, json, os, datetime, hashlib

EVID_DIR = os.path.expanduser("~/Nova/evidence")
INDEX = os.path.join(EVID_DIR, "index.jsonl")

def now_utc():
    return datetime.datetime.now(datetime.UTC).isoformat()

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def main():
    os.makedirs(EVID_DIR, exist_ok=True)
    os.makedirs(os.path.join(EVID_DIR, "raw"), exist_ok=True)
    os.makedirs(os.path.join(EVID_DIR, "notes"), exist_ok=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue

        host = r.get("host", "unknown")
        path = r.get("path", "/")
        method = r.get("method", "GET")
        target = f"{host}{path}"

        rec = {
            "ts": now_utc(),
            "target": target,
            "method": method,
            "status": r.get("status"),
            "confidence": r.get("confidence"),
            "priority": r.get("priority"),
            "signals": r.get("signals", []),
            "submission_status": r.get("submission_status"),
            "auth_context": r.get("auth_context", "unknown"),  # you can fill later
            "evidence": {
                "request_file": None,
                "response_file": None,
                "response_sha256": None,
                "response_bytes": None,
            },
            "notes_file": None,
        }

        with open(INDEX, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

if __name__ == "__main__":
    main()
