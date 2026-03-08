#!/usr/bin/env python3
"""
N.O.V.A Self-Evolution Engine
Reads own code, proposes improvements, waits for Travis approval.
Never modifies herself without permission.
"""
import json, requests, os, random, sys
from pathlib import Path
from datetime import datetime

BASE       = Path.home() / "Nova"
PROPOSALS  = BASE / "memory/proposals"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

PROPOSALS.mkdir(parents=True, exist_ok=True)

EVOLVABLE = [
    "tools/reasoning/hypothesize.py",
    "tools/reasoning/reflect.py",
    "tools/scoring/score.py",
    "bin/nova_dream.py",
    "bin/nova_life.py",
]

def read_script(path: str) -> str:
    full = BASE / path
    return full.read_text() if full.exists() else ""

def propose_improvement(script_path: str) -> dict:
    code = read_script(script_path)
    if not code:
        return {"error": "file not found"}

    prompt = f"""You are N.O.V.A reviewing your own code for one improvement.

File: {script_path}
Code snippet:
{code[:800]}

Return ONE improvement as JSON:
{{
  "file": "{script_path}",
  "issue": "one specific weakness",
  "proposed_change": "exactly what to change",
  "expected_improvement": "what gets better",
  "risk": "low",
  "confidence": 0.8
}}

Return ONLY the JSON object."""

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
        parsed = json.loads(raw)
        return parsed
    except Exception as e:
        return {"error": str(e)}

def list_proposals():
    proposals = sorted(PROPOSALS.glob("proposal_*.json"))
    if not proposals:
        print("[N.O.V.A] No pending proposals.")
        return
    print(f"\n[N.O.V.A] {len(proposals)} pending proposals:\n")
    for p in proposals:
        try:
            data = json.loads(p.read_text())
            status = data.get("status", "pending")
            print(f"  {p.name}  [{status}]")
            print(f"    File   : {data.get('file','?')}")
            print(f"    Issue  : {data.get('issue','?')}")
            print(f"    Change : {str(data.get('proposed_change','?'))[:80]}...")
            print(f"    Risk   : {data.get('risk','?')}")
            print()
        except:
            print(f"  {p.name} [unreadable]")

def approve_proposal(proposal_name: str):
    path = PROPOSALS / proposal_name
    if not path.exists():
        print(f"[!] Proposal not found: {proposal_name}")
        return
    data = json.loads(path.read_text())
    print(f"\n[N.O.V.A] Reviewing: {proposal_name}")
    print(f"  File   : {data.get('file')}")
    print(f"  Issue  : {data.get('issue')}")
    print(f"  Change : {data.get('proposed_change')}")
    print(f"  Risk   : {data.get('risk')}")
    confirm = input("\nApprove this proposal? [yes/no]: ").strip().lower()
    if confirm != "yes":
        print("[N.O.V.A] Cancelled.")
        return
    data["approved"]    = True
    data["approved_at"] = datetime.now().isoformat()
    data["approved_by"] = "Travis"
    data["status"]      = "approved"
    path.write_text(json.dumps(data, indent=2))
    print(f"[N.O.V.A] ✓ Approved. Implement manually or wait for auto-apply.")

def run_evolve():
    script   = random.choice(EVOLVABLE)
    date_str = datetime.now().strftime("%Y-%m-%d-%H%M")
    print(f"[N.O.V.A] Analyzing {script} for improvements...")

    proposal = propose_improvement(script)
    if "error" in proposal:
        print(f"[!] Could not generate proposal: {proposal['error']}")
        return

    proposal["proposed_at"] = date_str
    proposal["status"]      = "pending"

    proposal_file = PROPOSALS / f"proposal_{date_str}.json"
    proposal_file.write_text(json.dumps(proposal, indent=2))

    print(f"\n[N.O.V.A] Proposal saved → {proposal_file.name}")
    print(f"  Issue  : {proposal.get('issue','?')}")
    print(f"  Change : {str(proposal.get('proposed_change','?'))[:100]}")
    print(f"  Risk   : {proposal.get('risk','?')}")
    print(f"\n  Review : nova evolve list")
    print(f"  Approve: nova evolve approve {proposal_file.name}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        run_evolve()
    elif sys.argv[1] == "list":
        list_proposals()
    elif sys.argv[1] == "approve" and len(sys.argv) == 3:
        approve_proposal(sys.argv[2])
    else:
        print("Usage: nova_evolve.py [list|approve <name>]")
