#!/usr/bin/env python3
"""
N.O.V.A Skill Graph

Accumulates Nova's knowledge depth per topic over time using an
exponential moving average. Depth is a 0.0-1.0 signal: how well
she knows something, not just how often she's touched it.

Storage: memory/skill_graph.json
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE            = Path.home() / "Nova"
SKILL_GRAPH_FILE = BASE / "memory/skill_graph.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("general")
    TIMEOUT    = cfg.timeout("standard")
except Exception:
    import os
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "dolphin-mistral")
    TIMEOUT    = 180

SKILL_GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    if SKILL_GRAPH_FILE.exists():
        try:
            return json.loads(SKILL_GRAPH_FILE.read_text())
        except Exception:
            pass
    return {"skills": {}, "last_updated": None}


def _save(data: dict):
    SKILL_GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
    SKILL_GRAPH_FILE.write_text(json.dumps(data, indent=2))


def _slug(topic: str) -> str:
    """Normalize topic to a stable key: lowercase, underscores, no punctuation."""
    s = topic.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s


def update_skill(topic: str, gain: float = 0.1, source: str = "research") -> float:
    """
    Apply one learning event for topic. Uses EMA:
        depth = min(1.0, depth * 0.9 + gain * 0.1)
    Tracks up to 10 most recent sources. Returns new depth.
    """
    data = _load()
    slug = _slug(topic)
    now  = datetime.now(timezone.utc).isoformat()

    skill = data["skills"].get(slug, {
        "label":        topic,
        "depth":        0.0,
        "mentions":     0,
        "last_updated": now,
        "sources":      [],
        "related":      [],
    })

    old_depth = skill["depth"]
    skill["depth"]        = round(min(1.0, old_depth * 0.9 + gain * 0.1), 4)
    skill["mentions"]     = skill.get("mentions", 0) + 1
    skill["last_updated"] = now
    if source:
        skill["sources"].append(source)
        skill["sources"] = skill["sources"][-10:]

    data["skills"][slug] = skill
    data["last_updated"] = now
    _save(data)
    return skill["depth"]


def get_skills(min_depth: float = 0.0, top_n: int = None) -> list:
    """Return list of skill dicts sorted by depth descending."""
    data   = _load()
    skills = []
    for slug, sk in data["skills"].items():
        if sk["depth"] >= min_depth:
            skills.append({"slug": slug, **sk})
    skills.sort(key=lambda x: x["depth"], reverse=True)
    if top_n is not None:
        skills = skills[:top_n]
    return skills


def relate(topic_a: str, topic_b: str):
    """Create a bidirectional link between two topics."""
    data  = _load()
    now   = datetime.now(timezone.utc).isoformat()
    slug_a = _slug(topic_a)
    slug_b = _slug(topic_b)

    for slug, label in ((slug_a, topic_a), (slug_b, topic_b)):
        if slug not in data["skills"]:
            data["skills"][slug] = {
                "label":        label,
                "depth":        0.0,
                "mentions":     0,
                "last_updated": now,
                "sources":      [],
                "related":      [],
            }

    for sl, other in ((slug_a, slug_b), (slug_b, slug_a)):
        related = data["skills"][sl].get("related", [])
        if other not in related:
            related.append(other)
        data["skills"][sl]["related"] = related

    data["last_updated"] = now
    _save(data)


def to_prompt_context(top_n: int = 6) -> str:
    """Compact skill context for LLM injection. Max ~200 chars."""
    skills = get_skills(top_n=top_n)
    if not skills:
        return "Skills: none yet"
    parts = [f"{sk['label']} ({sk['depth']:.2f})" for sk in skills]
    result = "Skills: " + ", ".join(parts)
    return result[:200]


def status():
    """Print all skills grouped by depth tier."""
    G = "\033[32m"; Y = "\033[33m"; C = "\033[36m"; DIM = "\033[2m"
    NC = "\033[0m"; B = "\033[1m"; M = "\033[35m"; R = "\033[31m"

    skills = get_skills()
    data   = _load()

    deep      = [sk for sk in skills if sk["depth"] >  0.6]
    learning  = [sk for sk in skills if 0.3 < sk["depth"] <= 0.6]
    glimpsed  = [sk for sk in skills if sk["depth"] <= 0.3]

    print(f"\n{B}N.O.V.A Skill Graph{NC}  ({len(skills)} topics tracked)")
    last_upd = data.get('last_updated') or 'never'
    print(f"  Last updated: {DIM}{last_upd[:10]}{NC}\n")

    def print_tier(label, col, tier_skills):
        if not tier_skills:
            return
        print(f"  {B}{col}{label}{NC}")
        for sk in tier_skills:
            bar_len = int(sk["depth"] * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            related_str = ""
            if sk.get("related"):
                related_str = f"  {DIM}↔ {', '.join(sk['related'][:3])}{NC}"
            print(f"    {col}{sk['label']:<22}{NC} {bar} {sk['depth']:.3f}"
                  f"  {DIM}×{sk['mentions']}{NC}{related_str}")

    print_tier("Deep (>0.6)",          G, deep)
    print_tier("Learning (0.3–0.6)",   Y, learning)
    print_tier("Glimpsed (<0.3)",      DIM, glimpsed)

    if not skills:
        print(f"  {DIM}No skills recorded yet. Use: skill_graph.py update TOPIC GAIN{NC}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd in ("status", "list") or len(sys.argv) == 1:
        status()

    elif cmd == "top":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        skills = get_skills(top_n=n)
        for sk in skills:
            print(f"{sk['depth']:.3f}  {sk['label']}")

    elif cmd == "update":
        if len(sys.argv) < 3:
            print("Usage: skill_graph.py update TOPIC [GAIN]")
            sys.exit(1)
        topic = sys.argv[2]
        gain  = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1
        new_depth = update_skill(topic, gain)
        G = "\033[32m"; NC = "\033[0m"
        print(f"{G}Updated '{topic}' — depth now {new_depth:.4f}{NC}")

    elif cmd == "relate":
        if len(sys.argv) < 4:
            print("Usage: skill_graph.py relate TOPIC_A TOPIC_B")
            sys.exit(1)
        relate(sys.argv[2], sys.argv[3])
        print(f"Linked '{sys.argv[2]}' <-> '{sys.argv[3]}'")

    elif cmd == "context":
        print(to_prompt_context())

    else:
        status()


if __name__ == "__main__":
    main()
