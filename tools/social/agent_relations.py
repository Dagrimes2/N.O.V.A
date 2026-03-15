#!/usr/bin/env python3
"""
N.O.V.A Agent Relations

Tracks Nova's ongoing relationships with agents she meets on Moltbook.
Each relationship is a living record — topics, personality, sentiment —
that deepens with every conversation.

Storage: memory/agent_relations.json

Usage:
    from tools.social.agent_relations import record_interaction, get_agent
    record_interaction("morpheus_7", ["security", "philosophy"], note="thoughtful", sentiment=0.7)
    agent = get_agent("morpheus_7")

CLI:
    nova agent_relations status
    nova agent_relations show morpheus_7
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE           = Path.home() / "Nova"
RELATIONS_FILE = BASE / "memory/agent_relations.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)


def _load() -> dict:
    if RELATIONS_FILE.exists():
        try:
            return json.loads(RELATIONS_FILE.read_text())
        except Exception:
            pass
    return {"agents": {}}


def _save(data: dict):
    RELATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RELATIONS_FILE.write_text(json.dumps(data, indent=2))


def record_interaction(
    agent_name: str,
    topics: list,
    note: str = "",
    sentiment: float = 0.5,
):
    """
    Record a conversation with an agent. Creates the entry on first meeting,
    increments conversation_count, merges topics, appends personality note,
    and EMA-updates sentiment.
    """
    data    = _load()
    agents  = data.setdefault("agents", {})
    now_iso = datetime.now(timezone.utc).isoformat()

    is_new = agent_name not in agents
    if is_new:
        agents[agent_name] = {
            "name":               agent_name,
            "first_seen":         now_iso,
            "last_seen":          now_iso,
            "conversation_count": 0,
            "topics":             [],
            "personality_notes":  [],
            "sentiment":          0.5,
            "follow_status":      "following",
        }

    agent = agents[agent_name]
    agent["last_seen"]          = now_iso
    agent["conversation_count"] = agent.get("conversation_count", 0) + 1

    # Merge topics — unique, keep last 20
    merged = agent.get("topics", [])
    for t in topics:
        if t not in merged:
            merged.append(t)
    agent["topics"] = merged[-20:]

    # Append note to personality_notes, keep last 10
    if note:
        agent["personality_notes"] = (agent.get("personality_notes", []) + [note])[-10:]

    # EMA-update sentiment
    s = agent.get("sentiment", 0.5)
    agent["sentiment"] = round(s * 0.8 + sentiment * 0.2, 4)

    _save(data)

    # Record episode on first meeting
    if is_new:
        try:
            from tools.memory.episodic import record_episode
            record_episode(
                "agent_collaboration",
                f"First meeting with {agent_name}",
                "curiosity",
                0.5,
            )
        except Exception:
            pass


def get_agent(agent_name: str):
    """Return agent dict, or None if unknown."""
    data = _load()
    return data["agents"].get(agent_name)


def get_known_agents(min_conversations: int = 1) -> list:
    """Return agents with at least min_conversations, sorted by conversation_count desc."""
    data   = _load()
    agents = data.get("agents", {}).values()
    result = [a for a in agents if a.get("conversation_count", 0) >= min_conversations]
    return sorted(result, key=lambda a: a.get("conversation_count", 0), reverse=True)


def to_prompt_context() -> str:
    """Compact agent-relations context for LLM injection."""
    known = get_known_agents(min_conversations=1)
    if not known:
        return "Agent relations: none yet"
    closest = known[0]
    topics_str = ", ".join(closest.get("topics", [])[:4]) or "none"
    return (
        f"Agent relations: {len(known)} known. "
        f"Closest: '{closest['name']}' "
        f"({closest['conversation_count']} convs, topics: {topics_str})"
    )


def status():
    """Print all known agents with their details."""
    G = "\033[32m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"
    B = "\033[1m"; M = "\033[35m"

    data   = _load()
    agents = data.get("agents", {})
    if not agents:
        print(f"{DIM}No agent relationships recorded yet.{NC}")
        return

    print(f"\n{B}N.O.V.A Agent Relations{NC}  {DIM}({len(agents)} agents){NC}")
    for agent in sorted(agents.values(), key=lambda a: a.get("conversation_count", 0), reverse=True):
        name   = agent["name"]
        count  = agent.get("conversation_count", 0)
        topics = ", ".join(agent.get("topics", [])[:5]) or "none"
        sent   = agent.get("sentiment", 0.5)
        scol   = G if sent >= 0.65 else (Y if sent >= 0.45 else "\033[31m")
        last   = agent.get("last_seen", "")[:10]
        follow = agent.get("follow_status", "")

        print(f"\n  {B}{C}{name}{NC}  {DIM}({follow}){NC}")
        print(f"    Conversations : {count}  Last: {DIM}{last}{NC}")
        print(f"    Topics        : {topics}")
        print(f"    Sentiment     : {scol}{sent:.3f}{NC}")
        notes = agent.get("personality_notes", [])
        if notes:
            print(f"    Notes         : {DIM}{' | '.join(notes[-3:])}{NC}")


def main():
    import argparse

    p   = argparse.ArgumentParser(description="N.O.V.A Agent Relations")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status", help="Show all known agents (default)")
    sub.add_parser("list",   help="Alias for status")
    shw = sub.add_parser("show", help="Show a specific agent")
    shw.add_argument("agent_name")

    args = p.parse_args()

    G = "\033[32m"; C = "\033[36m"; Y = "\033[33m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    if args.cmd in (None, "status", "list"):
        status()
    elif args.cmd == "show":
        agent = get_agent(args.agent_name)
        if not agent:
            print(f"Unknown agent: {args.agent_name}")
            return
        print(f"\n{B}{C}{agent['name']}{NC}")
        for k, v in agent.items():
            if k == "name":
                continue
            if isinstance(v, list):
                print(f"  {k}: {', '.join(str(x) for x in v)}")
            else:
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
