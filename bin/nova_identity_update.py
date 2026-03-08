#!/usr/bin/env python3
"""
N.O.V.A Identity Updater
Automatically keeps nova_identity.json current.
Called after scans, dreams, and chats.
"""
import json, datetime
from pathlib import Path

BASE          = Path.home() / "Nova"
IDENTITY_FILE = BASE / "memory/nova_identity.json"
MEMORY_INDEX  = BASE / "memory/store/index.jsonl"
DREAMS        = BASE / "memory/dreams"
CHATS         = BASE / "memory/chats"
LIFE_DIR      = BASE / "memory/life"
REPORTS       = BASE / "reports"

def update():
    if not IDENTITY_FILE.exists():
        print("[!] nova_identity.json not found")
        return

    identity = json.loads(IDENTITY_FILE.read_text())
    stats = identity.get("stats", {})

    # Count everything from actual files
    stats["findings_stored"] = sum(
        1 for _ in open(MEMORY_INDEX)
    ) if MEMORY_INDEX.exists() else 0

    stats["dreams_completed"] = len(
        list(DREAMS.glob("dream_*.md"))
    ) if DREAMS.exists() else 0

    stats["total_scans"] = len(
        list(REPORTS.glob("*_recon.json"))
    ) if REPORTS.exists() else 0

    stats["chats_with_travis"] = len(
        list(CHATS.glob("chat_*.md"))
    ) if CHATS.exists() else 0

    stats["life_entries"] = len(
        list(LIFE_DIR.glob("*.md"))
    ) if LIFE_DIR.exists() else 0

    identity["stats"]        = stats
    identity["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d")

    IDENTITY_FILE.write_text(json.dumps(identity, indent=2))
    print(f"[N.O.V.A] Identity updated — {stats['total_scans']} scans, "
          f"{stats['findings_stored']} memories, "
          f"{stats['dreams_completed']} dreams")

if __name__ == "__main__":
    update()
