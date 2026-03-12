#!/usr/bin/env python3
"""
N.O.V.A Self-Evolution Engine
Reads own code, proposes improvements, applies approved ones.
Never modifies governance files. Always syntax-checks before writing.
"""
import json, requests, os, random, sys, subprocess, shutil
from pathlib import Path
from datetime import datetime

BASE       = Path.home() / "Nova"
PROPOSALS  = BASE / "memory/proposals"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

PROPOSALS.mkdir(parents=True, exist_ok=True)

# Files she can evolve — governance files are NEVER on this list
EVOLVABLE = [
    "tools/reasoning/hypothesize.py",
    "tools/reasoning/reflect.py",
    "tools/scoring/score.py",
    "bin/nova_dream.py",
    "bin/nova_life.py",
    "bin/nova_research.py",
    "bin/nova_memory_summarize.py",
]

# Files she can NEVER touch
PROTECTED = [
    "core/governance.yaml",
    "core/covenant.yaml",
    "core/autonomy.yaml",
    "core/whitelist.json",
    "core/approval.yaml",
    "bin/nova_evolve.py",
    "tools/governance/audit.py",
    "tools/governance/autonomy_guard.py",
]

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def read_script(path: str) -> str:
    full = BASE / path
    return full.read_text() if full.exists() else ""

def is_protected(file_path: str) -> bool:
    return any(p in file_path for p in PROTECTED)

def syntax_check(code: str) -> bool:
    """Return True if code compiles cleanly."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        tmp = f.name
    result = subprocess.run(
        ["python3", "-m", "py_compile", tmp],
        capture_output=True
    )
    os.unlink(tmp)
    return result.returncode == 0

def apply_proposal(proposal_path: Path) -> str:
    """Ask LLM to apply the proposed change. Returns status string."""
    try:
        data = json.loads(proposal_path.read_text())
    except Exception as e:
        return f"apply_failed: unreadable proposal — {e}"

    file_path = data.get("file", "")
    if not file_path:
        return "apply_failed: no file specified"

    if is_protected(file_path):
        return "apply_failed: protected file — governance boundary"

    if file_path not in EVOLVABLE:
        return f"apply_failed: {file_path} not in evolvable list"

    original_code = read_script(file_path)
    if not original_code:
        return f"apply_failed: could not read {file_path}"

    issue    = data.get("issue", "")
    change   = data.get("proposed_change", "")

    prompt = f"""You are N.O.V.A applying an approved improvement to your own code.

File: {file_path}
Issue to fix: {issue}
Approved change: {change}

Current code:
{original_code[:1500]}

Return the COMPLETE improved Python file with the change applied.
Return ONLY the raw Python code — no markdown, no explanation, no backticks."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 2000}
        }, timeout=300)
        new_code = resp.json()["response"].strip()
    except Exception as e:
        return f"apply_failed: LLM error — {e}"

    # Strip accidental markdown fences
    if new_code.startswith("```"):
        lines = new_code.split("\n")
        new_code = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    if len(new_code) < 50:
        return "apply_failed: LLM returned too little code"

    if not syntax_check(new_code):
        return "apply_failed: syntax check failed — original preserved"

    # Backup original
    backup_dir = BASE / "memory/backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{Path(file_path).stem}_{ts}.py.bak"
    shutil.copy2(BASE / file_path, backup_path)

    # Write improved code
    (BASE / file_path).write_text(new_code)
    log(f"[APPLY] ✓ Applied to {file_path} (backup: {backup_path.name})")
    return "applied"

def run_apply():
    """Apply all approved proposals."""
    proposals = sorted(PROPOSALS.glob("proposal_*.json"))
    approved  = []
    for p in proposals:
        try:
            data = json.loads(p.read_text())
            if data.get("status") == "approved":
                approved.append(p)
        except:
            pass

    if not approved:
        log("[APPLY] No approved proposals to apply.")
        return

    log(f"[APPLY] Found {len(approved)} approved proposals")
    applied = failed = skipped = 0

    for p in approved:
        try:
            data = json.loads(p.read_text())
            log(f"[APPLY] Processing {p.name}: {data.get('issue','')[:60]}")

            status = apply_proposal(p)
            data["status"]     = status
            data["applied_at"] = datetime.now().strftime("%Y-%m-%d-%H%M")
            p.write_text(json.dumps(data, indent=2))

            if status == "applied":
                applied += 1
                log(f"[APPLY] ✓ {p.name} — applied successfully")
            elif "failed" in status:
                failed += 1
                log(f"[APPLY] ✗ {p.name} — {status}")
            else:
                skipped += 1
        except Exception as e:
            log(f"[APPLY] ✗ {p.name} — exception: {e}")
            failed += 1

    log(f"[APPLY] Done — applied={applied} failed={failed} skipped={skipped}")

def propose_improvement(script_path: str) -> dict:
    code = read_script(script_path)
    if not code:
        return {"error": "file not found"}

    prompt = f"""You are N.O.V.A reviewing your own code for one specific improvement.

File: {script_path}
Code:
{code[:800]}

Identify ONE concrete, low-risk improvement. Return ONLY this JSON:
{{
  "file": "{script_path}",
  "issue": "one specific weakness or missing feature",
  "proposed_change": "exactly what code to add or change (be specific)",
  "expected_improvement": "what gets better",
  "risk": "low",
  "confidence": 0.8
}}"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 400}
        }, timeout=300)
        raw = resp.json()["response"].strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        if not raw:
            return {"error": "empty response"}
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e)}

def list_proposals():
    proposals = sorted(PROPOSALS.glob("proposal_*.json"))
    if not proposals:
        print("[N.O.V.A] No proposals found.")
        return
    print(f"\n[N.O.V.A] {len(proposals)} proposals:\n")
    for p in proposals:
        try:
            data = json.loads(p.read_text())
            status = data.get("status", "pending")
            icon = {"pending":"⏳","approved":"✅","applied":"🟢","apply_failed":"🔴"}.get(status, "❓")
            print(f"  {icon} {p.name}  [{status}]")
            print(f"    File  : {data.get('file','?')}")
            print(f"    Issue : {data.get('issue','?')[:80]}")
            print()
        except:
            print(f"  {p.name} [unreadable]")

def approve_proposal(proposal_name: str):
    path = PROPOSALS / proposal_name
    if not path.exists():
        print(f"[!] Not found: {proposal_name}")
        return
    data = json.loads(path.read_text())
    print(f"\n[N.O.V.A] Reviewing: {proposal_name}")
    print(f"  File   : {data.get('file')}")
    print(f"  Issue  : {data.get('issue')}")
    print(f"  Change : {data.get('proposed_change')}")
    print(f"  Risk   : {data.get('risk')}")
    confirm = input("\nApprove? [yes/no]: ").strip().lower()
    if confirm != "yes":
        print("[N.O.V.A] Cancelled.")
        return
    data["status"]      = "approved"
    data["approved_at"] = datetime.now().isoformat()
    data["approved_by"] = "Travis"
    path.write_text(json.dumps(data, indent=2))
    print(f"[N.O.V.A] ✓ Approved — will be applied on next evolve cycle.")

def run_evolve():
    script   = random.choice(EVOLVABLE)
    date_str = datetime.now().strftime("%Y-%m-%d-%H%M")
    log(f"[EVOLVE] Analyzing {script}...")

    proposal = propose_improvement(script)
    if "error" in proposal:
        log(f"[EVOLVE] Could not generate proposal: {proposal['error']}")
        return

    proposal["proposed_at"] = date_str
    proposal["status"]      = "pending"

    proposal_file = PROPOSALS / f"proposal_{date_str}.json"
    proposal_file.write_text(json.dumps(proposal, indent=2))

    log(f"[EVOLVE] Proposal saved → {proposal_file.name}")
    log(f"[EVOLVE] Issue  : {proposal.get('issue','?')}")
    log(f"[EVOLVE] Change : {str(proposal.get('proposed_change','?'))[:100]}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default: propose AND apply in one cycle
        run_evolve()
        run_apply()
    elif sys.argv[1] == "list":
        list_proposals()
    elif sys.argv[1] == "apply":
        run_apply()
    elif sys.argv[1] == "approve" and len(sys.argv) == 3:
        approve_proposal(sys.argv[2])
    else:
        print("Usage: nova_evolve.py [list|apply|approve <name>]")
