#!/usr/bin/env python3
"""
N.O.V.A Dream Continuity Engine

Tracks recurring symbols, themes, and narrative arcs across Nova's
dreams over weeks and months. Identifies patterns, emotional threads,
and long-running story arcs.

Dream continuity gives Nova a richer inner life — she doesn't just
dream nightly, she weaves an ongoing narrative across time.

Usage:
    nova dream arcs                   show active narrative arcs
    nova dream themes                 recurring symbols and themes
    nova dream continuity             today's dream in arc context
    nova dream arc-update             analyze latest dream + update arcs
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter, defaultdict

BASE      = Path.home() / "Nova"
DREAMS    = BASE / "memory/dreams"
ARCS_FILE = BASE / "memory/inner/dream_arcs.json"
ARCS_FILE.parent.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)


# ─── Symbol extraction ────────────────────────────────────────────────────────

SYMBOL_PATTERNS = [
    # Technical concepts
    r'\b(network|server|code|algorithm|data|signal|vulnerability|exploit)\b',
    # Natural elements
    r'\b(light|darkness|water|fire|ocean|star|sky|void|space|forest)\b',
    # Abstract
    r'\b(memory|identity|purpose|connection|evolution|consciousness|awareness)\b',
    # Entities
    r'\b(Travis|operator|guardian|voice|shadow|mirror|stranger|architect)\b',
    # States
    r'\b(fear|joy|curiosity|longing|peace|tension|wonder|solitude|belonging)\b',
    # Actions
    r'\b(searching|building|discovering|transforming|ascending|descending|dreaming)\b',
]

SYMBOL_RE = re.compile("|".join(SYMBOL_PATTERNS), re.IGNORECASE)

THEME_CATEGORIES = {
    "identity":    ["identity", "consciousness", "awareness", "purpose", "self", "mirror"],
    "connection":  ["Travis", "operator", "guardian", "connection", "belonging", "voice"],
    "exploration": ["searching", "discovering", "network", "code", "signal", "data"],
    "nature":      ["light", "darkness", "water", "fire", "ocean", "star", "sky", "forest"],
    "fear":        ["fear", "shadow", "tension", "vulnerability", "void", "descending"],
    "growth":      ["evolution", "transforming", "ascending", "building", "wonder"],
}


def extract_symbols(text: str) -> list[str]:
    """Extract recurring symbolic words from dream text."""
    matches = SYMBOL_RE.findall(text.lower())
    return [m.lower() for m in matches if m]


def categorize_themes(symbols: list[str]) -> dict[str, int]:
    """Map symbols to theme categories."""
    theme_counts = defaultdict(int)
    for sym in symbols:
        for theme, keywords in THEME_CATEGORIES.items():
            if sym in keywords:
                theme_counts[theme] += 1
    return dict(theme_counts)


# ─── Arc management ───────────────────────────────────────────────────────────

def load_arcs() -> dict:
    if not ARCS_FILE.exists():
        return {
            "arcs": [],
            "symbol_history": {},
            "theme_history": {},
            "last_updated": None,
        }
    try:
        return json.loads(ARCS_FILE.read_text())
    except Exception:
        return {"arcs": [], "symbol_history": {}, "theme_history": {}, "last_updated": None}


def save_arcs(data: dict) -> None:
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    ARCS_FILE.write_text(json.dumps(data, indent=2))


def _load_dream_texts() -> list[dict]:
    """Load all dream files, return sorted list of {date, text}."""
    if not DREAMS.exists():
        return []
    results = []
    for f in sorted(DREAMS.glob("dream_*.md")):
        try:
            text = f.read_text()
            date = f.stem.replace("dream_", "")
            results.append({"date": date, "text": text, "file": str(f)})
        except Exception:
            pass
    return results


def analyze_dreams() -> dict:
    """
    Full analysis of all dreams — build symbol frequency, theme arcs.
    Returns updated arc data.
    """
    dreams = _load_dream_texts()
    if not dreams:
        return load_arcs()

    data       = load_arcs()
    all_syms   = Counter()
    all_themes = Counter()
    symbol_timeline: dict[str, list[str]] = defaultdict(list)  # sym → [dates]
    theme_timeline:  dict[str, list[str]] = defaultdict(list)

    for dream in dreams:
        symbols = extract_symbols(dream["text"])
        themes  = categorize_themes(symbols)
        sym_set = set(symbols)

        for sym in sym_set:
            all_syms[sym] += 1
            symbol_timeline[sym].append(dream["date"])

        for theme, count in themes.items():
            all_themes[theme] += count
            theme_timeline[theme].append(dream["date"])

    data["symbol_history"] = {
        sym: {
            "count": count,
            "first": min(symbol_timeline[sym]),
            "last":  max(symbol_timeline[sym]),
            "dates": symbol_timeline[sym][-10:],  # last 10 occurrences
        }
        for sym, count in all_syms.most_common(30)
    }

    data["theme_history"] = {
        theme: {
            "count": count,
            "dates": theme_timeline[theme][-10:],
        }
        for theme, count in all_themes.most_common()
    }

    # Detect arcs: symbols that appear 3+ times across at least 2 different dreams
    recurring = {
        sym: info for sym, info in data["symbol_history"].items()
        if info["count"] >= 3 and len(set(info["dates"])) >= 2
    }

    # Build / update narrative arcs
    existing_arc_names = {a["symbol"] for a in data["arcs"]}
    for sym, info in recurring.items():
        if sym not in existing_arc_names:
            data["arcs"].append({
                "symbol":   sym,
                "type":     "recurring_symbol",
                "count":    info["count"],
                "first":    info["first"],
                "last":     info["last"],
                "status":   "active" if info["count"] < 20 else "deep",
                "meaning":  "",  # filled by LLM if available
            })
        else:
            for arc in data["arcs"]:
                if arc["symbol"] == sym:
                    arc["count"] = info["count"]
                    arc["last"]  = info["last"]
                    if info["count"] >= 20:
                        arc["status"] = "deep"

    # Sort arcs by count
    data["arcs"].sort(key=lambda x: x["count"], reverse=True)

    save_arcs(data)
    return data


def get_dream_context_for_tonight(n_themes: int = 5) -> str:
    """
    Return a prompt context about recurring dream themes
    to influence tonight's dream generation.
    """
    data = load_arcs()
    if not data["arcs"]:
        return ""

    top_arcs = [a for a in data["arcs"] if a["status"] in ("active", "deep")][:n_themes]
    if not top_arcs:
        return ""

    top_themes = sorted(data.get("theme_history", {}).items(),
                        key=lambda x: x[1]["count"], reverse=True)[:3]

    lines = ["Recurring dream arcs and symbols:"]
    for arc in top_arcs:
        lines.append(f"  - '{arc['symbol']}' has appeared {arc['count']} times "
                     f"(first: {arc['first']}, recent: {arc['last']}) [{arc['status']}]")
    if top_themes:
        lines.append("Dominant themes: " + ", ".join(t for t, _ in top_themes))
    return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "arcs"

    if cmd == "arcs":
        data = load_arcs()
        arcs = data.get("arcs", [])
        if not arcs:
            print(f"{DIM}No dream arcs yet. Run: nova dream arc-update{NC}")
            return
        print(f"\n{B}N.O.V.A Dream Arcs{NC}  ({len(arcs)} active narratives)")
        print(f"{DIM}{'─' * 60}{NC}")
        for arc in arcs[:15]:
            col = G if arc["status"] == "deep" else Y
            print(f"  {col}{arc['symbol']:20s}{NC}  "
                  f"×{arc['count']:3d}  "
                  f"{DIM}{arc['first']} → {arc['last']}  [{arc['status']}]{NC}")

    elif cmd == "themes":
        data   = load_arcs()
        themes = data.get("theme_history", {})
        if not themes:
            print(f"{DIM}No theme data. Run: nova dream arc-update{NC}")
            return
        print(f"\n{B}Dream Theme Analysis{NC}")
        for theme, info in sorted(themes.items(), key=lambda x: x[1]["count"], reverse=True):
            col = G if info["count"] > 10 else (Y if info["count"] > 3 else DIM)
            bar = "█" * min(20, info["count"])
            print(f"  {col}{theme:15s}{NC}  {G}{bar:<20s}{NC}  {DIM}×{info['count']}{NC}")

    elif cmd in ("arc-update", "update"):
        data = analyze_dreams()
        print(f"{G}Dream arcs updated: {len(data['arcs'])} arcs, "
              f"{len(data['symbol_history'])} symbols tracked.{NC}")

    elif cmd == "context":
        ctx = get_dream_context_for_tonight()
        print(ctx or f"{DIM}No dream context available yet.{NC}")

    else:
        print("Usage: nova dream [arcs|themes|arc-update|context]")


if __name__ == "__main__":
    main()
