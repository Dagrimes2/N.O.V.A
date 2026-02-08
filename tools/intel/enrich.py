#!/usr/bin/env python3
"""
Nova Phase 5.2 — Intelligence Enrichment (Hardened)

Adds:
- confidence score (0.0–1.0)
- deduplicated commands
- human-readable vulnerability notes
- markdown-ready report block
"""

import json
import sys
from typing import Dict, List, Any

CONFIDENCE_WEIGHTS = {
    "auth-path": 0.9,
    "error-403": 0.8,
    "numeric-id": 0.7,
    "method-post": 0.6,
    "error-500": 0.5,
}


def safe_status(record: Dict[str, Any]):
    return (
        record.get("status")
        or record.get("status_code")
        or "N/A"
    )


def dedupe(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def build_note(record: Dict[str, Any]) -> str:
    host = record.get("host", "unknown")
    path = record.get("path", "/")
    signals = ", ".join(record.get("signals", [])) or "none"
    status = safe_status(record)

    return (
        f"The endpoint `{path}` on `{host}` triggered the following signals: "
        f"{signals}. The server responded with HTTP {status}. "
        "This behavior suggests a potential access control, logic flaw, "
        "or unexplored surface worthy of manual testing."
    )


def build_markdown(record: Dict[str, Any]) -> str:
    cmds = []
    for pb in record.get("playbooks", []):
        for c in pb.get("commands", []):
            cmds.append(f"- `{c}`")

    return f"""### 🔎 {record.get('host','')}{record.get('path','')}

**Method:** {record.get('method', 'N/A')}
**Status:** {safe_status(record)}
**Priority:** {record.get('priority', 'LOW')}
**Confidence:** {record.get('confidence', 0.0):.2f}

**Signals:** {", ".join(record.get("signals", [])) or "none"}

**Description:**
{record['note']}

**Proof of Concept:**
{chr(10).join(cmds) if cmds else "_No automated PoC generated yet._"}
"""


def main() -> int:
    for line in sys.stdin:
        record = json.loads(line)

        signals = record.get("signals", [])
        if signals:
            confidence = max(
                CONFIDENCE_WEIGHTS.get(sig, 0.3)
                for sig in signals
            )
        else:
            confidence = 0.2  # scope-only / unexplored asset

        for pb in record.get("playbooks", []):
            pb["commands"] = dedupe(pb.get("commands", []))

        record["confidence"] = round(confidence, 2)
        record["note"] = build_note(record)
        record["markdown"] = build_markdown(record)

        print(json.dumps(record))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
