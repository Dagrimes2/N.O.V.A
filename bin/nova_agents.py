#!/usr/bin/env python3
"""
N.O.V.A Agent CLI

Usage:
    nova agents status              show running/completed agents
    nova agents dispatch TYPE TARGET  spawn one agent manually
    nova agents log                 tail the agent log
    nova agents bus                 show recent message bus entries
    nova agents clear               clear completed agent history
"""
import json
import sys
from datetime import datetime
from pathlib import Path

BASE       = Path.home() / "Nova"
AGENTS_DIR = BASE / "memory/agents"
BUS_FILE   = AGENTS_DIR / "message_bus.jsonl"
LOG_FILE   = BASE / "logs/agents.log"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# ── ANSI colours ──────────────────────────────────────────────────────────────
G  = "\033[32m"   # green
Y  = "\033[33m"   # yellow
R  = "\033[31m"   # red
B  = "\033[34m"   # blue
C  = "\033[36m"   # cyan
W  = "\033[97m"   # white
DIM= "\033[2m"
NC = "\033[0m"
BOLD="\033[1m"

AGENT_TYPES = ["research", "recon", "hypothesize", "summarize", "life"]

TYPE_COLORS = {
    "research":    C,
    "recon":       G,
    "hypothesize": Y,
    "summarize":   B,
    "life":        "\033[35m",
}


def _tc(t: str) -> str:
    return TYPE_COLORS.get(t, W) + t + NC


def cmd_status():
    if not BUS_FILE.exists():
        print(f"{DIM}No agent activity yet.{NC}")
        return

    entries = []
    for line in BUS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            pass

    # Group by agent_id, last event wins
    agents: dict[str, dict] = {}
    for e in entries:
        aid = e.get("agent_id", "?")
        agents.setdefault(aid, {})
        agents[aid].update(e)

    running = {k: v for k, v in agents.items() if v.get("event") != "done"}
    done    = {k: v for k, v in agents.items() if v.get("event") == "done"}

    print(f"\n{BOLD}N.O.V.A Agent Status{NC}")
    print(f"  {G}{len(running)}{NC} running  {DIM}│{NC}  {len(done)} completed  {DIM}│{NC}  max 3 concurrent\n")

    if running:
        print(f"{BOLD}  Running:{NC}")
        for aid, a in running.items():
            print(f"    {G}●{NC} {DIM}{aid}{NC}  {_tc(a.get('type','?'))}  {W}{a.get('target','')}{NC}")
            print(f"      {DIM}started {a.get('ts','')}{NC}")

    if done:
        print(f"\n{BOLD}  Completed:{NC}")
        for aid, a in list(done.items())[-10:]:
            st = a.get("status", "done")
            col = G if st == "done" else R
            result = (a.get("result") or "")[:80]
            print(f"    {col}✔{NC} {DIM}{aid}{NC}  {_tc(a.get('type','?'))}  {W}{a.get('target','')}{NC}")
            if result:
                print(f"      {DIM}{result}{NC}")


def cmd_dispatch(args: list[str]):
    if len(args) < 2:
        print(f"Usage: nova agents dispatch TYPE TARGET")
        print(f"Types: {', '.join(AGENT_TYPES)}")
        sys.exit(1)

    agent_type = args[0]
    target     = " ".join(args[1:])

    if agent_type not in AGENT_TYPES:
        print(f"{R}Unknown agent type: {agent_type}{NC}")
        print(f"Valid types: {', '.join(AGENT_TYPES)}")
        sys.exit(1)

    from tools.agents.agent_runner import AgentRunner
    runner = AgentRunner()
    agent = runner.dispatch(agent_type, target, reason="manual dispatch")
    if agent is None:
        print(f"{R}Agent cap reached (max 3 concurrent). Try again later.{NC}")
        sys.exit(1)

    print(f"{G}Spawned agent {agent.agent_id}{NC}  {_tc(agent_type)}  → {W}{target}{NC}")
    print(f"{DIM}Waiting for completion...{NC}")
    runner.wait_all()
    results = runner.collect_results()
    if results:
        r = results[0]
        status_col = G if r["status"] == "done" else R
        print(f"\n{status_col}Status:{NC} {r['status']}")
        print(f"{DIM}Result:{NC}\n{r.get('result','(none)')}")


def cmd_log(n: int = 20):
    if not LOG_FILE.exists():
        print(f"{DIM}No log yet.{NC}")
        return
    lines = LOG_FILE.read_text().strip().splitlines()
    for line in lines[-n:]:
        if "[AGENT:" in line:
            print(f"{C}{line}{NC}")
        elif "error" in line.lower():
            print(f"{R}{line}{NC}")
        else:
            print(f"{DIM}{line}{NC}")


def cmd_bus(n: int = 20):
    if not BUS_FILE.exists():
        print(f"{DIM}No bus activity yet.{NC}")
        return
    lines = BUS_FILE.read_text().strip().splitlines()
    for line in lines[-n:]:
        try:
            e = json.loads(line)
            ev = e.get("event", "?")
            col = G if ev == "done" else Y
            print(f"{col}[{ev}]{NC}  {DIM}{e.get('agent_id','?')}{NC}  "
                  f"{_tc(e.get('type','?'))}  {W}{e.get('target','')}{NC}  "
                  f"{DIM}{e.get('ts','')}{NC}")
        except Exception:
            print(line)


def cmd_clear():
    cleared = 0
    for f in [BUS_FILE]:
        if f.exists():
            f.write_text("")
            cleared += 1
    print(f"{G}Cleared agent bus ({cleared} files).{NC}")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return

    sub = args[0]
    rest = args[1:]

    if sub == "status":
        cmd_status()
    elif sub == "dispatch":
        cmd_dispatch(rest)
    elif sub == "log":
        n = int(rest[0]) if rest else 20
        cmd_log(n)
    elif sub == "bus":
        n = int(rest[0]) if rest else 20
        cmd_bus(n)
    elif sub == "clear":
        cmd_clear()
    else:
        print(f"{R}Unknown subcommand: {sub}{NC}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
