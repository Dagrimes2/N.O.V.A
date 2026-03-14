#!/usr/bin/env python3
"""
N.O.V.A Knowledge Graph CLI

Usage:
    nova graph stats
    nova graph query [--type TYPE] [--label LABEL] [--limit N]
    nova graph related LABEL [--type TYPE] [--depth N]
    nova graph ingest           # backfill all existing memory into graph
    nova graph show NODE_ID
"""
import sys
from pathlib import Path

ROOT = Path.home() / "Nova"
sys.path.insert(0, str(ROOT))

from tools.knowledge.graph import stats, find_nodes, related, get_node, neighbors


# ── ANSI colours ──────────────────────────────────────────────────────────────
R  = "\033[0;31m"
G  = "\033[0;32m"
Y  = "\033[0;33m"
B  = "\033[0;34m"
M  = "\033[0;35m"
C  = "\033[0;36m"
W  = "\033[1;37m"
DIM= "\033[2m"
NC = "\033[0m"

TYPE_COLORS = {
    "finding":       C,
    "target":        G,
    "signal":        Y,
    "pattern":       M,
    "research":      B,
    "research_topic":B,
    "proposal":      Y,
    "gan_attack":    R,
    "action":        DIM,
    "cve":           R,
    "knowledge":     W,
    "program":       G,
    "script":        DIM,
    "agent":         W,
}

RELATION_COLORS = {
    "found_on":      G,
    "triggered_by":  Y,
    "led_to":        C,
    "confirmed_by":  G,
    "generated_by":  M,
    "part_of":       B,
    "related_to":    B,
    "targets":       R,
    "references":    C,
}

def col(s: str, color: str) -> str:
    return f"{color}{s}{NC}"

def type_col(t: str) -> str:
    return col(t, TYPE_COLORS.get(t, W))

def rel_col(r: str) -> str:
    return col(r, RELATION_COLORS.get(r, DIM))


# ── Formatters ────────────────────────────────────────────────────────────────

def fmt_node(n: dict, show_data: bool = False) -> str:
    label    = n.get("label","?")[:90]
    ntype    = n.get("type","?")
    nid      = n.get("id","?")
    updated  = (n.get("updated_at") or n.get("created_at",""))[:16]
    direction= n.get("_direction","")
    relation = n.get("relation","")
    weight   = n.get("weight",1.0)

    arrow = ""
    if relation:
        arrow = f"  {rel_col(f'─[{relation}]─→')}  " if direction=="out" \
               else f"  {rel_col(f'←─[{relation}]─')}  "

    base = (f"  {DIM}{str(nid).rjust(4)}{NC} "
            f"{type_col(f'[{ntype}]'):20s} "
            f"{W}{label}{NC}"
            f"{arrow}"
            f"  {DIM}{updated}{NC}")

    if show_data and n.get("data"):
        import json
        data_str = json.dumps(n["data"], indent=2)
        base += f"\n       {DIM}{data_str[:400]}{NC}"

    return base


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_stats():
    s = stats()
    print(f"\n{W}N.O.V.A Knowledge Graph{NC}")
    print(f"  {C}{s['total_nodes']}{NC} nodes   {C}{s['total_edges']}{NC} edges\n")

    print(f"  {W}Nodes by type:{NC}")
    for t, cnt in sorted(s["nodes_by_type"].items(), key=lambda x: -x[1]):
        bar = "█" * min(cnt, 40)
        print(f"    {type_col(t):30s}  {C}{cnt:4d}{NC}  {DIM}{bar}{NC}")

    print(f"\n  {W}Edges by relation:{NC}")
    for r, cnt in sorted(s["edges_by_relation"].items(), key=lambda x: -x[1]):
        bar = "█" * min(cnt, 40)
        print(f"    {rel_col(r):30s}  {C}{cnt:4d}{NC}  {DIM}{bar}{NC}")
    print()


def cmd_query(args: list):
    ntype = None
    label = None
    limit = 20

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--type","-t") and i+1 < len(args):
            ntype = args[i+1]; i += 2
        elif a in ("--label","-l") and i+1 < len(args):
            label = args[i+1]; i += 2
        elif a in ("--limit","-n") and i+1 < len(args):
            limit = int(args[i+1]); i += 2
        else:
            # positional = label
            label = a; i += 1

    nodes = find_nodes(type_=ntype, label=label, limit=limit)
    print(f"\n{W}Query results ({len(nodes)} nodes):{NC}")
    if not nodes:
        print(f"  {DIM}No nodes found.{NC}\n")
        return
    for n in nodes:
        print(fmt_node(n))
    print()


def cmd_related(args: list):
    if not args:
        print("Usage: nova graph related LABEL [--type TYPE] [--depth N]")
        return

    label = args[0]
    ntype = None
    depth = 2

    i = 1
    while i < len(args):
        a = args[i]
        if a in ("--type","-t") and i+1 < len(args):
            ntype = args[i+1]; i += 2
        elif a in ("--depth","-d") and i+1 < len(args):
            depth = int(args[i+1]); i += 2
        else:
            i += 1

    # Find anchor node first
    anchor = find_nodes(type_=ntype, label=label, limit=1)
    if not anchor:
        print(f"  {R}No node found matching '{label}'{NC}\n")
        return

    a = anchor[0]
    print(f"\n{W}Related to:{NC} {type_col(a['type'])} {W}{a['label']}{NC}  (depth={depth})\n")

    # Show direct neighbors with relation labels
    nbs = neighbors(a["id"], direction="both")
    if nbs:
        print(f"  {W}Direct connections:{NC}")
        for nb in nbs:
            print(fmt_node(nb))

    # Show deeper relatives
    rels = related(label, type_=ntype, depth=depth)
    deeper = [r for r in rels if r["id"] not in {nb["id"] for nb in nbs}]
    if deeper:
        print(f"\n  {W}Deeper connections (depth≤{depth}):{NC}")
        for n in deeper[:30]:
            print(fmt_node(n))
    print()


def cmd_show(args: list):
    if not args:
        print("Usage: nova graph show NODE_ID")
        return
    try:
        nid = int(args[0])
    except ValueError:
        print(f"  {R}NODE_ID must be an integer{NC}")
        return

    n = get_node(nid)
    if not n:
        print(f"  {R}Node {nid} not found{NC}\n")
        return

    print(f"\n{W}Node {nid}:{NC}")
    print(fmt_node(n, show_data=True))

    nbs = neighbors(nid, direction="both")
    if nbs:
        print(f"\n  {W}Connections:{NC}")
        for nb in nbs:
            print(fmt_node(nb))
    print()


def cmd_ingest():
    print(f"{W}Running backfill ingestion...{NC}\n")
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/knowledge/graph_ingest.py"), "--verbose"],
        cwd=str(ROOT)
    )
    sys.exit(result.returncode)


def cmd_help():
    print(f"""
{W}N.O.V.A Knowledge Graph{NC}

  {C}nova graph stats{NC}
      Node/edge counts by type and relation.

  {C}nova graph query{NC} [--type TYPE] [--label LABEL] [--limit N]
      Find nodes. TYPE: finding, target, signal, research, proposal,
      gan_attack, pattern, cve, program, action, agent.
      Example: nova graph query --type finding --label gitlab

  {C}nova graph related{NC} LABEL [--type TYPE] [--depth N]
      Show everything connected to a node (BFS up to depth).
      Example: nova graph related "gitlab.com" --depth 3

  {C}nova graph show{NC} NODE_ID
      Show a specific node and its direct connections.

  {C}nova graph ingest{NC}
      Backfill all existing Nova memory into the graph.
""")


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: list = None):
    argv = argv or sys.argv[1:]
    if not argv or argv[0] in ("help", "--help", "-h"):
        cmd_help(); return
    cmd  = argv[0]
    rest = argv[1:]
    if cmd == "stats":    cmd_stats()
    elif cmd == "query":  cmd_query(rest)
    elif cmd == "related":cmd_related(rest)
    elif cmd == "show":   cmd_show(rest)
    elif cmd == "ingest": cmd_ingest()
    else:
        print(f"  {R}Unknown command: {cmd}{NC}"); cmd_help()


if __name__ == "__main__":
    main()
