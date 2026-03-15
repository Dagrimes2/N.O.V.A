#!/usr/bin/env python3
"""
N.O.V.A Agency Layer

Nova's external agency — she proposes actions in the real world, Travis
approves them, and then they execute. Nothing runs without Travis's approval.

Storage:
  memory/proposals/agency_proposals.jsonl  — append-only proposal log
  memory/proposals/agency_approved.json    — approved pending execution
  memory/agency_responses/                 — saved web_request responses

Usage:
    from tools.operator.agency import propose_action, approve, execute_approved
    pid = propose_action("github_issue", "File bug report for SSRF in X", ...)
    approve(pid)
    execute_approved()

CLI:
    nova agency list
    nova agency approve ID
    nova agency reject ID
    nova agency execute
    nova agency propose TYPE DESC
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE          = Path.home() / "Nova"
PROPOSALS_DIR = BASE / "memory/proposals"
PROPOSALS_LOG = PROPOSALS_DIR / "agency_proposals.jsonl"
APPROVED_FILE = PROPOSALS_DIR / "agency_approved.json"
RESPONSES_DIR = BASE / "memory/agency_responses"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)


# ── GitHub token helper ───────────────────────────────────────────────────────

def _github_pat() -> str:
    """Read GitHub PAT from config/github.yaml if present."""
    gh_config = BASE / "config/github.yaml"
    if gh_config.exists():
        try:
            for line in gh_config.read_text().splitlines():
                line = line.strip()
                if line.startswith("token:"):
                    return line.split(":", 1)[1].strip().strip("\"'")
        except Exception:
            pass
    return ""


# ── Discord notification helper ───────────────────────────────────────────────

def _notify_travis(message: str):
    """Best-effort Discord notification to Travis."""
    try:
        from tools.notify.discord import send
        send(message)
    except Exception:
        pass


# ── Storage helpers ───────────────────────────────────────────────────────────

def _load_approved() -> list:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    if APPROVED_FILE.exists():
        try:
            return json.loads(APPROVED_FILE.read_text())
        except Exception:
            pass
    return []


def _save_approved(data: list):
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    APPROVED_FILE.write_text(json.dumps(data, indent=2))


def _append_proposal(proposal: dict):
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROPOSALS_LOG, "a") as f:
        f.write(json.dumps(proposal) + "\n")


def _read_all_proposals() -> list:
    if not PROPOSALS_LOG.exists():
        return []
    results = []
    for line in PROPOSALS_LOG.read_text().strip().splitlines():
        if not line.strip():
            continue
        try:
            results.append(json.loads(line))
        except Exception:
            pass
    return results


# ── Core functions ────────────────────────────────────────────────────────────

def propose_action(
    action_type: str,
    description: str,
    target: str,
    payload: dict = None,
    reason: str = "",
) -> str:
    """
    Propose an action for Travis to review. Creates the proposal, appends it
    to the JSONL log, and sends a Telegram notification. Does NOT execute.
    Returns proposal_id.
    """
    now     = datetime.now(timezone.utc)
    ts_tag  = now.strftime("%Y%m%d_%H%M%S")
    prop_id = f"ag_{ts_tag}"

    # Safety: check moral_reasoning
    flagged = False
    try:
        from tools.inner.moral_reasoning import check  # type: ignore
        concern = check(description)
        if concern:
            description = f"[FLAGGED] {description}"
            reason = f"[MORAL FLAG: {concern}] {reason}"
            flagged = True
    except Exception:
        pass

    proposal = {
        "id":          prop_id,
        "action_type": action_type,
        "description": description,
        "target":      target,
        "payload":     payload or {},
        "reason":      reason,
        "status":      "pending",
        "created":     now.isoformat(),
        "travis_note": "",
    }

    _append_proposal(proposal)

    # Notify Travis
    _notify_travis(
        f"Nova wants to: {description}. To approve: nova agency approve {prop_id}"
    )

    return prop_id


def approve(proposal_id: str, travis_note: str = "") -> bool:
    """
    Find a pending proposal by ID and move it to the approved list.
    Returns True if found and approved.
    """
    proposals = _read_all_proposals()
    target    = None
    for p in proposals:
        if p.get("id") == proposal_id and p.get("status") == "pending":
            target = dict(p)
            break

    if not target:
        return False

    target["status"]      = "approved"
    target["travis_note"] = travis_note
    target["approved_at"] = datetime.now(timezone.utc).isoformat()

    approved = _load_approved()
    approved.append(target)
    _save_approved(approved)

    # Append updated record to JSONL (tombstone)
    updated = dict(target)
    _append_proposal({**updated, "_tombstone": "approved"})
    return True


def reject(proposal_id: str) -> bool:
    """
    Reject a pending proposal. Appends a rejection record to the JSONL.
    Returns True if found.
    """
    proposals = _read_all_proposals()
    found     = any(
        p.get("id") == proposal_id and p.get("status") == "pending"
        for p in proposals
    )
    if not found:
        return False

    rejection = {
        "id":          proposal_id,
        "status":      "rejected",
        "rejected_at": datetime.now(timezone.utc).isoformat(),
    }
    _append_proposal(rejection)
    return True


def execute_approved() -> list:
    """
    Execute all approved proposals. Supports github_issue and web_request types.
    Marks each as executed. Returns list of executed IDs.
    """
    approved  = _load_approved()
    executed  = []
    remaining = []

    for proposal in approved:
        if proposal.get("status") != "approved":
            remaining.append(proposal)
            continue

        prop_id     = proposal["id"]
        action_type = proposal.get("action_type", "")
        target      = proposal.get("target", "")
        payload     = proposal.get("payload", {})

        success = False
        error   = ""

        if action_type == "github_issue":
            pat = _github_pat()
            if not pat:
                error   = "No GitHub PAT found in config/github.yaml — skipping."
                success = False
            else:
                try:
                    body    = json.dumps(payload).encode()
                    req     = urllib.request.Request(
                        target,
                        data=body,
                        headers={
                            "Content-Type":  "application/json",
                            "Authorization": f"token {pat}",
                            "User-Agent":    "NOVA-Agency/1.0",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        _ = resp.read()
                    success = True
                except Exception as exc:
                    error = str(exc)

        elif action_type == "web_request":
            try:
                req = urllib.request.Request(
                    target,
                    headers={"User-Agent": "NOVA-Agency/1.0"},
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content = resp.read()
                RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
                ts_tag    = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                save_path = RESPONSES_DIR / f"{prop_id}_{ts_tag}.txt"
                save_path.write_bytes(content)
                success = True
            except Exception as exc:
                error = str(exc)

        # Record episode regardless of success
        try:
            from tools.memory.episodic import record_episode  # type: ignore
            record_episode(
                "agency_execution",
                f"Executed proposal {prop_id} ({action_type}): {proposal.get('description', '')[:80]}",
                "action",
                0.5,
            )
        except Exception:
            pass

        proposal["status"]      = "executed" if success else "execution_failed"
        proposal["executed_at"] = datetime.now(timezone.utc).isoformat()
        if error:
            proposal["execution_error"] = error
        _append_proposal({**proposal, "_tombstone": "executed"})

        if success:
            executed.append(prop_id)
        remaining.append(proposal)

    # Save back (keep failed ones for visibility, remove only successfully executed)
    still_pending = [p for p in remaining if p.get("status") == "approved"]
    _save_approved(still_pending)
    return executed


def list_pending() -> list:
    """Return all proposals with status == 'pending'."""
    proposals = _read_all_proposals()
    # De-duplicate: only the latest record per ID
    by_id = {}
    for p in proposals:
        pid = p.get("id")
        if pid:
            by_id[pid] = p
    return [p for p in by_id.values() if p.get("status") == "pending"]


def to_prompt_context() -> str:
    """Compact agency context for LLM injection."""
    pending = list_pending()
    if not pending:
        return "Agency: no pending actions"
    return f"Agency: {len(pending)} pending proposal{'s' if len(pending) != 1 else ''} awaiting Travis approval"


def status():
    """Print pending, approved, and executed counts."""
    G = "\033[32m"; C = "\033[36m"; Y = "\033[33m"; R = "\033[31m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    all_proposals = _read_all_proposals()
    by_id         = {}
    for p in all_proposals:
        pid = p.get("id")
        if pid:
            by_id[pid] = p

    pending  = [p for p in by_id.values() if p.get("status") == "pending"]
    approved = [p for p in by_id.values() if p.get("status") == "approved"]
    executed = [p for p in by_id.values() if p.get("status") == "executed"]
    failed   = [p for p in by_id.values() if p.get("status") == "execution_failed"]
    rejected = [p for p in by_id.values() if p.get("status") == "rejected"]

    print(f"\n{B}N.O.V.A Agency{NC}")
    print(f"  {Y}Pending  :{NC} {len(pending)}")
    print(f"  {G}Approved :{NC} {len(approved)}")
    print(f"  {G}Executed :{NC} {len(executed)}")
    print(f"  {R}Failed   :{NC} {len(failed)}")
    print(f"  {DIM}Rejected :{NC} {len(rejected)}")

    if pending:
        print(f"\n  {B}Pending proposals:{NC}")
        for p in pending[-5:]:
            print(f"    {Y}{p['id']}{NC}  [{p.get('action_type', '?')}]")
            print(f"      {p.get('description', '')[:80]}")
            print(f"      {DIM}Reason: {p.get('reason', '')[:60]}{NC}")


def main():
    import argparse

    p   = argparse.ArgumentParser(description="N.O.V.A Agency Layer")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("list",    help="Show pending proposals (default)")
    sub.add_parser("status",  help="Show all proposal counts")
    sub.add_parser("execute", help="Execute all approved proposals")

    app = sub.add_parser("approve", help="Approve a proposal")
    app.add_argument("proposal_id")
    app.add_argument("--note", default="", dest="travis_note")

    rej = sub.add_parser("reject", help="Reject a proposal")
    rej.add_argument("proposal_id")

    prp = sub.add_parser("propose", help="Create a new proposal")
    prp.add_argument("action_type")
    prp.add_argument("description", nargs="+")

    args = p.parse_args()

    G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    if args.cmd in (None, "list"):
        pending = list_pending()
        if not pending:
            print(f"{DIM}No pending proposals.{NC}")
        else:
            print(f"\n{B}Pending proposals ({len(pending)}):{NC}")
            for p in pending:
                print(f"\n  {Y}{p['id']}{NC}  [{p.get('action_type', '?')}]")
                print(f"    {p.get('description', '')}")
                print(f"    {DIM}{p.get('reason', '')}{NC}")

    elif args.cmd == "status":
        status()

    elif args.cmd == "approve":
        ok = approve(args.proposal_id, args.travis_note)
        if ok:
            print(f"{G}Approved:{NC} {args.proposal_id}")
        else:
            print(f"{R}Not found or not pending:{NC} {args.proposal_id}")

    elif args.cmd == "reject":
        ok = reject(args.proposal_id)
        if ok:
            print(f"Rejected: {args.proposal_id}")
        else:
            print(f"{R}Not found:{NC} {args.proposal_id}")

    elif args.cmd == "execute":
        print("Executing approved proposals...")
        executed = execute_approved()
        if executed:
            print(f"{G}Executed:{NC} {', '.join(executed)}")
        else:
            print(f"{DIM}Nothing to execute (or all failed).{NC}")

    elif args.cmd == "propose":
        desc   = " ".join(args.description)
        prop_id = propose_action(args.action_type, desc, target="", reason="CLI proposal")
        print(f"{G}Proposal created:{NC} {prop_id}")
        print(f"  Awaiting Travis approval.")


if __name__ == "__main__":
    main()
