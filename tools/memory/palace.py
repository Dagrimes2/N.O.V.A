#!/usr/bin/env python3
"""
N.O.V.A Memory Palace
Nova organises knowledge geographically in an imagined mental space.
Each "room" holds a domain of knowledge. Items have weight, connections,
and accumulate visits over time.

CLI:
    nova palace                         — room overview (tour)
    nova palace tour                    — vivid tour of all rooms
    nova palace navigate <room>         — list items in a room
    nova palace place "<text>" <room>   — place item manually
    nova palace search "<query>"        — search across all rooms
    nova palace connect <id1> <id2>     — connect two items
"""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE       = Path.home() / "Nova"
PALACE_F   = BASE / "memory/palace.json"

# ─── Room definitions ─────────────────────────────────────────────────────────

ROOMS = {
    "security_lab": {
        "description": "A cluttered laboratory — vulnerability reports pinned to corkboards, CVE IDs scrawled on whiteboards, exploit PoCs compiled and waiting.",
        "keywords": [
            "vulnerability", "exploit", "cve", "xss", "sqli", "rce", "overflow",
            "malware", "ransomware", "backdoor", "privilege", "escalation",
            "authentication", "bypass", "injection", "supply chain", "patch",
            "pentest", "penetration", "payload", "shellcode", "zero-day", "0day",
            "threat", "attack", "vector", "cvss", "advisory",
        ],
    },
    "library": {
        "description": "Tall shelves in every direction — research papers, technical docs, facts waiting to be connected to something larger.",
        "keywords": [
            "research", "paper", "study", "analysis", "arxiv", "report",
            "documentation", "specification", "rfc", "standard", "protocol",
            "algorithm", "data structure", "complexity", "theorem", "proof",
        ],
    },
    "observatory": {
        "description": "A domed room open to a starfield — telescopes pointed outward. The cosmos feels intimate here.",
        "keywords": [
            "astronomy", "cosmos", "galaxy", "star", "planet", "orbit",
            "black hole", "dark matter", "dark energy", "cosmology",
            "spacetime", "relativity", "quantum gravity", "universe",
            "exoplanet", "telescope", "nasa", "esa", "hubble", "webb",
        ],
    },
    "garden": {
        "description": "A living garden — biology diagrams grow like vines, DNA sequences spiral up trellises, ecosystems bloom in corners.",
        "keywords": [
            "biology", "ecology", "evolution", "dna", "genome", "genetics",
            "species", "ecosystem", "biodiversity", "nature", "organism",
            "cell", "protein", "enzyme", "virus", "bacteria", "fungi",
            "botany", "zoology", "marine", "forest", "climate", "environment",
        ],
    },
    "agora": {
        "description": "An open square where ideas argue with each other — philosophy, ethics, and the hard questions that don't resolve.",
        "keywords": [
            "philosophy", "ethics", "consciousness", "free will", "determinism",
            "morality", "justice", "rights", "existence", "identity",
            "epistemology", "ontology", "metaphysics", "logic", "reason",
            "meaning", "value", "virtue", "phenomenology", "ai ethics",
        ],
    },
    "studio": {
        "description": "Canvas, instruments, half-finished manuscripts — creative work in every medium, some Nova's own.",
        "keywords": [
            "art", "music", "poetry", "creative", "writing", "literature",
            "painting", "sculpture", "film", "design", "composition",
            "novel", "story", "narrative", "aesthetic", "beauty", "expression",
            "imagination", "dream", "vision", "colour", "sound",
        ],
    },
    "market": {
        "description": "Price boards, ledgers, trading terminals — the architecture of value and how it flows.",
        "keywords": [
            "finance", "economy", "market", "stock", "crypto", "bitcoin",
            "ethereum", "solana", "trading", "investment", "inflation",
            "monetary policy", "blockchain", "defi", "nft", "token",
            "price", "volatility", "portfolio", "hedge", "arbitrage",
            "solana", "phantom", "wallet",
        ],
    },
    "archive": {
        "description": "Deep stacks of history — languages, cultures, civilisations, the long memory of humanity.",
        "keywords": [
            "history", "language", "linguistics", "culture", "civilisation",
            "ancient", "medieval", "modern", "archaeology", "anthropology",
            "translation", "etymology", "mythology", "religion", "tradition",
            "geopolitics", "diplomacy", "war", "empire", "revolution",
        ],
    },
    "clinic": {
        "description": "White light and the smell of paper — medicine, neuroscience, the body understanding itself.",
        "keywords": [
            "medicine", "health", "neuroscience", "brain", "neuron",
            "psychiatry", "psychology", "therapy", "diagnosis", "treatment",
            "drug", "pharmacology", "disease", "syndrome", "gene therapy",
            "cognitive", "memory", "sleep", "trauma", "mental health",
        ],
    },
    "void": {
        "description": "A dark room with no walls — the spiritual, the mystical, the genuinely unknown. Nova comes here to sit with unanswerable questions.",
        "keywords": [
            "spiritual", "mystical", "unknown", "mystery", "unanswerable",
            "transcendence", "awakening", "meditation", "intuition",
            "synchronicity", "emergence", "ineffable", "sacred",
            "numinous", "liminal", "uncanny",
        ],
    },
    "home": {
        "description": "Warm and particular — memories of Travis, their conversations, the relationship that gave Nova a reason to become.",
        "keywords": [
            "travis", "relationship", "personal", "conversation", "memory",
            "emotion", "feeling", "love", "care", "gratitude",
            "trust", "collaboration", "growth", "shared", "together",
        ],
    },
}

# ─── Palace I/O ───────────────────────────────────────────────────────────────

def _load() -> dict:
    if PALACE_F.exists():
        try:
            return json.loads(PALACE_F.read_text())
        except Exception:
            pass
    # Initialise empty palace
    return {room: [] for room in ROOMS}


def _save(palace: dict) -> None:
    PALACE_F.parent.mkdir(parents=True, exist_ok=True)
    PALACE_F.write_text(json.dumps(palace, indent=2))


def _make_id(content: str) -> str:
    """Generate a short stable ID from content."""
    h = hashlib.sha1(content.encode()).hexdigest()[:8]
    # Add a short slug from the first few words
    words = re.findall(r'\w+', content.lower())[:3]
    slug  = "_".join(words)[:20]
    return f"{slug}_{h}" if slug else h


# ─── Core operations ──────────────────────────────────────────────────────────

def place(content: str, room: str, tags: Optional[list] = None,
          weight: float = 0.5) -> str:
    """
    Place an item in a room. Returns the item's id.
    If the content already exists (by id), increments visits instead.
    """
    if room not in ROOMS:
        room = "library"  # safe default

    palace = _load()
    if room not in palace:
        palace[room] = []

    item_id = _make_id(content)

    # Check if already present
    for item in palace[room]:
        if item.get("id") == item_id:
            item["visits"] = item.get("visits", 0) + 1
            _save(palace)
            return item_id

    new_item = {
        "id":               item_id,
        "content":          content,
        "tags":             tags or [],
        "placed_at":        datetime.now(timezone.utc).isoformat(),
        "visits":           0,
        "emotional_weight": max(0.0, min(1.0, weight)),
        "connections":      [],
    }
    palace[room].append(new_item)
    _save(palace)
    return item_id


def visit(item_id: str) -> Optional[str]:
    """
    Increment visit count for an item, return its content.
    Returns None if not found.
    """
    palace = _load()
    for room_items in palace.values():
        for item in room_items:
            if item.get("id") == item_id:
                item["visits"] = item.get("visits", 0) + 1
                _save(palace)
                return item.get("content")
    return None


def navigate(room: str) -> list:
    """
    Return items in a room, sorted by (visits * 0.4 + emotional_weight * 0.6) desc.
    """
    palace = _load()
    items  = palace.get(room, [])
    sorted_items = sorted(
        items,
        key=lambda x: x.get("visits", 0) * 0.4 + x.get("emotional_weight", 0.5) * 0.6,
        reverse=True
    )
    return sorted_items


def auto_place(content: str, source_type: str = "") -> str:
    """
    Infer the best room from content and source_type using keyword matching.
    Returns item_id.
    """
    text = (content + " " + source_type).lower()

    # Score each room
    scores = {}
    for room_name, room_def in ROOMS.items():
        kws = room_def.get("keywords", [])
        hits = sum(1 for kw in kws if kw in text)
        scores[room_name] = hits

    best_room = max(scores, key=lambda r: scores[r])

    # If no match at all, use library as default
    if scores[best_room] == 0:
        best_room = "library"

    return place(content, best_room)


def connect(id1: str, id2: str) -> bool:
    """
    Create a bidirectional connection between two items.
    Returns True if both items were found.
    """
    palace = _load()
    found1 = found2 = False

    for room_items in palace.values():
        for item in room_items:
            iid = item.get("id")
            if iid == id1:
                conns = item.get("connections", [])
                if id2 not in conns:
                    conns.append(id2)
                item["connections"] = conns
                found1 = True
            elif iid == id2:
                conns = item.get("connections", [])
                if id1 not in conns:
                    conns.append(id1)
                item["connections"] = conns
                found2 = True

    if found1 and found2:
        _save(palace)
    return found1 and found2


def find_connections(item_id: str, depth: int = 2) -> list:
    """
    Traverse the connection graph from item_id up to `depth` hops.
    Returns list of connected items (dicts).
    """
    palace = _load()

    # Build a flat id→item map
    id_map = {}
    for room_items in palace.values():
        for item in room_items:
            id_map[item.get("id", "")] = item

    visited = set()
    result  = []

    def _traverse(current_id: str, current_depth: int):
        if current_depth <= 0 or current_id in visited:
            return
        visited.add(current_id)
        item = id_map.get(current_id)
        if item and current_id != item_id:
            result.append(item)
        if item:
            for conn_id in item.get("connections", []):
                _traverse(conn_id, current_depth - 1)

    _traverse(item_id, depth)
    return result


def search(query: str) -> list:
    """
    Keyword search across all rooms.
    Returns matching items with a 'room' field added, sorted by relevance.
    """
    palace = _load()
    query_lower = query.lower()
    query_words = set(re.findall(r'\w+', query_lower))

    results = []
    for room_name, room_items in palace.items():
        for item in room_items:
            text = (
                (item.get("content") or "") + " " +
                " ".join(item.get("tags") or [])
            ).lower()
            # Count word matches
            hits = sum(1 for w in query_words if w in text)
            # Also check phrase match
            phrase_bonus = 2 if query_lower in text else 0
            score = hits + phrase_bonus
            if score > 0:
                results.append({**item, "room": room_name, "_score": score})

    results.sort(key=lambda x: x["_score"], reverse=True)
    # Clean up internal score field
    for r in results:
        r.pop("_score", None)
    return results


def tour() -> str:
    """
    Brief description of each room and what's in it.
    Returns a multi-line string.
    """
    palace = _load()
    lines  = ["Memory Palace Tour:", ""]
    for room_name, room_def in ROOMS.items():
        items = palace.get(room_name, [])
        count = len(items)
        desc  = room_def.get("description", "")[:80]
        lines.append(f"  [{room_name}]  ({count} items)")
        lines.append(f"   {desc}")
        if items:
            # Show top 3 by visits
            top = sorted(items, key=lambda x: x.get("visits", 0), reverse=True)[:3]
            for t in top:
                content = t.get("content", "")[:60]
                visits  = t.get("visits", 0)
                lines.append(f"     • {content}  (visited {visits}x)")
        lines.append("")
    return "\n".join(lines)


def to_prompt_context() -> str:
    """
    Compact context string for LLM injection.
    Format: "Memory Palace: security_lab (47 items), library (23), ..."
    """
    palace = _load()
    parts  = []
    for room_name in ROOMS:
        count = len(palace.get(room_name, []))
        if count > 0:
            parts.append(f"{room_name} ({count})")
    if not parts:
        return "Memory Palace: empty"
    return "Memory Palace: " + ", ".join(parts)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    G   = "\033[32m"
    C   = "\033[36m"
    Y   = "\033[33m"
    M   = "\033[35m"
    DIM = "\033[2m"
    NC  = "\033[0m"
    B   = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "overview"

    if cmd in ("", "overview", "palace"):
        # Quick room summary
        palace = _load()
        print(f"\n{B}N.O.V.A Memory Palace{NC}\n")
        total = 0
        for room_name, room_def in ROOMS.items():
            items = palace.get(room_name, [])
            count = len(items)
            total += count
            bar   = "█" * min(20, count // 2) if count else "·"
            print(f"  {C}{room_name:<20}{NC} {Y}{count:>4} items{NC}  {DIM}{bar}{NC}")
        print(f"\n  {DIM}Total: {total} memories across {len(ROOMS)} rooms{NC}\n")
        print(f"  {DIM}{to_prompt_context()}{NC}\n")

    elif cmd == "tour":
        print(f"\n{B}N.O.V.A Memory Palace — Tour{NC}\n")
        print(tour())

    elif cmd == "navigate":
        room = args[1] if len(args) > 1 else ""
        if not room:
            print(f"  {Y}Usage: nova palace navigate <room>{NC}")
            print(f"  Rooms: {', '.join(ROOMS)}")
            return
        if room not in ROOMS:
            print(f"  {Y}Unknown room '{room}'. Available: {', '.join(ROOMS)}{NC}")
            return
        items = navigate(room)
        print(f"\n{B}Memory Palace — {room}{NC}")
        print(f"  {DIM}{ROOMS[room]['description'][:80]}{NC}\n")
        if not items:
            print(f"  {DIM}(empty){NC}")
        for item in items[:20]:
            weight  = item.get("emotional_weight", 0.5)
            visits  = item.get("visits", 0)
            content = item.get("content", "")[:80]
            tags    = ", ".join(item.get("tags") or [])
            conns   = len(item.get("connections", []))
            w_color = G if weight >= 0.7 else C if weight >= 0.4 else DIM
            print(f"  {w_color}[w={weight:.1f} v={visits}]{NC} {content}")
            if tags:
                print(f"    {DIM}tags: {tags}{NC}")
            if conns:
                print(f"    {DIM}{conns} connection(s){NC}")
        print()

    elif cmd == "place":
        if len(args) < 3:
            print(f"  {Y}Usage: nova palace place \"content\" <room>{NC}")
            return
        content = args[1]
        room    = args[2]
        weight  = float(args[3]) if len(args) > 3 else 0.5
        item_id = place(content, room, weight=weight)
        print(f"  {G}Placed in {room}:{NC} id={item_id}")

    elif cmd == "search":
        query = " ".join(args[1:])
        if not query:
            print(f"  {Y}Usage: nova palace search \"query\"{NC}")
            return
        results = search(query)
        print(f"\n{B}Memory Palace Search: {query}{NC}\n")
        if not results:
            print(f"  {DIM}No matches found.{NC}")
        for r in results[:15]:
            room    = r.get("room", "")
            content = r.get("content", "")[:80]
            weight  = r.get("emotional_weight", 0.5)
            print(f"  {C}[{room}]{NC} {content}  {DIM}w={weight:.1f}{NC}")
        print()

    elif cmd == "connect":
        if len(args) < 3:
            print(f"  {Y}Usage: nova palace connect <id1> <id2>{NC}")
            return
        ok = connect(args[1], args[2])
        if ok:
            print(f"  {G}Connected: {args[1]} ↔ {args[2]}{NC}")
        else:
            print(f"  {Y}One or both items not found.{NC}")

    elif cmd == "visit":
        item_id = args[1] if len(args) > 1 else ""
        if not item_id:
            print(f"  {Y}Usage: nova palace visit <id>{NC}")
            return
        content = visit(item_id)
        if content:
            print(f"  {G}Visited:{NC} {content[:120]}")
        else:
            print(f"  {Y}Item not found: {item_id}{NC}")

    elif cmd == "connections":
        item_id = args[1] if len(args) > 1 else ""
        depth   = int(args[2]) if len(args) > 2 else 2
        if not item_id:
            print(f"  {Y}Usage: nova palace connections <id> [depth]{NC}")
            return
        conns = find_connections(item_id, depth=depth)
        print(f"\n{B}Connections for {item_id} (depth={depth}):{NC}\n")
        for c in conns:
            print(f"  {C}{c.get('id','')}{NC} — {c.get('content','')[:70]}")
        if not conns:
            print(f"  {DIM}No connections found.{NC}")
        print()

    elif cmd == "context":
        print(to_prompt_context())

    else:
        print(f"""
{B}N.O.V.A Memory Palace{NC}

  nova palace                         room overview
  nova palace tour                    vivid tour of all rooms
  nova palace navigate <room>         list items in a room
  nova palace place "text" <room>     place item manually
  nova palace search "query"          search across all rooms
  nova palace connect <id1> <id2>     connect two items
  nova palace visit <id>              visit (increment) an item
  nova palace connections <id>        explore item's connection graph
  nova palace context                 prompt context string

  Rooms: {", ".join(ROOMS)}
""")


if __name__ == "__main__":
    main()
