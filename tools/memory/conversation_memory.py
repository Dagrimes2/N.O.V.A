#!/usr/bin/env python3
"""
N.O.V.A Conversation Memory

Indexes past Discord conversations and retrieves relevant exchanges for
current context. Gives Nova genuine conversation continuity — she can
remember what she and Travis talked about before.

Storage (input, read-only):
  memory/conversations/discord.jsonl  — {role, content, ts} lines

Index (written here):
  memory/conversations/conv_index.json — keyword index + session summaries
"""
import json
import os
import sys
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE           = Path.home() / "Nova"
CONV_DIR       = BASE / "memory/conversations"
DISCORD_FILE   = CONV_DIR / "discord.jsonl"
INDEX_FILE     = CONV_DIR / "conv_index.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg          # noqa: F401 — available for future use
except Exception:
    pass

_STOPWORDS = {
    "the","and","for","are","but","not","you","all","can","her","was","one",
    "our","out","had","has","have","him","his","how","its","let","may","nor",
    "now","off","old","own","put","say","she","too","use","way","who","why",
    "with","that","this","they","from","than","then","when","what","will",
    "been","come","into","like","look","more","such","take","than","them",
    "well","were","your","also","just","very","even","some","over","here",
    "there","about","would","could","should","other","after","before",
}


# ── Low-level I/O ──────────────────────────────────────────────────────────────

def _load_exchanges(n: int = None) -> list:
    """
    Load exchanges from discord.jsonl. Each exchange = {user, nova, ts}.
    Pairs consecutive user/assistant lines. Returns last n exchanges if given.
    """
    if not DISCORD_FILE.exists():
        return []

    raw_lines = []
    for line in DISCORD_FILE.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        role    = (obj.get("role") or obj.get("type") or "").lower()
        content = (obj.get("content") or obj.get("message") or obj.get("text") or "").strip()
        ts      = obj.get("ts") or obj.get("timestamp") or ""
        if content:
            raw_lines.append({"role": role, "content": content, "ts": ts})

    # Pair consecutive user → assistant into exchanges
    exchanges = []
    i = 0
    while i < len(raw_lines):
        entry = raw_lines[i]
        role  = entry["role"]
        if role in ("user", "human", "travis"):
            # Look for the next assistant reply
            if i + 1 < len(raw_lines) and raw_lines[i + 1]["role"] in ("assistant", "nova", "bot"):
                exchanges.append({
                    "user": entry["content"],
                    "nova": raw_lines[i + 1]["content"],
                    "ts":   entry["ts"] or raw_lines[i + 1]["ts"],
                })
                i += 2
                continue
        i += 1

    return exchanges[-n:] if n is not None else exchanges


def _significant_words(text: str) -> list:
    """Extract significant words (>4 chars, not stopwords)."""
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if len(w) > 4 and w not in _STOPWORDS]


def _load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except Exception:
            pass
    return {"keyword_index": {}, "sessions": [], "total_exchanges": 0, "built": None}


def _save_index(idx: dict) -> None:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(idx, indent=2))


# ── Public API ─────────────────────────────────────────────────────────────────

def build_index() -> int:
    """
    Build keyword index over all past exchanges.
    For each exchange: extract significant words (>4 chars, not stopwords),
    store in index: {word: [exchange_idx, ...]}.
    Also build session summaries: group by day, summarize as first 100 chars.
    Returns count of exchanges indexed.
    """
    exchanges = _load_exchanges()
    if not exchanges:
        _save_index({"keyword_index": {}, "sessions": [], "total_exchanges": 0,
                     "built": datetime.now(timezone.utc).isoformat()})
        return 0

    keyword_index: dict = defaultdict(list)
    for idx, ex in enumerate(exchanges):
        combined = (ex.get("user", "") + " " + ex.get("nova", ""))
        for word in _significant_words(combined):
            if idx not in keyword_index[word]:
                keyword_index[word].append(idx)

    # Session summaries — group by day (from ts)
    sessions_by_day: dict = {}
    for idx, ex in enumerate(exchanges):
        ts = ex.get("ts", "")
        day = ts[:10] if ts else "unknown"
        if day not in sessions_by_day:
            summary_text = ex.get("user", "")[:100]
            sessions_by_day[day] = {
                "day":     day,
                "summary": summary_text,
                "start":   idx,
                "count":   0,
            }
        sessions_by_day[day]["count"] += 1

    sessions = sorted(sessions_by_day.values(), key=lambda s: s["day"])

    idx_data = {
        "keyword_index":  dict(keyword_index),
        "sessions":       sessions,
        "total_exchanges": len(exchanges),
        "built":          datetime.now(timezone.utc).isoformat(),
    }
    _save_index(idx_data)
    return len(exchanges)


def recall(query: str, top_k: int = 3) -> list:
    """
    Find past exchanges relevant to query.
    Score = number of query words found in the exchange text.
    Returns top_k exchanges with {user, nova, ts, score}.
    """
    idx_data  = _load_index()
    exchanges = _load_exchanges()
    if not exchanges or not idx_data.get("keyword_index"):
        return []

    keyword_index = idx_data["keyword_index"]
    query_words   = _significant_words(query)

    # Score each exchange by keyword hit count
    score_map: dict = defaultdict(int)
    for word in query_words:
        for ex_idx in keyword_index.get(word, []):
            if 0 <= ex_idx < len(exchanges):
                score_map[ex_idx] += 1

    # Also do a direct substring scan for any short important words missed
    query_lower = query.lower()
    short_words = [w for w in re.findall(r"[a-zA-Z]+", query_lower) if len(w) > 2]
    for ex_idx, ex in enumerate(exchanges):
        combined = (ex.get("user", "") + " " + ex.get("nova", "")).lower()
        for w in short_words:
            if w in combined:
                score_map[ex_idx] += 1

    if not score_map:
        return []

    ranked = sorted(score_map.items(), key=lambda x: x[1], reverse=True)

    results = []
    for ex_idx, score in ranked[:top_k]:
        ex = exchanges[ex_idx]
        results.append({
            "user":  ex.get("user", ""),
            "nova":  ex.get("nova", ""),
            "ts":    ex.get("ts", ""),
            "score": score,
        })
    return results


def to_prompt_context(current_message: str, n_recent: int = 4) -> str:
    """
    Build conversation context for LLM:
    - Last n_recent exchanges (verbatim)
    - Up to 2 relevant past exchanges from recall()
    Returns formatted string, max 600 chars.
    """
    exchanges = _load_exchanges()
    parts     = []

    # Recent exchanges
    recent = exchanges[-n_recent:] if exchanges else []
    for ex in recent:
        u = ex.get("user", "")[:80].replace("\n", " ")
        n = ex.get("nova", "")[:80].replace("\n", " ")
        parts.append(f"Travis: {u}")
        parts.append(f"Nova: {n}")

    # Relevant past exchanges (skip any already in recent)
    recent_set = {ex.get("ts", "") for ex in recent}
    relevant   = recall(current_message, top_k=4)
    added      = 0
    for r in relevant:
        if r.get("ts") in recent_set:
            continue
        if added >= 2:
            break
        u = r.get("user", "")[:60].replace("\n", " ")
        n = r.get("nova", "")[:60].replace("\n", " ")
        parts.append(f"[past] Travis: {u}")
        parts.append(f"[past] Nova: {n}")
        added += 1

    context = "\n".join(parts)
    # Truncate to 600 chars
    if len(context) > 600:
        context = context[:597] + "…"
    return context


def status() -> None:
    """Print total exchanges, date range, index size."""
    idx_data  = _load_index()
    exchanges = _load_exchanges()

    G = "\033[32m"; C = "\033[36m"; B = "\033[1m"; NC = "\033[0m"; DIM = "\033[2m"

    total    = len(exchanges)
    kw_count = len(idx_data.get("keyword_index", {}))
    sessions = idx_data.get("sessions", [])

    date_range = "—"
    if exchanges:
        ts_list = [e.get("ts", "") for e in exchanges if e.get("ts")]
        if ts_list:
            date_range = f"{min(ts_list)[:10]}  →  {max(ts_list)[:10]}"

    print(f"\n{B}N.O.V.A Conversation Memory{NC}")
    print(f"  Total exchanges : {G}{total}{NC}")
    print(f"  Date range      : {C}{date_range}{NC}")
    print(f"  Unique keywords : {kw_count}")
    print(f"  Sessions (days) : {len(sessions)}")
    built = idx_data.get('built') or 'never'
    print(f"  Index built     : {DIM}{built[:19]}{NC}")
    print()


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "status"

    if cmd == "status":
        status()
    elif cmd == "build":
        count = build_index()
        print(f"[conv_memory] indexed {count} exchanges")
    elif cmd == "recall" and len(args) >= 2:
        query   = " ".join(args[1:])
        results = recall(query, top_k=5)
        if not results:
            print("No relevant past exchanges found.")
        else:
            print(f"\nPast exchanges relevant to: \"{query}\"\n")
            for r in results:
                print(f"  score={r['score']}  ts={r['ts'][:10]}")
                print(f"  Travis: {r['user'][:100]}")
                print(f"  Nova:   {r['nova'][:100]}")
                print()
    elif cmd == "context" and len(args) >= 2:
        query = " ".join(args[1:])
        print(to_prompt_context(query))
    else:
        print("Usage: nova conv_memory [status|build|recall <query>|context <query>]")


if __name__ == "__main__":
    main()
