#!/usr/bin/env python3
"""
tools/nova_wire.py — N.O.V.A Tool Wiring Layer
Wraps all orphaned stdin/stdout tools into clean Python functions.
Import this from any bin script to use the tools.

Usage:
    from tools.nova_wire import enrich, adjust_score, pattern_boost,
                                promote_to_queue, check_watchlist, mutate_endpoint
"""

import json
import sys
import subprocess
from pathlib import Path

BASE      = Path.home() / "Nova"
TOOLS_DIR = BASE / "tools"

# ─────────────────────────────────────────────
# Internal runner — pipes JSON through a tool
# ─────────────────────────────────────────────

def _pipe(tool_path: Path, record: dict) -> dict:
    """Run a tool via subprocess, pipe one JSON record in, get one back."""
    try:
        result = subprocess.run(
            [sys.executable, str(tool_path)],
            input=json.dumps(record),
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(BASE)
        )
        if result.stdout.strip():
            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
            for line in reversed(lines):
                try:
                    return json.loads(line)
                except Exception:
                    continue
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        pass
    return record  # passthrough on failure


def _pipe_many(tool_path: Path, records: list) -> list:
    """Pipe a list of JSON records through a tool (one per line)."""
    try:
        stdin_data = "\n".join(json.dumps(r) for r in records)
        result = subprocess.run(
            [sys.executable, str(tool_path)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(BASE)
        )
        if result.stdout.strip():
            out = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
            return out if out else records
    except Exception:
        pass
    return records

# ─────────────────────────────────────────────
# 1. ENRICH — tools/intel/enrich.py
#    Adds confidence score, dedup, vulnerability notes, markdown block
#    Wire: nova_research.py after fetching findings
# ─────────────────────────────────────────────

def enrich(record: dict) -> dict:
    """
    Enrich a recon/research record with confidence score and notes.
    Input:  {"host": "...", "path": "...", "signals": [...], ...}
    Output: same record + {"confidence": 0.85, "notes": "...", "report_block": "..."}
    """
    tool = TOOLS_DIR / "intel" / "enrich.py"
    if not tool.exists():
        return record
    return _pipe(tool, record)


def enrich_many(records: list) -> list:
    """Enrich a list of records."""
    tool = TOOLS_DIR / "intel" / "enrich.py"
    if not tool.exists():
        return records
    return _pipe_many(tool, records)

# ─────────────────────────────────────────────
# 2. ADJUST SCORE — tools/scoring/memory_adjust.py
#    Adjusts scores using learned memory store
#    Wire: score.py after initial scoring
# ─────────────────────────────────────────────

def adjust_score(record: dict) -> dict:
    """
    Adjust a scored record using memory store.
    Input:  {"score": 0.6, "host": "...", "signals": [...]}
    Output: same record with adjusted "score" clamped to 0.0-1.0
    """
    tool = TOOLS_DIR / "scoring" / "memory_adjust.py"
    if not tool.exists():
        return record
    # memory_adjust.py needs the store to exist
    store = BASE / "memory" / "store.json"
    if not store.exists():
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("{}")
    result = _pipe(tool, record)
    # Always clamp score — memory_adjust can drift above 1.0
    if "score" in result:
        result["score"] = round(min(1.0, max(0.0, float(result["score"]))), 4)
    return result


def adjust_scores(records: list) -> list:
    """Adjust scores for a list of records."""
    tool = TOOLS_DIR / "scoring" / "memory_adjust.py"
    if not tool.exists():
        return records
    store = BASE / "memory" / "store.json"
    if not store.exists():
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("{}")
    results = _pipe_many(tool, records)
    for r in results:
        if "score" in r:
            r["score"] = round(min(1.0, max(0.0, float(r["score"]))), 4)
    return results

# ─────────────────────────────────────────────
# 3. PATTERN BOOST — tools/reasoning/pattern_memory.py
#    Applies confidence nudges based on prior confirmed patterns
#    Wire: score.py after memory_adjust
# ─────────────────────────────────────────────

def pattern_boost(record: dict) -> dict:
    """
    Apply pattern memory confidence nudges to a record.
    Input:  scored record
    Output: same record with nudged confidence, clamped to 0.0-1.0
    """
    tool = TOOLS_DIR / "reasoning" / "pattern_memory.py"
    if not tool.exists():
        return record
    patterns = BASE / "memory" / "patterns"
    patterns.mkdir(parents=True, exist_ok=True)
    result = _pipe(tool, record)
    for key in ("score", "confidence"):
        if key in result:
            result[key] = round(min(1.0, max(0.0, float(result[key]))), 4)
    return result


def pattern_boost_many(records: list) -> list:
    tool = TOOLS_DIR / "reasoning" / "pattern_memory.py"
    if not tool.exists():
        return records
    patterns = BASE / "memory" / "patterns"
    patterns.mkdir(parents=True, exist_ok=True)
    return _pipe_many(tool, records)

# ─────────────────────────────────────────────
# 4. PROMOTE — tools/knowledge/promote.py
#    Promotes findings to knowledge/queue with fingerprint dedup
#    Wire: nova_memory_summarize.py after summarization
# ─────────────────────────────────────────────

def promote_to_queue(record: dict) -> bool:
    """
    Promote a high-confidence finding to knowledge/queue.
    Returns True if promoted, False if duplicate or skipped.
    """
    tool = TOOLS_DIR / "knowledge" / "promote.py"
    if not tool.exists():
        return False
    queue_dir = BASE / "knowledge" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    result = _pipe(tool, record)
    return result.get("promoted", False)


def promote_many(records: list, min_confidence: float = 0.7) -> int:
    """
    Promote all records above min_confidence threshold.
    Returns count of newly promoted records.
    """
    promoted = 0
    for r in records:
        if r.get("confidence", r.get("score", 0)) >= min_confidence:
            if promote_to_queue(r):
                promoted += 1
    return promoted

# ─────────────────────────────────────────────
# 5. WATCHLIST — tools/operator/watchlist.py
#    Manages target watchlist for autonomous agent
#    Wire: nova_autonomous.py — check before scanning
# ─────────────────────────────────────────────

def check_watchlist(host: str) -> dict:
    """
    Check if a host is on the watchlist and get its priority/notes.
    Returns: {"on_watchlist": bool, "priority": int, "notes": str}
    """
    wl_path = BASE / "memory" / "watchlist" / "watchlist.json"
    if not wl_path.exists():
        return {"on_watchlist": False, "priority": 0, "notes": ""}
    try:
        data = json.loads(wl_path.read_text())
        targets = data.get("targets", {})
        if host in targets:
            entry = targets[host]
            return {
                "on_watchlist": True,
                "priority":     entry.get("priority", 5),
                "notes":        entry.get("notes", ""),
                "added":        entry.get("added", ""),
            }
    except Exception:
        pass
    return {"on_watchlist": False, "priority": 0, "notes": ""}


def add_to_watchlist(host: str, priority: int = 5, notes: str = "") -> bool:
    """Add a host to the watchlist via watchlist.py tool."""
    tool = TOOLS_DIR / "operator" / "watchlist.py"
    wl_path = BASE / "memory" / "watchlist" / "watchlist.json"
    wl_path.parent.mkdir(parents=True, exist_ok=True)

    # Load or init
    if wl_path.exists():
        try:
            data = json.loads(wl_path.read_text())
        except Exception:
            data = {"targets": {}}
    else:
        data = {"targets": {}}

    from datetime import datetime, timezone
    data["targets"][host] = {
        "priority": priority,
        "notes":    notes,
        "added":    datetime.now(timezone.utc).isoformat(),
    }
    try:
        wl_path.write_text(json.dumps(data, indent=2))
        return True
    except Exception:
        return False


def get_watchlist_hosts() -> list:
    """Return all watched hosts sorted by priority (highest first)."""
    wl_path = BASE / "memory" / "watchlist" / "watchlist.json"
    if not wl_path.exists():
        return []
    try:
        data   = json.loads(wl_path.read_text())
        items  = data.get("targets", {}).items()
        sorted_items = sorted(items, key=lambda x: x[1].get("priority", 0), reverse=True)
        return [h for h, _ in sorted_items]
    except Exception:
        return []

# ─────────────────────────────────────────────
# 6. MUTATE — tools/expansion/mutate.py
#    Generates context-aware endpoint variants
#    Wire: nova_gan.py approved attacks → expand surface
#          auto_scan.py → expand discovered paths
# ─────────────────────────────────────────────

def mutate_endpoint(record: dict) -> list:
    """
    Generate endpoint mutations for an attack record.
    Input:  {"host": "gitlab.com", "path": "/api/v4/users/123",
             "signals": ["numeric-id", "auth-path"]}
    Output: list of mutated endpoint records
    """
    tool = TOOLS_DIR / "expansion" / "mutate.py"
    if not tool.exists():
        return [record]
    try:
        stdin_data = json.dumps(record)
        result = subprocess.run(
            [sys.executable, str(tool)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(BASE)
        )
        if result.stdout.strip():
            variants = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    variants.append(json.loads(line))
                except Exception:
                    pass
            return variants if variants else [record]
    except Exception:
        pass
    return [record]


def mutate_approved_attack(attack_text: str, program: str) -> list:
    """
    Extract endpoint from an approved GAN attack and generate mutations.
    Returns list of mutation records ready for scanning.
    """
    import re
    # Extract TARGET line from attack text
    target_match = re.search(r'TARGET:\s*(.+)', attack_text, re.IGNORECASE)
    if not target_match:
        return []

    target_line = target_match.group(1).strip()
    # Parse out path
    path_match = re.search(r'(/[^\s]+)', target_line)
    if not path_match:
        return []

    path   = path_match.group(1)
    # Detect signals from path
    signals = []
    if any(x in path for x in ["user", "auth", "login", "token"]):
        signals.append("auth-path")
    if re.search(r'/\d+', path):
        signals.append("numeric-id")
    if "graphql" in path.lower():
        signals.append("method-post")

    record = {
        "host":    "gitlab.com",
        "path":    path,
        "signals": signals or ["auth-path"],
        "source":  "gan_approved",
        "program": program,
    }
    return mutate_endpoint(record)

# ─────────────────────────────────────────────
# PIPELINE — chain all tools for a full record
# ─────────────────────────────────────────────

def full_pipeline(record: dict) -> dict:
    """
    Run a record through: enrich → adjust_score → pattern_boost
    Use this in score.py or auto_scan.py for a complete processing pass.
    """
    record = enrich(record)
    record = adjust_score(record)
    record = pattern_boost(record)
    return record


if __name__ == "__main__":
    # Quick self-test
    test = {
        "host":    "gitlab.com",
        "path":    "/api/v4/users/123",
        "signals": ["numeric-id", "auth-path"],
        "score":   0.6,
    }
    print("[nova_wire] Self-test:")
    print(f"  Input:  {test}")
    enriched = enrich(test)
    print(f"  Enriched: confidence={enriched.get('confidence', 'n/a')}")
    adjusted = adjust_score(enriched)
    print(f"  Adjusted score: {adjusted.get('score', 'n/a')}")
    boosted  = pattern_boost(adjusted)
    print(f"  Pattern boosted: {boosted.get('score', 'n/a')}")
    mutations = mutate_endpoint(test)
    print(f"  Mutations: {len(mutations)} variants")
    wl = check_watchlist("gitlab.com")
    print(f"  Watchlist: {wl}")
    print("[nova_wire] OK")
