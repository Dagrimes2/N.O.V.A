#!/usr/bin/env python3
"""
N.O.V.A Memory System v2 — Python 3.14 compatible
Uses JSON files instead of ChromaDB (same interface, no deps)
"""
import sys, json, hashlib, os
from pathlib import Path
from datetime import datetime, timezone, timezone

# Knowledge graph integration (non-fatal if unavailable)
try:
    import sys as _sys
    _nova_root = str(Path.home() / "Nova")
    if _nova_root not in _sys.path:
        _sys.path.insert(0, _nova_root)
    from tools.knowledge.graph import node_id_for, add_edge as _graph_edge
    _GRAPH_ENABLED = True
except Exception:
    _GRAPH_ENABLED = False

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

def _graph_insert(r: dict):
    """Push finding into knowledge graph (best-effort, never fails pipeline)."""
    if not _GRAPH_ENABLED:
        return
    try:
        host       = r.get("host","")
        path       = r.get("path","")
        signals    = r.get("signals",[])
        decision   = r.get("reflection",{}).get("decision","hold")
        confidence = float(r.get("confidence",0))
        text       = to_text(r)

        f_id = node_id_for("finding", text[:200], {
            "host": host, "path": path,
            "decision": decision, "confidence": confidence,
            "signals": signals,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        if host:
            t_id = node_id_for("target", host, {})
            _graph_edge(f_id, t_id, "found_on", weight=confidence)
        for sig in signals:
            s_id = node_id_for("signal", sig, {})
            _graph_edge(f_id, s_id, "triggered_by")
        # Link hypotheses categories
        for hyp in r.get("hypotheses",[]):
            cat = hyp.get("category","")
            if cat:
                p_id = node_id_for("pattern", cat, {})
                _graph_edge(f_id, p_id, "led_to",
                            weight=hyp.get("confidence_modifier",0))
    except Exception:
        pass


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
    _graph_insert(r)

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
