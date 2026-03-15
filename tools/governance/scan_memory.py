#!/usr/bin/env python3
"""
N.O.V.A Scan Memory — deduplication layer

Tracks what Nova has scanned and when.
Prevents redundant rescans of the same target within a cooldown window.

Usage:
    from tools.governance.scan_memory import was_scanned_recently, record_scan
    if was_scanned_recently("gitlab.com", hours=24):
        return "Skipped — scanned recently"
    record_scan("gitlab.com", findings_count=3, score=7.2)
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE             = Path.home() / "Nova"
GOV_DIR          = BASE / "memory/governance"
SCAN_MEMORY_FILE = GOV_DIR / "scan_memory.json"
DEFAULT_COOLDOWN = 24  # hours

GOV_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    if not SCAN_MEMORY_FILE.exists():
        return {}
    try:
        return json.loads(SCAN_MEMORY_FILE.read_text())
    except Exception:
        return {}


def _save(data: dict) -> None:
    SCAN_MEMORY_FILE.write_text(json.dumps(data, indent=2))


def was_scanned_recently(target: str, hours: int = DEFAULT_COOLDOWN) -> bool:
    """Return True if target was scanned within the cooldown window."""
    data  = _load()
    entry = data.get(target)
    if not entry:
        return False
    try:
        last_ts = datetime.fromisoformat(entry["last_scanned"])
        cutoff  = datetime.now(timezone.utc) - timedelta(hours=hours)
        return last_ts > cutoff
    except Exception:
        return False


def record_scan(target: str, findings_count: int = 0, score: float = 0.0) -> None:
    """Record that target was just scanned."""
    data = _load()
    prev = data.get(target, {})
    data[target] = {
        "last_scanned":  datetime.now(timezone.utc).isoformat(),
        "scan_count":    prev.get("scan_count", 0) + 1,
        "last_findings": findings_count,
        "last_score":    round(score, 2),
        "first_scanned": prev.get("first_scanned",
                                  datetime.now(timezone.utc).isoformat()),
    }
    _save(data)


def get_scan_history(target: str) -> dict:
    """Return full scan history for a target."""
    return _load().get(target, {})


def time_since_last_scan(target: str) -> str:
    """Human-readable time since last scan, or 'never'."""
    entry = _load().get(target)
    if not entry:
        return "never"
    try:
        last_ts = datetime.fromisoformat(entry["last_scanned"])
        delta   = datetime.now(timezone.utc) - last_ts
        hours   = int(delta.total_seconds() // 3600)
        if hours < 1:
            return f"{int(delta.total_seconds() // 60)}m ago"
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return "unknown"


def list_recent(hours: int = 72) -> list[dict]:
    """Return scans from the last N hours, newest first."""
    data   = _load()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = []
    for target, info in data.items():
        try:
            ts = datetime.fromisoformat(info["last_scanned"])
            if ts > cutoff:
                result.append({"target": target, **info})
        except Exception:
            pass
    return sorted(result, key=lambda x: x["last_scanned"], reverse=True)


def stats() -> dict:
    data = _load()
    return {
        "total_targets": len(data),
        "total_scans":   sum(v.get("scan_count", 0) for v in data.values()),
        "recent_24h":    len(list_recent(24)),
    }


def main():
    import sys
    G = "\033[32m"; C = "\033[36m"; W = "\033[97m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        entries = list_recent(72)
        if not entries:
            print(f"{DIM}No scans in the last 72 hours.{NC}")
            return
        print(f"\n{B}Recent Scans ({len(entries)}){NC}")
        for e in entries:
            age  = time_since_last_scan(e["target"])
            n    = e.get("last_findings", 0)
            sc   = e.get("last_score", 0)
            cnt  = e.get("scan_count", 1)
            col  = G if sc >= 7 else (C if sc >= 4 else DIM)
            print(f"  {col}{e['target']:35s}{NC} {DIM}{age:10s}{NC} "
                  f"findings={n} score={sc} scans={cnt}")

    elif cmd == "stats":
        s = stats()
        print(f"\n{B}Scan Memory Stats{NC}")
        print(f"  Total targets: {s['total_targets']}")
        print(f"  Total scans:   {s['total_scans']}")
        print(f"  Last 24h:      {s['recent_24h']}")

    elif cmd == "check" and len(sys.argv) > 2:
        target = sys.argv[2]
        recent = was_scanned_recently(target)
        hist   = get_scan_history(target)
        print(f"\n{B}{target}{NC}")
        if hist:
            print(f"  Last scanned: {time_since_last_scan(target)}")
            print(f"  Scan count:   {hist.get('scan_count', 0)}")
            print(f"  Last score:   {hist.get('last_score', 0)}")
            print(f"  Skip (24h cooldown): {recent}")
        else:
            print(f"  {DIM}Never scanned.{NC}")

    else:
        print("Usage: nova scanmem [list|stats|check <target>]")


if __name__ == "__main__":
    main()
