#!/usr/bin/env python3
"""
N.O.V.A Memory System v2 — Python 3.14 compatible
Uses JSON files instead of ChromaDB (same interface, no deps)
"""
import sys, json, hashlib, os
from pathlib import Path
from datetime import datetime, timezone, timezone

MEMORY_DIR = Path.home() / "Nova/memory/store"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
INDEX_FILE = MEMORY_DIR / "index.jsonl"

def to_text(r: dict) -> str:
    return f"{r.get('host','')}{r.get('path','')} status={r.get('status')} signals={r.get('signals',[])} {r.get('note','')}"

def get_similar(r: dict, n=3) -> list:
    """Simple keyword similarity — no vectors needed for our scale"""
    if not INDEX_FILE.exists():
        return []
    target = to_text(r).lower()
    target_words = set(target.split())
    scored = []
    try:
        with open(INDEX_FILE) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    words = set(entry.get("text","").lower().split())
                    overlap = len(target_words & words)
                    if overlap > 0:
                        scored.append((overlap, entry.get("text","")))
                except: continue
    except: return []
    scored.sort(reverse=True)
    return [s[1] for s in scored[:n]]

def store(r: dict):
    uid = hashlib.sha256(to_text(r).encode()).hexdigest()[:16]
    entry = {
        "id": uid,
        "text": to_text(r),
        "host": r.get("host",""),
        "decision": r.get("reflection",{}).get("decision","hold"),
        "confidence": str(r.get("confidence",0)),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    try:
        with open(INDEX_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except: pass

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        similar = get_similar(r)
        r["memory_context"] = {"similar_findings": similar, "count": len(similar)}
        store(r)
        print(json.dumps(r))

if __name__ == "__main__":
    main()
