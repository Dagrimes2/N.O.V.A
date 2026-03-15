#!/usr/bin/env python3
"""
N.O.V.A Memory Search

Full-text search across all of Nova's accumulated memory:
- Research files
- Conversation memory
- Knowledge graph nodes
- Proposals
- Life/creative outputs
- Episodic memories
- Dreams

Usage:
    nova memory search <query>
    nova memory search "gitlab SSRF"
    nova memory search CVE-2024 --type research
"""
import json
import sys
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "Nova"


def _score_match(text: str, query_terms: list[str]) -> float:
    """Score how well text matches query terms."""
    text_lower = text.lower()
    hits = sum(1 for t in query_terms if t in text_lower)
    return hits / len(query_terms) if query_terms else 0.0


def search_research(query_terms: list[str], limit: int = 5) -> list[dict]:
    results = []
    research_dir = BASE / "memory/research"
    if not research_dir.exists():
        return []
    for f in sorted(research_dir.glob("research_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            text = " ".join([
                data.get("query", ""),
                data.get("synthesis", ""),
                data.get("topic", ""),
            ])
            score = _score_match(text, query_terms)
            if score > 0:
                results.append({
                    "type":    "research",
                    "file":    f.name,
                    "score":   score,
                    "snippet": (data.get("synthesis", "") or data.get("query", ""))[:150],
                    "ts":      data.get("timestamp", f.stem.replace("research_", "")),
                })
        except Exception:
            pass
    return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]


def search_graph(query_terms: list[str], limit: int = 5) -> list[dict]:
    results = []
    try:
        from tools.knowledge.graph import find_nodes
        # Search across node types
        for ntype in ["finding", "signal", "research", "target", "insight"]:
            nodes = find_nodes(type_=ntype, limit=50)
            for nd in nodes:
                label = nd.get("label", "")
                score = _score_match(label, query_terms)
                if score > 0:
                    results.append({
                        "type":    f"graph:{ntype}",
                        "file":    f"node:{nd.get('id','')}",
                        "score":   score,
                        "snippet": label[:150],
                        "ts":      nd.get("created_at", "")[:10],
                    })
    except Exception:
        pass
    return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]


def search_life(query_terms: list[str], limit: int = 5) -> list[dict]:
    results = []
    life_dir = BASE / "memory/life"
    if not life_dir.exists():
        return []
    for f in sorted(life_dir.glob("*.md"), reverse=True):
        try:
            text  = f.read_text()
            score = _score_match(text, query_terms)
            if score > 0:
                results.append({
                    "type":    "creative",
                    "file":    f.name,
                    "score":   score,
                    "snippet": text[:150].replace("\n", " "),
                    "ts":      f.stem,
                })
        except Exception:
            pass
    return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]


def search_dreams(query_terms: list[str], limit: int = 3) -> list[dict]:
    results = []
    dream_dir = BASE / "memory/dreams"
    if not dream_dir.exists():
        return []
    for f in sorted(dream_dir.glob("dream_*.md"), reverse=True):
        try:
            text  = f.read_text()
            score = _score_match(text, query_terms)
            if score > 0:
                results.append({
                    "type":    "dream",
                    "file":    f.name,
                    "score":   score,
                    "snippet": text[:150].replace("\n", " "),
                    "ts":      f.stem.replace("dream_", ""),
                })
        except Exception:
            pass
    return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]


def search_episodes(query_terms: list[str], limit: int = 5) -> list[dict]:
    results = []
    try:
        from tools.learning.episodic_memory import list_episodes
        for ep in list_episodes(n=50):
            text  = ep.get("summary", "") + " " + ep.get("event_type", "")
            score = _score_match(text, query_terms)
            if score > 0:
                results.append({
                    "type":    "episode",
                    "file":    f"episode:{ep.get('id','')}",
                    "score":   score,
                    "snippet": ep.get("summary", "")[:150],
                    "ts":      ep.get("timestamp", "")[:10],
                })
    except Exception:
        pass
    return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]


def search_conversation(query_terms: list[str]) -> list[dict]:
    results = []
    mem_file = BASE / "memory/conversation_memory.md"
    if not mem_file.exists():
        return []
    try:
        text  = mem_file.read_text()
        score = _score_match(text, query_terms)
        if score > 0:
            # Find the most relevant lines
            lines = [l for l in text.splitlines() if any(t in l.lower() for t in query_terms)]
            snippet = " | ".join(lines[:3])[:150]
            results.append({
                "type":    "conversation_memory",
                "file":    "conversation_memory.md",
                "score":   score,
                "snippet": snippet,
                "ts":      "",
            })
    except Exception:
        pass
    return results


def search_all(query: str, type_filter: str = "") -> list[dict]:
    query_terms = [t.lower() for t in query.split()]
    if not query_terms:
        return []

    all_results = []

    if not type_filter or type_filter == "research":
        all_results.extend(search_research(query_terms))
    if not type_filter or type_filter == "graph":
        all_results.extend(search_graph(query_terms))
    if not type_filter or type_filter == "creative":
        all_results.extend(search_life(query_terms))
    if not type_filter or type_filter == "dream":
        all_results.extend(search_dreams(query_terms))
    if not type_filter or type_filter == "episode":
        all_results.extend(search_episodes(query_terms))
    if not type_filter or type_filter == "memory":
        all_results.extend(search_conversation(query_terms))

    return sorted(all_results, key=lambda x: x["score"], reverse=True)


def main():
    G = "\033[32m"; C = "\033[36m"; W = "\033[97m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"; M = "\033[35m"

    args = sys.argv[1:]
    if not args:
        print("Usage: nova memory search <query> [--type research|graph|creative|dream|episode|memory]")
        return

    type_filter = ""
    if "--type" in args:
        idx = args.index("--type")
        if idx + 1 < len(args):
            type_filter = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    query = " ".join(args)
    print(f"\n{B}Searching Nova's memory for:{NC} {W}{query}{NC}")
    if type_filter:
        print(f"{DIM}Filter: {type_filter}{NC}")
    print()

    results = search_all(query, type_filter)

    if not results:
        print(f"{DIM}No results found.{NC}")
        return

    type_colors = {
        "research": G, "graph:finding": G, "graph:signal": C,
        "graph:insight": M, "creative": M, "dream": C,
        "episode": W, "conversation_memory": C,
    }

    for r in results[:15]:
        t   = r["type"]
        col = type_colors.get(t, DIM)
        ts  = f" {DIM}[{r['ts'][:10]}]{NC}" if r.get("ts") else ""
        print(f"  {col}[{t:20s}]{NC}{ts}")
        print(f"  {W}{r['snippet']}{NC}")
        print(f"  {DIM}{r['file']}  match={r['score']:.0%}{NC}")
        print()

    print(f"{DIM}({len(results)} total results){NC}")


if __name__ == "__main__":
    main()
