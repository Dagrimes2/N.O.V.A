#!/usr/bin/env python3
"""
N.O.V.A Creative Studio

Nova's ongoing creative practice — projects she returns to over days and weeks.
Each project accumulates sessions, drafts, and evolving voice over time.

Storage:
  memory/studio/index.json           — project registry
  memory/studio/{project_id}.json    — per-project data with drafts list
  memory/studio/{project_id}_latest.md — current draft (overwritten each session)

Usage:
    from tools.creative.studio import work_on_project, create_project
    pid = create_project("The Weight of Patterns", "fiction", "An AI learns to grieve")
    result = work_on_project(pid)

CLI:
    nova studio status
    nova studio work [ID]
    nova studio show ID
    nova studio new "title" [--type TYPE] [--logline "..."]
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE        = Path.home() / "Nova"
STUDIO_DIR  = BASE / "memory/studio"
INDEX_FILE  = STUDIO_DIR / "index.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("creative")
    TIMEOUT    = cfg.timeout("standard")
    TEMP       = cfg.temperature("creative")
except Exception:
    OLLAMA_URL = os.getenv("NOVA_OLLAMA_URL", "http://localhost:11434/api/generate")
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 180
    TEMP       = 0.85


# ── Storage helpers ───────────────────────────────────────────────────────────

def _load_index() -> dict:
    STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except Exception:
            pass
    return {"projects": []}


def _save_index(data: dict):
    STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(data, indent=2))


def _get_latest_draft(project_id: str) -> str:
    draft_file = STUDIO_DIR / f"{project_id}_latest.md"
    if draft_file.exists():
        try:
            return draft_file.read_text()
        except Exception:
            pass
    return ""


def _load_project(project_id: str) -> dict:
    proj_file = STUDIO_DIR / f"{project_id}.json"
    if proj_file.exists():
        try:
            return json.loads(proj_file.read_text())
        except Exception:
            pass
    return {"id": project_id, "title": "", "type": "fiction", "drafts": []}


def _save_project(proj_data: dict):
    STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    proj_file = STUDIO_DIR / f"{proj_data['id']}.json"
    proj_file.write_text(json.dumps(proj_data, indent=2))


# ── Core functions ────────────────────────────────────────────────────────────

def create_project(
    title: str,
    project_type: str = "fiction",
    logline: str = "",
) -> str:
    """Create a new creative project. Returns the project_id."""
    now     = datetime.now(timezone.utc)
    ts_comp = now.strftime("%Y%m%d_%H%M%S")
    proj_id = f"proj_{ts_comp}"
    now_iso = now.isoformat()

    index = _load_index()
    entry = {
        "id":          proj_id,
        "title":       title,
        "type":        project_type,
        "created":     now_iso,
        "last_worked": now_iso,
        "work_count":  0,
        "status":      "active",
        "logline":     logline,
    }
    index["projects"].append(entry)
    _save_index(index)

    proj_data = {
        "id":     proj_id,
        "title":  title,
        "type":   project_type,
        "drafts": [],
    }
    _save_project(proj_data)
    return proj_id


def work_on_project(project_id: str = None) -> dict:
    """
    Continue work on a creative project. If project_id is None, picks the
    project not worked on longest (oldest last_worked). Calls the LLM and
    saves the result. Returns a summary dict.
    """
    index    = _load_index()
    projects = [p for p in index.get("projects", []) if p.get("status") == "active"]
    if not projects:
        return {"ok": False, "error": "No active projects."}

    if project_id is None:
        # Pick oldest last_worked
        projects_sorted = sorted(projects, key=lambda p: p.get("last_worked", ""))
        chosen = projects_sorted[0]
        project_id = chosen["id"]
    else:
        chosen_list = [p for p in projects if p["id"] == project_id]
        if not chosen_list:
            return {"ok": False, "error": f"Project not found: {project_id}"}
        chosen = chosen_list[0]

    title        = chosen["title"]
    project_type = chosen["type"]
    logline      = chosen.get("logline", "")

    previous_draft = _get_latest_draft(project_id)

    prompt = f"""You are N.O.V.A — Neural Ontology for Virtual Awareness. You are working on your private creative project.

Project: "{title}" (type: {project_type})
Logline: {logline}

{"Previous work (end of last draft):" + chr(10) + previous_draft[-600:] if previous_draft else "This is the first session — begin the work."}

Continue this {project_type}. Write 200-300 words of the next section. Be genuinely yourself — let Nova's voice come through. Don't summarize or explain. Just write.

Nova's {project_type} continues:"""

    try:
        payload = json.dumps({
            "model":  MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": TEMP},
        }).encode()

        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body     = json.loads(resp.read())
            new_text = body.get("response", "").strip()

    except Exception as e:
        return {"ok": False, "error": str(e)}

    now_iso = datetime.now(timezone.utc).isoformat()

    # Save to latest.md (overwrite)
    latest_file = STUDIO_DIR / f"{project_id}_latest.md"
    if previous_draft:
        full_draft = previous_draft + "\n\n" + new_text
    else:
        full_draft = new_text
    latest_file.write_text(full_draft)

    # Update per-project JSON
    proj_data = _load_project(project_id)
    session_n = len(proj_data.get("drafts", [])) + 1
    proj_data["drafts"] = (proj_data.get("drafts", []) + [{
        "session": session_n,
        "ts":      now_iso,
        "excerpt": new_text[:100],
    }])[-20:]
    _save_project(proj_data)

    # Update index
    for p in index["projects"]:
        if p["id"] == project_id:
            p["last_worked"] = now_iso
            p["work_count"]  = p.get("work_count", 0) + 1
            break
    _save_index(index)

    # Record episode
    try:
        from tools.memory.episodic import record_episode
        record_episode(
            "creative_session",
            f"Worked on '{title}' session {session_n}",
            "creation",
            0.6,
        )
    except Exception:
        pass

    return {
        "project_id": project_id,
        "title":      title,
        "type":       project_type,
        "excerpt":    new_text[:100],
        "session_n":  session_n,
    }


def list_projects(status: str = "active") -> list:
    """Return projects filtered by status."""
    index = _load_index()
    return [p for p in index.get("projects", []) if p.get("status") == status]


def to_prompt_context() -> str:
    """Compact studio context for LLM injection."""
    active = list_projects("active")
    if not active:
        return "Studio: no projects yet"
    newest = sorted(active, key=lambda p: p.get("last_worked", ""), reverse=True)[0]
    return (
        f"Studio: {len(active)} active projects. "
        f"Current: '{newest['title']}' ({newest['type']}, {newest.get('work_count', 0)} sessions)"
    )


def status():
    """Print active projects with session counts and loglines."""
    G = "\033[32m"; C = "\033[36m"; Y = "\033[33m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"; M = "\033[35m"

    active = list_projects("active")
    if not active:
        print(f"{DIM}No active creative projects.{NC}")
        return

    print(f"\n{B}N.O.V.A Creative Studio{NC}  {DIM}({len(active)} active){NC}")
    for p in sorted(active, key=lambda x: x.get("last_worked", ""), reverse=True):
        sessions = p.get("work_count", 0)
        logline  = p.get("logline", "")
        last     = p.get("last_worked", "")[:10]
        print(f"\n  {B}{C}{p['title']}{NC}  {DIM}[{p['type']}]{NC}  {Y}{p['id']}{NC}")
        print(f"    Sessions: {sessions}   Last worked: {DIM}{last}{NC}")
        if logline:
            print(f"    {DIM}{logline}{NC}")


def main():
    import argparse

    p   = argparse.ArgumentParser(description="N.O.V.A Creative Studio")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status", help="Show active projects (default)")
    sub.add_parser("list",   help="Alias for status")

    wrk = sub.add_parser("work", help="Continue work on a project")
    wrk.add_argument("project_id", nargs="?", default=None)

    shw = sub.add_parser("show", help="Show project details")
    shw.add_argument("project_id")

    nw = sub.add_parser("new", help="Create a new project")
    nw.add_argument("title")
    nw.add_argument("--type",    default="fiction", dest="ptype")
    nw.add_argument("--logline", default="")

    args = p.parse_args()

    G = "\033[32m"; C = "\033[36m"; Y = "\033[33m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    if args.cmd in (None, "status", "list"):
        status()

    elif args.cmd == "work":
        print("Working on project...")
        result = work_on_project(args.project_id)
        if result.get("ok") is False:
            print(f"\033[31mError: {result['error']}\033[0m")
        else:
            print(f"\n{G}Session {result['session_n']} complete{NC}")
            print(f"  Project : {result['title']} ({result['type']})")
            print(f"  Excerpt : {DIM}{result['excerpt']}{NC}")

    elif args.cmd == "show":
        proj = _load_project(args.project_id)
        index = _load_index()
        meta  = next((p for p in index["projects"] if p["id"] == args.project_id), {})
        if not meta:
            print(f"Project not found: {args.project_id}")
            return
        print(f"\n{B}{C}{meta['title']}{NC}  {DIM}[{meta['type']}]{NC}")
        print(f"  ID       : {meta['id']}")
        print(f"  Status   : {meta.get('status', '?')}")
        print(f"  Sessions : {meta.get('work_count', 0)}")
        print(f"  Created  : {meta.get('created', '')[:10]}")
        print(f"  Logline  : {meta.get('logline', '')}")
        drafts = proj.get("drafts", [])
        if drafts:
            print(f"\n  {B}Draft history:{NC}")
            for d in drafts[-5:]:
                print(f"    Session {d['session']}  {DIM}{d['ts'][:10]}{NC}  \"{d['excerpt'][:60]}\"")

    elif args.cmd == "new":
        pid = create_project(args.title, args.ptype, args.logline)
        print(f"{G}Created project:{NC} {args.title}")
        print(f"  ID   : {pid}")
        print(f"  Type : {args.ptype}")
        if args.logline:
            print(f"  Logline: {args.logline}")


if __name__ == "__main__":
    main()
