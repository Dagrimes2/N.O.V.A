#!/usr/bin/env python3
"""
Nova Phase 5.5.3 — Memory Learning Engine (Schema-Safe)

- Auto-migrates legacy flat memory
- Tracks paths + signals separately
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any

STORE = Path(__file__).parent / "store.json"


def load_store() -> Dict[str, Any]:
    if not STORE.exists():
        return {"paths": {}, "signals": {}}

    data = json.loads(STORE.read_text())

    # 🔁 Auto-migrate legacy flat schema
    if "paths" not in data and "signals" not in data:
        migrated = {"paths": {}, "signals": {}}
        for key, value in data.items():
            migrated["paths"][key] = {
                "seen": value.get("hits", 0),
                "confirmed": 0
            }
        return migrated

    # Ensure keys always exist
    data.setdefault("paths", {})
    data.setdefault("signals", {})
    return data


def save_store(data: Dict[str, Any]) -> None:
    STORE.write_text(json.dumps(data, indent=2))


def main() -> None:
    store = load_store()

    for line in sys.stdin:
        record = json.loads(line)

        host = record.get("host")
        path = record.get("path", "/")
        signals = record.get("signals", [])
        score = record.get("score", 0)

        key = f"{host}{path}"

        # 📍 Path memory
        store["paths"].setdefault(key, {"seen": 0, "confirmed": 0})
        store["paths"][key]["seen"] += 1
        if score >= 15:
            store["paths"][key]["confirmed"] += 1

        # 🧠 Signal memory
        for sig in signals:
            store["signals"].setdefault(sig, {"hits": 0, "confirmed": 0})
            store["signals"][sig]["hits"] += 1
            if score >= 15:
                store["signals"][sig]["confirmed"] += 1

        print(json.dumps(record))

    save_store(store)


if __name__ == "__main__":
    main()
