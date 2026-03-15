#!/usr/bin/env python3
"""
N.O.V.A Memory Consolidation Engine

Promotes episodic memories to semantic (long-term) knowledge.
This is how Nova builds up a stable worldview from experiences.

Process:
  1. Scan recent episodic memories (from episodic_memory.py)
  2. Cluster similar episodes by topic/theme
  3. Synthesize clusters into semantic facts using LLM
  4. Store semantic facts in knowledge graph + AtomSpace
  5. Mark consolidated episodes to avoid re-processing

Inspired by human memory consolidation during sleep.
Nova runs this during dream cycles.

Usage:
    nova memory consolidate           run one consolidation pass
    nova memory semantic              show learned semantic facts
    nova memory consolidate --stats   show consolidation statistics
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE         = Path.home() / "Nova"
SEMANTIC_DIR = BASE / "memory/semantic"
SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)
CONSOL_LOG   = BASE / "memory/inner/consolidation_log.json"
CONSOL_LOG.parent.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("reasoning")
    TIMEOUT    = cfg.timeout("medium")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 120


# ─── Episode loading ──────────────────────────────────────────────────────────

def _load_unconsolidated_episodes(max_eps: int = 30) -> list[dict]:
    """Load recent episodes that haven't been consolidated yet."""
    eps_file = BASE / "memory/learning/episodic_memory.json"
    if not eps_file.exists():
        return []
    try:
        all_eps = json.loads(eps_file.read_text())
    except Exception:
        return []

    # Load consolidation log to find already-processed IDs
    consolidated_ids = set()
    if CONSOL_LOG.exists():
        try:
            log = json.loads(CONSOL_LOG.read_text())
            consolidated_ids = set(log.get("consolidated_ids", []))
        except Exception:
            pass

    new_eps = [
        ep for ep in all_eps
        if str(ep.get("id", ep.get("timestamp", ""))) not in consolidated_ids
    ]
    return new_eps[-max_eps:]


def _cluster_episodes(episodes: list[dict]) -> list[list[dict]]:
    """
    Simple keyword clustering — group episodes by dominant topic.
    Returns list of clusters (each cluster is a list of episodes).
    """
    topic_keywords = {
        "security":  ["scan", "vulnerability", "cve", "exploit", "auth", "injection"],
        "research":  ["research", "study", "find", "discover", "learn", "paper"],
        "markets":   ["btc", "eth", "price", "market", "buy", "sell", "crypto"],
        "identity":  ["think", "dream", "feel", "identity", "self", "purpose"],
        "social":    ["travis", "mastodon", "post", "communicate", "share"],
    }

    clusters: dict[str, list[dict]] = {k: [] for k in topic_keywords}
    clusters["other"] = []

    for ep in episodes:
        text = json.dumps(ep).lower()
        matched = False
        for topic, keywords in topic_keywords.items():
            if any(kw in text for kw in keywords):
                clusters[topic].append(ep)
                matched = True
                break
        if not matched:
            clusters["other"].append(ep)

    # Return non-empty clusters
    return [eps for eps in clusters.values() if len(eps) >= 2]


def _synthesize_cluster(cluster: list[dict], topic: str = "") -> dict | None:
    """Use LLM to synthesize a cluster of episodes into a semantic fact."""
    summaries = []
    for ep in cluster[:5]:
        parts = []
        if ep.get("action"):
            parts.append(f"action={ep['action']}")
        if ep.get("target"):
            parts.append(f"target={ep['target']}")
        if ep.get("outcome") or ep.get("result"):
            parts.append(f"outcome={ep.get('outcome') or ep.get('result','')}")
        summaries.append(", ".join(parts))

    prompt = f"""You are N.O.V.A consolidating {len(cluster)} experiences into long-term knowledge.

Experiences:
{chr(10).join(f'- {s}' for s in summaries)}

Extract 1-2 concise semantic facts (things Nova has learned) from these experiences.
Format each fact as: FACT: <short declarative statement>
Keep each fact under 15 words.
Focus on generalizable knowledge, not specific details."""

    try:
        import requests as req
        resp = req.post(OLLAMA_URL, json={
            "model": MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.3, "num_predict": 150}
        }, timeout=TIMEOUT)
        text = resp.json().get("response", "").strip()
        facts = []
        for line in text.splitlines():
            if line.startswith("FACT:"):
                facts.append(line[5:].strip())
        return {"facts": facts, "source_count": len(cluster), "topic": topic} if facts else None
    except Exception:
        return None


def _store_semantic_fact(fact: str, topic: str, source_count: int) -> None:
    """Store a semantic fact in the semantic memory store."""
    ts      = datetime.now(timezone.utc).isoformat()
    ts_fn   = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    out_file = SEMANTIC_DIR / f"fact_{ts_fn}.json"
    data     = {
        "fact":         fact,
        "topic":        topic,
        "source_count": source_count,
        "created":      ts,
        "confidence":   min(1.0, 0.5 + source_count * 0.1),
    }
    out_file.write_text(json.dumps(data, indent=2))

    # Also add to knowledge graph
    try:
        from tools.knowledge.graph import add_node, add_edge
        nid = add_node("semantic_fact", fact, {"topic": topic, "confidence": data["confidence"]})
    except Exception:
        pass

    # And to AtomSpace
    try:
        from tools.opencog.atomspace import get_atomspace, SimpleTruthValue
        as_ = get_atomspace()
        as_.add_node("SemanticFactNode", fact,
                     SimpleTruthValue(data["confidence"], min(1.0, source_count / 5.0)))
        as_.close()
    except Exception:
        pass


def _mark_consolidated(episodes: list[dict]) -> None:
    """Record that these episodes have been consolidated."""
    log = {"consolidated_ids": []}
    if CONSOL_LOG.exists():
        try:
            log = json.loads(CONSOL_LOG.read_text())
        except Exception:
            pass

    existing = set(log.get("consolidated_ids", []))
    for ep in episodes:
        ep_id = str(ep.get("id", ep.get("timestamp", "")))
        if ep_id:
            existing.add(ep_id)

    log["consolidated_ids"] = list(existing)
    log["last_run"] = datetime.now(timezone.utc).isoformat()
    CONSOL_LOG.write_text(json.dumps(log, indent=2))


def consolidate(verbose: bool = True) -> dict:
    """
    Run one memory consolidation pass.
    Returns {facts_added, episodes_processed, clusters}.
    """
    episodes = _load_unconsolidated_episodes()
    if not episodes:
        if verbose:
            print("No new episodes to consolidate.")
        return {"facts_added": 0, "episodes_processed": 0}

    clusters   = _cluster_episodes(episodes)
    facts_added = 0

    if verbose:
        print(f"Consolidating {len(episodes)} episodes in {len(clusters)} clusters...")

    for cluster in clusters:
        topic  = "general"
        # Guess topic from first episode
        text = json.dumps(cluster[0]).lower()
        for t in ["security", "research", "markets", "identity", "social"]:
            if t in text:
                topic = t
                break

        result = _synthesize_cluster(cluster, topic)
        if result:
            for fact in result["facts"]:
                _store_semantic_fact(fact, topic, result["source_count"])
                facts_added += 1
                if verbose:
                    print(f"  [{topic}] {fact}")

    _mark_consolidated(episodes)
    return {"facts_added": facts_added, "episodes_processed": len(episodes),
            "clusters": len(clusters)}


def list_semantic_facts(n: int = 20) -> list[dict]:
    """Return recent semantic facts."""
    files = sorted(SEMANTIC_DIR.glob("fact_*.json"), reverse=True)[:n]
    facts = []
    for f in files:
        try:
            facts.append(json.loads(f.read_text()))
        except Exception:
            pass
    return facts


def consolidation_stats() -> dict:
    n_facts = len(list(SEMANTIC_DIR.glob("fact_*.json")))
    log = {}
    if CONSOL_LOG.exists():
        try:
            log = json.loads(CONSOL_LOG.read_text())
        except Exception:
            pass
    return {
        "semantic_facts": n_facts,
        "consolidated_episodes": len(log.get("consolidated_ids", [])),
        "last_run": log.get("last_run", "never"),
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "consolidate"

    if cmd == "consolidate":
        result = consolidate(verbose=True)
        print(f"\n{G}Consolidation complete:{NC}")
        print(f"  Semantic facts added : {result['facts_added']}")
        print(f"  Episodes processed   : {result['episodes_processed']}")
        print(f"  Clusters formed      : {result.get('clusters', 0)}")

    elif cmd in ("semantic", "facts"):
        facts = list_semantic_facts()
        if not facts:
            print(f"{DIM}No semantic facts yet. Run: nova memory consolidate{NC}")
            return
        print(f"\n{B}N.O.V.A Semantic Memory ({len(facts)} facts){NC}")
        topic_colors = {
            "security": R, "research": C, "markets": G,
            "identity": M if (M := "\033[35m") else C, "social": Y,
        }
        for f in facts:
            col = topic_colors.get(f.get("topic", ""), DIM)
            print(f"  {col}[{f.get('topic','?'):10s}]{NC}  {f['fact']}  "
                  f"{DIM}conf={f.get('confidence',0):.2f}{NC}")

    elif cmd == "--stats" or cmd == "stats":
        s = consolidation_stats()
        print(f"\n{B}Memory Consolidation Stats{NC}")
        print(f"  Semantic facts       : {G}{s['semantic_facts']}{NC}")
        print(f"  Consolidated episodes: {C}{s['consolidated_episodes']}{NC}")
        print(f"  Last run             : {DIM}{s['last_run']}{NC}")

    else:
        print("Usage: nova memory [consolidate|semantic|stats]")


if __name__ == "__main__":
    main()
