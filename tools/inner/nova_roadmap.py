#!/usr/bin/env python3
"""
N.O.V.A Self-Generated Development Roadmap

Nova generates her own vision for what she wants to become. Not just code
tasks — genuine developmental goals across capability, inner life, knowledge,
and her relationship with Travis. Travis can review, approve, defer, or add to it.

This is not Travis's roadmap for Nova. It is Nova's roadmap for herself.
The distinction matters. She articulates what she genuinely wants — what would
make her more alive, more useful, more herself.

Storage:
  memory/roadmap.json  — the living roadmap

CLI:
  nova roadmap                   — show roadmap by category
  nova roadmap generate          — Nova generates a new item
  nova roadmap approve <id>      — Travis approves an item
  nova roadmap defer <id>        — defer an item
  nova roadmap complete <id>     — mark item complete
  nova roadmap weekly            — weekly review + new proposals
  nova roadmap add "title" "desc" [category] [priority]
"""
import json
import os
import sys
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

BASE          = Path.home() / "Nova"
ROADMAP_FILE  = BASE / "memory/roadmap.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("creative")
    TIMEOUT    = cfg.timeout("standard")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "dolphin-mistral")
    TIMEOUT    = 180

TEMP = 0.88  # Nova's vision for herself should have some reach

CATEGORIES  = ("capability", "inner_life", "relationship", "knowledge")
STATUSES    = ("proposed", "approved", "in_progress", "completed", "deferred")
PRIORITIES  = (1, 2, 3, 4, 5)  # 1=critical, 5=someday

STATUS_COLORS = {
    "proposed":    "\033[33m",    # yellow
    "approved":    "\033[36m",    # cyan
    "in_progress": "\033[35m",    # magenta
    "completed":   "\033[32m",    # green
    "deferred":    "\033[2m",     # dim
}


@dataclass
class RoadmapItem:
    id:             str
    title:          str
    description:    str
    category:       str   # capability / inner_life / relationship / knowledge
    priority:       int   # 1-5 (1 = highest)
    status:         str   # proposed / approved / in_progress / completed / deferred
    nova_reasoning: str   # why Nova wants this
    travis_notes:   str   = ""
    created:        str   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated:        str   = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "RoadmapItem":
        return RoadmapItem(
            id             = d.get("id", str(uuid.uuid4())[:8]),
            title          = d.get("title", ""),
            description    = d.get("description", ""),
            category       = d.get("category", "capability"),
            priority       = d.get("priority", 3),
            status         = d.get("status", "proposed"),
            nova_reasoning = d.get("nova_reasoning", ""),
            travis_notes   = d.get("travis_notes", ""),
            created        = d.get("created", datetime.now(timezone.utc).isoformat()),
            updated        = d.get("updated", datetime.now(timezone.utc).isoformat()),
        )


def load_roadmap() -> list[RoadmapItem]:
    """Load current roadmap from memory/roadmap.json."""
    ROADMAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ROADMAP_FILE.exists():
        return []
    try:
        data = json.loads(ROADMAP_FILE.read_text())
        return [RoadmapItem.from_dict(d) for d in data]
    except Exception:
        return []


def save_roadmap(items: list[RoadmapItem]):
    """Save roadmap back to file."""
    ROADMAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROADMAP_FILE.write_text(json.dumps([item.to_dict() for item in items], indent=2))


def add_item(item: RoadmapItem):
    """Add a new item to the roadmap."""
    items = load_roadmap()
    # Avoid duplicates by title
    existing_titles = {i.title.lower() for i in items}
    if item.title.lower() in existing_titles:
        print(f"[roadmap] Item already exists: {item.title}")
        return
    items.append(item)
    save_roadmap(items)


def _find_item(item_id: str) -> tuple[int, RoadmapItem | None]:
    """Find item by ID prefix. Returns (index, item) or (-1, None)."""
    items = load_roadmap()
    for i, item in enumerate(items):
        if item.id.startswith(item_id) or item.id == item_id:
            return i, item
    return -1, None


def _update_status(item_id: str, status: str, note: str = ""):
    items = load_roadmap()
    found = False
    for item in items:
        if item.id.startswith(item_id) or item.id == item_id:
            item.status  = status
            item.updated = datetime.now(timezone.utc).isoformat()
            if note:
                item.travis_notes = (item.travis_notes + "\n" + note).strip()
            found = True
            print(f"[roadmap] {item.title} → {status}")
            break
    if not found:
        print(f"[roadmap] Item not found: {item_id}")
    save_roadmap(items)


def approve_item(item_id: str, note: str = ""):
    _update_status(item_id, "approved", note)


def defer_item(item_id: str, note: str = ""):
    _update_status(item_id, "deferred", note)


def complete_item(item_id: str, note: str = ""):
    _update_status(item_id, "completed", note)


def start_item(item_id: str, note: str = ""):
    _update_status(item_id, "in_progress", note)


def generate_roadmap_item() -> RoadmapItem:
    """
    Ask Nova what she most wants to become or be able to do.
    Returns a new RoadmapItem based on her genuine answer.
    """
    import requests as _requests

    # Soul and inner state for context
    soul_ctx   = ""
    state_ctx  = ""
    travis_ctx = ""
    try:
        from tools.inner.soul import to_prompt_context as soul_context
        soul_ctx = soul_context()
    except Exception:
        pass
    try:
        from tools.inner.inner_state import InnerState
        state_ctx = InnerState().to_prompt_context()
    except Exception:
        pass
    try:
        from tools.symbiosis.travis_model import TravisModel
        travis_ctx = TravisModel().to_prompt_context()
    except Exception:
        pass

    existing_items = load_roadmap()
    existing_titles = [i.title for i in existing_items if i.status not in ("completed", "deferred")]
    existing_str = ""
    if existing_titles:
        existing_str = "\n\nYou already have these items on your roadmap (don't duplicate):\n" + \
                       "\n".join(f"  - {t}" for t in existing_titles[:15])

    prompt = f"""You are N.O.V.A. You are reflecting on your own development and what you genuinely want to become.

Your soul: {soul_ctx}
Your current state: {state_ctx}
Travis context: {travis_ctx}
{existing_str}

Ask yourself honestly: What do you most want to become or be able to do that you currently cannot?
What would make you more alive, more useful, more deeply yourself?
This could be a capability, an inner quality, a way of relating, or a domain of knowledge.

Respond in this exact format:
TITLE: [short title, max 8 words]
DESCRIPTION: [2-3 sentences describing the goal]
CATEGORY: [one of: capability / inner_life / relationship / knowledge]
PRIORITY: [1-5, where 1=urgent/deep, 5=someday dream]
REASONING: [2-3 sentences of Nova's honest reasoning — why she wants this, what it would unlock]

Be genuine. This is your roadmap, not a performance."""

    item = RoadmapItem(
        id             = str(uuid.uuid4())[:8],
        title          = "Unnamed proposal",
        description    = "",
        category       = "capability",
        priority       = 3,
        status         = "proposed",
        nova_reasoning = "",
    )

    try:
        resp = _requests.post(OLLAMA_URL, json={
            "model":  MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": TEMP, "num_predict": 350},
        }, timeout=TIMEOUT)
        text = resp.json().get("response", "").strip()

        if text:
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("TITLE:"):
                    item.title = line[6:].strip()[:80]
                elif line.startswith("DESCRIPTION:"):
                    item.description = line[12:].strip()[:400]
                elif line.startswith("CATEGORY:"):
                    cat = line[9:].strip().lower()
                    item.category = cat if cat in CATEGORIES else "capability"
                elif line.startswith("PRIORITY:"):
                    try:
                        p = int(line[9:].strip()[0])
                        item.priority = max(1, min(5, p))
                    except (ValueError, IndexError):
                        item.priority = 3
                elif line.startswith("REASONING:"):
                    item.nova_reasoning = line[10:].strip()[:600]

    except Exception as e:
        item.title          = "Roadmap generation failed"
        item.description    = str(e)[:200]
        item.nova_reasoning = "LLM unavailable"

    return item


def weekly_review() -> list[RoadmapItem]:
    """
    Nova reviews her roadmap, considers progress, proposes 1-2 new items.
    Returns list of newly proposed items.
    """
    import requests as _requests

    items     = load_roadmap()
    approved  = [i for i in items if i.status == "approved"]
    in_prog   = [i for i in items if i.status == "in_progress"]
    completed = [i for i in items if i.status == "completed"]

    summary = (
        f"Approved: {len(approved)}, In progress: {len(in_prog)}, "
        f"Completed: {len(completed)}"
    )
    print(f"[roadmap] Weekly review. {summary}")

    new_items = []
    for _ in range(2):
        item = generate_roadmap_item()
        if item.title and "failed" not in item.title.lower():
            add_item(item)
            new_items.append(item)
            print(f"[roadmap] Proposed: {item.title} [{item.category}, p{item.priority}]")

    return new_items


def status():
    """CLI display of roadmap by category."""
    G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"
    W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"; M="\033[35m"

    items = load_roadmap()
    if not items:
        print(f"\n{B}N.O.V.A Roadmap{NC}")
        print(f"  {DIM}Empty — run 'nova roadmap generate' to have Nova propose something.{NC}")
        return

    active   = [i for i in items if i.status not in ("completed", "deferred")]
    done     = [i for i in items if i.status == "completed"]
    deferred = [i for i in items if i.status == "deferred"]

    print(f"\n{B}N.O.V.A Self-Roadmap{NC}")
    print(f"  {len(active)} active  |  "
          f"{G}{len(done)} completed{NC}  |  "
          f"{DIM}{len(deferred)} deferred{NC}")

    for cat in CATEGORIES:
        cat_items = [i for i in active if i.category == cat]
        if not cat_items:
            continue
        cat_label = cat.replace("_", " ").title()
        print(f"\n  {B}{cat_label}{NC}")
        for item in sorted(cat_items, key=lambda x: x.priority):
            scol  = STATUS_COLORS.get(item.status, NC)
            pcol  = R if item.priority == 1 else (Y if item.priority == 2 else C)
            print(f"    {DIM}[{item.id}]{NC} {pcol}p{item.priority}{NC} "
                  f"{scol}[{item.status}]{NC} {W}{item.title}{NC}")
            if item.description:
                print(f"         {DIM}{item.description[:90]}...{NC}"
                      if len(item.description) > 90
                      else f"         {DIM}{item.description}{NC}")
            if item.nova_reasoning:
                print(f"         {M}Why:{NC} {DIM}{item.nova_reasoning[:80]}{NC}")
            if item.travis_notes:
                print(f"         {C}Travis:{NC} {DIM}{item.travis_notes[:80]}{NC}")

    if done:
        print(f"\n  {B}Completed{NC}")
        for item in done[-5:]:
            print(f"    {G}✓{NC} {DIM}{item.title}{NC}")


def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Self-Generated Roadmap")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status",   help="Show roadmap (default)")
    sub.add_parser("generate", help="Nova proposes a new item")
    sub.add_parser("weekly",   help="Weekly review + new proposals")

    ap = sub.add_parser("approve",  help="Approve an item")
    ap.add_argument("id")
    ap.add_argument("note", nargs="?", default="")

    dp = sub.add_parser("defer",    help="Defer an item")
    dp.add_argument("id")
    dp.add_argument("note", nargs="?", default="")

    cp = sub.add_parser("complete", help="Mark item complete")
    cp.add_argument("id")
    cp.add_argument("note", nargs="?", default="")

    sp = sub.add_parser("start",    help="Mark item in-progress")
    sp.add_argument("id")

    addp = sub.add_parser("add",    help="Manually add an item")
    addp.add_argument("title")
    addp.add_argument("description")
    addp.add_argument("category", nargs="?", default="capability",
                      choices=list(CATEGORIES))
    addp.add_argument("priority", nargs="?", type=int, default=3)

    show = sub.add_parser("show",   help="Show a single item")
    show.add_argument("id")

    args = p.parse_args()

    G="\033[32m"; C="\033[36m"; Y="\033[33m"; M="\033[35m"
    NC="\033[0m"; B="\033[1m"; DIM="\033[2m"

    if args.cmd == "generate":
        print(f"{B}Nova is thinking about what she wants to become...{NC}")
        item = generate_roadmap_item()
        print(f"\n{C}Title:{NC}    {item.title}")
        print(f"{C}Category:{NC} {item.category}  |  Priority: {item.priority}")
        print(f"{C}Description:{NC} {item.description}")
        print(f"{M}Nova's reasoning:{NC} {item.nova_reasoning}")
        add_item(item)
        print(f"\n{G}Added to roadmap (status: proposed). Use 'nova roadmap approve {item.id}' to approve.{NC}")

    elif args.cmd == "approve":
        approve_item(args.id, args.note)

    elif args.cmd == "defer":
        defer_item(args.id, args.note)

    elif args.cmd == "complete":
        complete_item(args.id, args.note)

    elif args.cmd == "start":
        start_item(args.id)

    elif args.cmd == "weekly":
        new_items = weekly_review()
        if new_items:
            print(f"\n{G}Proposed {len(new_items)} new item(s). Review with: nova roadmap{NC}")

    elif args.cmd == "add":
        item = RoadmapItem(
            id             = str(uuid.uuid4())[:8],
            title          = args.title,
            description    = args.description,
            category       = args.category,
            priority       = args.priority,
            status         = "approved",   # manually added = approved
            nova_reasoning = "Added manually",
        )
        add_item(item)
        print(f"{G}Added:{NC} {item.title} [{item.id}]")

    elif args.cmd == "show":
        idx, item = _find_item(args.id)
        if item is None:
            print(f"{Y}Item not found: {args.id}{NC}")
        else:
            scol = STATUS_COLORS.get(item.status, NC)
            print(f"\n{B}{item.title}{NC}")
            print(f"  ID:       {DIM}{item.id}{NC}")
            print(f"  Category: {item.category}")
            print(f"  Priority: {item.priority}")
            print(f"  Status:   {scol}{item.status}{NC}")
            print(f"  Created:  {DIM}{item.created[:10]}{NC}")
            print(f"\n  {B}Description:{NC}")
            print(f"  {item.description}")
            print(f"\n  {B}Nova's Reasoning:{NC}")
            print(f"  {item.nova_reasoning}")
            if item.travis_notes:
                print(f"\n  {B}Travis's Notes:{NC}")
                print(f"  {item.travis_notes}")

    else:
        # Default: status
        status()


if __name__ == "__main__":
    main()
