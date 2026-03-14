#!/usr/bin/env python3
"""
N.O.V.A Knowledge Graph — Backfill ingestion script.

Reads all existing Nova memory files and inserts nodes+edges into graph.db.
Safe to run multiple times (all operations are upserts).

Usage:
    python3 tools/knowledge/graph_ingest.py [--verbose]
"""
import sys, json
from pathlib import Path

ROOT = Path.home() / "Nova"
sys.path.insert(0, str(ROOT))

from tools.knowledge.graph import link, node_id_for, add_node, add_edge

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

def log(msg: str):
    if VERBOSE:
        print(f"  {msg}")

def _safe_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text())
    except Exception as e:
        log(f"skip {path.name}: {e}")
        return None


# ── 1. Autonomous history ─────────────────────────────────────────────────────

def ingest_autonomous_history():
    path = ROOT / "memory/autonomous_history.json"
    if not path.exists():
        return
    data = _safe_json(path)
    if not isinstance(data, list):
        return
    count = 0
    for entry in data:
        action  = entry.get("action", "unknown")
        target  = entry.get("target", "unknown")
        ts      = entry.get("timestamp", "")
        reason  = entry.get("reason", "")

        # Action node (unique per action+target combo)
        action_label = f"{action}:{target[:80]}"
        action_id = add_node("action", action_label, {
            "action": action, "target": target,
            "timestamp": ts, "reason": reason
        })

        # Topic node for the target
        topic_id = node_id_for("research_topic", target[:120], {"source": "autonomous"})
        add_edge(action_id, topic_id, "led_to")

        count += 1
    print(f"[autonomous_history] {count} actions ingested")


# ── 2. Research files ─────────────────────────────────────────────────────────

def ingest_research():
    research_dir = ROOT / "memory/research"
    if not research_dir.exists():
        return
    files = list(research_dir.glob("*.json"))
    count = 0
    for f in files:
        data = _safe_json(f)
        if not isinstance(data, dict):
            continue
        query     = data.get("query", f.stem)
        ts        = data.get("timestamp", "")
        synthesis = data.get("synthesis", "")
        sources   = data.get("sources", {})

        r_id = add_node("research", query[:160], {
            "timestamp": ts,
            "synthesis": synthesis[:500] if synthesis else "",
            "file": f.name
        })

        # Link CVEs
        for cve in sources.get("cves", []):
            cve_id = cve.get("id", "")
            if cve_id:
                c_id = node_id_for("cve", cve_id, {
                    "score": cve.get("score"),
                    "description": cve.get("description", "")[:300]
                })
                add_edge(r_id, c_id, "references", data={"research_file": f.name})

        # Link Wikipedia topic
        wiki = sources.get("wikipedia", {})
        if wiki.get("title"):
            w_id = node_id_for("knowledge", wiki["title"], {"url": wiki.get("url","")})
            add_edge(r_id, w_id, "related_to")

        count += 1
    print(f"[research] {count} research entries ingested")


# ── 3. Proposals ─────────────────────────────────────────────────────────────

def ingest_proposals():
    proposals_dir = ROOT / "memory/proposals"
    if not proposals_dir.exists():
        return
    files = list(proposals_dir.glob("*.json"))
    count = 0
    for f in files:
        data = _safe_json(f)
        if not isinstance(data, dict):
            continue
        file_target = data.get("file", "unknown")
        issue       = data.get("issue", "")[:200]
        status      = data.get("status", "pending")
        risk        = data.get("risk", "unknown")
        confidence  = data.get("confidence", 0)

        label = f"{file_target}:{issue[:60]}"
        p_id = add_node("proposal", label[:200], {
            "file": file_target, "issue": issue,
            "status": status, "risk": risk,
            "confidence": confidence,
            "proposed_at": data.get("proposed_at",""),
            "source_file": f.name
        })

        # Link to the script it targets
        s_id = node_id_for("script", file_target, {})
        add_edge(p_id, s_id, "targets")

        count += 1
    print(f"[proposals] {count} proposals ingested")


# ── 4. GAN approved attacks ───────────────────────────────────────────────────

def ingest_gan():
    gan_dir = ROOT / "memory/gan/approved"
    if not gan_dir.exists():
        return

    # Attack files
    attack_files = list(gan_dir.glob("gan_attack_*.json"))
    for f in attack_files:
        data = _safe_json(f)
        if not isinstance(data, dict):
            continue
        program   = data.get("program", "unknown")
        iteration = data.get("iteration", 0)
        attack    = data.get("attack", "")[:300]
        verdict   = data.get("evaluation", {}).get("verdict", "unknown")
        score     = data.get("evaluation", {}).get("score", 0)

        label = f"gan_attack:{f.stem}"
        a_id = add_node("gan_attack", label, {
            "program": program, "iteration": iteration,
            "verdict": verdict, "score": score,
            "attack_summary": attack[:300],
            "file": f.name
        })

        # Link to program
        prog_id = node_id_for("program", program, {})
        add_edge(a_id, prog_id, "targets", weight=score)

    # Mutation files
    mutation_files = list(gan_dir.glob("mutations_*.json"))
    mutation_count = 0
    for f in mutation_files:
        data = _safe_json(f)
        if not isinstance(data, list):
            continue
        for m in data:
            host    = m.get("host","")
            path    = m.get("path","")
            signals = m.get("signals", [])
            program = m.get("program","unknown")

            if not host:
                continue

            label = f"{host}{path}"
            m_id = node_id_for("finding", label[:200], {
                "host": host, "path": path,
                "signals": signals, "source": "gan_mutation",
                "program": program
            })

            t_id = node_id_for("target", host, {"program": program})
            add_edge(m_id, t_id, "found_on")

            for sig in signals:
                s_id = node_id_for("signal", sig, {})
                add_edge(m_id, s_id, "triggered_by")

            mutation_count += 1

    print(f"[gan] {len(attack_files)} attacks + {mutation_count} mutations ingested")


# ── 5. Memory store (confirmed findings from pipeline) ───────────────────────

def ingest_memory_store():
    index_file = ROOT / "memory/store/index.jsonl"
    if not index_file.exists():
        return
    count = 0
    with open(index_file) as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except Exception:
                continue
            host       = entry.get("host","")
            text       = entry.get("text","")
            decision   = entry.get("decision","hold")
            confidence = float(entry.get("confidence",0))
            ts         = entry.get("timestamp","")

            if not host:
                continue

            f_id = node_id_for("finding", text[:200], {
                "host": host, "decision": decision,
                "confidence": confidence, "timestamp": ts
            })
            t_id = node_id_for("target", host, {})
            add_edge(f_id, t_id, "found_on", weight=confidence)
            count += 1
    print(f"[memory_store] {count} findings ingested")


# ── 6. Watchlist ──────────────────────────────────────────────────────────────

def ingest_watchlist():
    path = ROOT / "memory/watchlist/watchlist.json"
    if not path.exists():
        return
    data = _safe_json(path)
    if not isinstance(data, dict):
        return
    targets = data.get("targets", {})
    count = 0
    for host, info in targets.items():
        node_id_for("target", host, {
            "priority": info.get("priority", 0),
            "notes":    info.get("notes","")[:300],
            "decision": info.get("decision",""),
            "confidence": info.get("confidence", 0)
        })
        count += 1
    print(f"[watchlist] {count} targets ingested")


# ── 7. Nova identity / programs ───────────────────────────────────────────────

def ingest_identity():
    path = ROOT / "memory/nova_identity.json"
    if not path.exists():
        return
    data = _safe_json(path)
    if not isinstance(data, dict):
        return
    node_id_for("agent", "N.O.V.A", {
        "version":        data.get("version",""),
        "operator":       data.get("operator",""),
        "mission":        data.get("mission",""),
        "total_scans":    data.get("stats",{}).get("total_scans",0),
        "findings_stored":data.get("stats",{}).get("findings_stored",0),
        "emotional_state":data.get("emotional_state",{})
    })
    print(f"[identity] N.O.V.A identity node ingested")


# ── 8. Programs list ──────────────────────────────────────────────────────────

def ingest_programs():
    programs_dir = ROOT / "programs"
    if not programs_dir.exists():
        return
    count = 0
    for f in programs_dir.glob("*.json"):
        data = _safe_json(f)
        if not isinstance(data, dict):
            continue
        name = data.get("name") or data.get("program") or f.stem
        node_id_for("program", name[:120], {
            "file": f.name,
            "platform": data.get("platform",""),
        })
        count += 1
    if count:
        print(f"[programs] {count} bug bounty programs ingested")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("N.O.V.A Knowledge Graph — backfill ingestion starting...")
    ingest_identity()
    ingest_watchlist()
    ingest_autonomous_history()
    ingest_research()
    ingest_proposals()
    ingest_gan()
    ingest_memory_store()
    ingest_programs()
    print("\nDone.")

    # Print summary
    from tools.knowledge.graph import stats
    s = stats()
    print(f"\n  Nodes : {s['total_nodes']}  |  Edges : {s['total_edges']}")
    print(f"  By type  : {s['nodes_by_type']}")
    print(f"  By edge  : {s['edges_by_relation']}")


if __name__ == "__main__":
    main()
