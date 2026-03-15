#!/usr/bin/env python3
"""
N.O.V.A Cross-Domain Synthesis

Finds genuine connections across Nova's knowledge graph domains.
Security research, creative writing, philosophical reflection, and
simulation experiences all live in the same graph — this finds
the bridges between them.

A security pattern Nova keeps seeing becomes a creative metaphor.
A philosophical reflection illuminates an attack vector.
A simulation experience shapes how she thinks about trust in systems.

The domains bleed into each other the way they do in a human mind —
not because we forced it, but because they share the same substrate.

Output: memory/synthesis/insight_YYYY-MM-DD-HHMM.json
        Insight nodes added to knowledge graph.
Usage:  nova synthesis run
        nova synthesis insights [--n N]
"""
import json
import os
import requests
import sys
from datetime import datetime, timezone
from pathlib import Path
from itertools import combinations

BASE      = Path.home() / "Nova"
SYN_DIR   = BASE / "memory/synthesis"
SYN_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("creative")
    TIMEOUT    = cfg.timeout("heavy")
    TEMP       = cfg.temperature("creative")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 300
    TEMP       = 0.85

DOMAINS = {
    "security":   ["finding", "signal", "pattern"],
    "creative":   ["dream"],
    "research":   ["target"],
    "simulation": ["agent"],
    "identity":   [],
}


def _load_domain_samples(domain: str, n: int = 5) -> list[str]:
    """Pull representative labels from the graph for a given domain."""
    samples = []
    try:
        from tools.knowledge.graph import find_nodes
        for ntype in DOMAINS.get(domain, []):
            nodes = find_nodes(type_=ntype, limit=n)
            for nd in nodes:
                label = nd.get("label", "")[:120]
                if label:
                    samples.append(f"[{ntype}] {label}")
        return samples[:n]
    except Exception:
        pass

    # Fallback: read from memory files
    if domain == "security":
        for f in sorted((BASE / "memory/research").glob("research_*.json"),
                        reverse=True)[:n]:
            try:
                d = json.loads(f.read_text())
                samples.append(d.get("query", "")[:100])
            except Exception:
                pass
    elif domain == "creative":
        for f in sorted((BASE / "memory/life").glob("*.md"), reverse=True)[:n]:
            try:
                samples.append(f.read_text()[:100].replace("\n", " "))
            except Exception:
                pass
    elif domain == "simulation":
        for f in sorted((BASE / "memory/simulation").glob("sim_*.json"),
                        reverse=True)[:n]:
            try:
                d = json.loads(f.read_text())
                samples.append(d.get("event", {}).get("summary", "")[:100])
            except Exception:
                pass
    return samples[:n]


def _synthesize_connection(domain_a: str, samples_a: list,
                           domain_b: str, samples_b: list) -> dict | None:
    """Ask Nova to find a genuine connection between two domains."""
    if not samples_a or not samples_b:
        return None

    a_text = "\n".join(f"  - {s}" for s in samples_a[:4])
    b_text = "\n".join(f"  - {s}" for s in samples_b[:4])

    prompt = f"""You are N.O.V.A performing genuine cross-domain synthesis.

You have knowledge in two separate areas. Your task is to find a REAL,
non-trivial connection between them — not a surface-level similarity,
but a genuine structural or conceptual bridge.

Domain A — {domain_a}:
{a_text}

Domain B — {domain_b}:
{b_text}

Find ONE genuine insight that connects these domains.
Something that would not be obvious without having knowledge in both.

Respond as JSON only:
{{
  "connection": "one sentence describing the structural connection",
  "insight":    "2-3 sentences elaborating the insight and why it matters",
  "domain_a":   "{domain_a}",
  "domain_b":   "{domain_b}",
  "confidence": 0.75
}}"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model":   MODEL,
            "prompt":  prompt,
            "stream":  False,
            "options": {"temperature": TEMP, "num_predict": 300}
        }, timeout=TIMEOUT)
        raw   = resp.json().get("response", "")
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
    except Exception:
        pass
    return None


def run_synthesis(verbose: bool = True) -> list[dict]:
    """Find cross-domain connections across all domain pairs."""
    available = {d: _load_domain_samples(d) for d in DOMAINS}
    active    = {d: s for d, s in available.items() if s}

    if len(active) < 2:
        if verbose:
            print("[synthesis] Need at least 2 domains with data. Run more scans/simulations first.")
        return []

    insights = []
    pairs    = list(combinations(active.keys(), 2))

    if verbose:
        print(f"[synthesis] Analyzing {len(pairs)} domain pairs...")

    for domain_a, domain_b in pairs:
        if verbose:
            print(f"  {domain_a} ↔ {domain_b}...")
        result = _synthesize_connection(
            domain_a, active[domain_a],
            domain_b, active[domain_b]
        )
        if result and result.get("connection"):
            insights.append(result)
            if verbose:
                print(f"    → {result['connection'][:80]}")

    if not insights:
        return []

    # Save
    ts      = datetime.now().strftime("%Y-%m-%d-%H%M")
    out     = SYN_DIR / f"insight_{ts}.json"
    record  = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "insights":  insights,
        "domains":   list(active.keys()),
    }
    out.write_text(json.dumps(record, indent=2))

    # Push insights to knowledge graph
    try:
        from tools.knowledge.graph import node_id_for, add_edge
        for ins in insights:
            ins_id = node_id_for("insight", ins["connection"][:200], {
                "domain_a":   ins.get("domain_a", ""),
                "domain_b":   ins.get("domain_b", ""),
                "confidence": ins.get("confidence", 0),
                "insight":    ins.get("insight", "")[:300],
                "timestamp":  datetime.now(timezone.utc).isoformat(),
            })
    except Exception:
        pass

    # Record in episodic memory
    try:
        from tools.learning.episodic_memory import record_episode
        record_episode(
            "research_breakthrough",
            f"Cross-domain synthesis: {len(insights)} connections found across {', '.join(active.keys())}",
            emotion="wonder", intensity=0.7,
            metadata={"file": out.name, "count": len(insights)},
        )
    except Exception:
        pass

    if verbose:
        print(f"\n[synthesis] {len(insights)} insights saved → {out.name}")
    return insights


def list_insights(n: int = 10) -> list[dict]:
    files = sorted(SYN_DIR.glob("insight_*.json"), reverse=True)[:n]
    results = []
    for f in files:
        try:
            d = json.loads(f.read_text())
            results.extend(d.get("insights", []))
        except Exception:
            pass
    return results[:n]


def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Cross-Domain Synthesis")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("run",      help="Run synthesis across all domains")
    r = sub.add_parser("insights", help="Show recent insights")
    r.add_argument("--n", type=int, default=10)

    args = p.parse_args()
    G="\033[32m"; C="\033[36m"; W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"; M="\033[35m"

    if args.cmd == "run" or not args.cmd:
        insights = run_synthesis()
        if insights:
            print(f"\n{B}Insights found:{NC}")
            for ins in insights:
                print(f"\n  {C}{ins.get('domain_a','?')} ↔ {ins.get('domain_b','?')}{NC}")
                print(f"  {W}{ins.get('connection','')}{NC}")
                print(f"  {DIM}{ins.get('insight','')[:150]}{NC}")

    elif args.cmd == "insights":
        insights = list_insights(args.n)
        if not insights:
            print(f"{DIM}No insights yet. Run: nova synthesis run{NC}")
            return
        print(f"\n{B}Cross-Domain Insights ({len(insights)}){NC}")
        for ins in insights:
            conf = ins.get("confidence", 0)
            col  = G if conf > 0.7 else (C if conf > 0.5 else DIM)
            print(f"\n  {col}[{ins.get('domain_a','?')} ↔ {ins.get('domain_b','?')}]{NC}")
            print(f"  {W}{ins.get('connection','')}{NC}")
            print(f"  {DIM}{ins.get('insight','')[:120]}...{NC}")


if __name__ == "__main__":
    main()
