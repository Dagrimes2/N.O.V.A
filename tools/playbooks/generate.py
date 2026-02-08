#!/usr/bin/env python3
"""
Nova Phase 5.1 — Playbook Generator

Reads scored JSONL from stdin and emits actionable test playbooks.
"""

import json
import sys
from typing import Dict, List, Any


PLAYBOOKS = {
    "auth-path": [
        {
            "name": "Auth bypass via proxy headers",
            "commands": [
                "curl -H 'X-Original-URL: {path}' https://{host}{path}",
                "curl -H 'X-Rewrite-URL: {path}' https://{host}{path}",
                "curl -H 'X-Forwarded-For: 127.0.0.1' https://{host}{path}"
            ]
        }
    ],
    "error-403": [
        {
            "name": "403 bypass variations",
            "commands": [
                "curl https://{host}{path}/.",
                "curl https://{host}//{path}",
                "curl -X POST https://{host}{path}"
            ]
        }
    ],
    "error-500": [
    {
        "name": "Server error probing",
        "commands": [
            "ffuf -u https://{host}{path}?FUZZ=1 -w params.txt",
            "curl -d '{{}}' https://{host}{path}"
        ]
    }
    ],

    "numeric-id": [
        {
            "name": "IDOR checks",
            "commands": [
                "curl https://{host}{path}?id=1",
                "curl https://{host}{path}?id=2",
                "curl https://{host}{path}?id=9999"
            ]
        }
    ],
    "method-post": [
        {
            "name": "POST abuse / CSRF",
            "commands": [
                "curl -X POST https://{host}{path}",
                "curl -X POST -H 'Content-Type: application/json' -d '{{}}' https://{host}{path}"
            ]
        }
    ]
}


def main() -> int:
    for line in sys.stdin:
        record = json.loads(line)
        signals = record.get("signals", [])
        host = record.get("host")
        path = record.get("path")

        playbooks: List[Dict[str, Any]] = []

        for sig in signals:
            if sig in PLAYBOOKS:
                for pb in PLAYBOOKS[sig]:
                    commands = [
                        cmd.format(host=host, path=path)
                        for cmd in pb["commands"]
                    ]
                    playbooks.append({
                        "signal": sig,
                        "name": pb["name"],
                        "commands": commands
                    })

        record["priority"] = (
            "HIGH" if record.get("score", 0) >= 15
            else "MEDIUM" if record.get("score", 0) >= 8
            else "LOW"
        )

        record["playbooks"] = playbooks
        print(json.dumps(record))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
