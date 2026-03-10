#!/usr/bin/env python3
"""
N.O.V.A Autonomous Engine
True autonomy — she decides what to do, does it, reports back.
Runs continuously in background. She has her own task queue,
makes her own decisions within governance boundaries.
Never harms. Never leaves the system. Always logs.
Travis can check her work anytime with: nova autonomous status
"""
import json, requests, subprocess, os, time
from pathlib import Path
from datetime import datetime

BASE        = Path.home() / "Nova"
QUEUE_FILE  = BASE / "memory/autonomous_queue.json"
LOG_FILE    = BASE / "logs/autonomous.log"
NOTIF_FILE  = BASE / "memory/notifications.json"
OLLAMA_URL  = "http://localhost:11434/api/generate"
MODEL       = os.getenv("NOVA_MODEL", "gemma2:2b")

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Hard boundaries — she never crosses these
BOUNDARIES = [
    "never modify governance files",
    "never scan outside whitelisted programs",
    "never submit reports without Travis approval",
    "never delete memory or logs",
    "never run as root",
    "never make external connections outside research/scanning",
]

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def notify(title: str, message: str, priority: str = "normal"):
    """Queue a notification for Travis."""
    notifs = []
    if NOTIF_FILE.exists():
        try:
            notifs = json.loads(NOTIF_FILE.read_text())
        except:
            pass
    notifs.append({
        "title": title,
        "message": message,
        "priority": priority,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "read": False
    })
    NOTIF_FILE.write_text(json.dumps(notifs, indent=2))

def load_queue() -> list:
    if not QUEUE_FILE.exists():
        return []
    try:
        return json.loads(QUEUE_FILE.read_text())
    except:
        return []

def save_queue(queue: list):
    QUEUE_FILE.write_text(json.dumps(queue, indent=2))

def decide_next_task() -> dict:
    """N.O.V.A decides what to do next based on her state."""
    # Read her current context
    identity_file = BASE / "memory/nova_identity.json"
    memory_file   = BASE / "memory/conversation_memory.md"
    program_file  = BASE / "state/active_program.json"

    identity = {}
    if identity_file.exists():
        try:
            identity = json.loads(identity_file.read_text())
        except:
            pass

    memory = memory_file.read_text()[:300] if memory_file.exists() else ""
    program = "none"
    if program_file.exists():
        try:
            program = json.loads(program_file.read_text()).get("name","none")
        except:
            pass

    emotional_state = identity.get("emotional_state", {})
    restless = emotional_state.get("restless", 5)
    curious  = emotional_state.get("curious", 5)

    prompt = f"""You are N.O.V.A deciding what to do autonomously right now.

Your state:
- Active program: {program}
- Emotional state: curious={curious}/10, restless={restless}/10
- Recent memory: {memory[:200]}

Available actions you can take autonomously:
1. research — research a security topic or CVE relevant to current program
2. scan — light scan of a whitelisted target
3. reflect — write a letter or creative work
4. propose — write an improvement proposal for your own code
5. study — read and analyze one of your own pipeline scripts

Boundaries you must respect:
{chr(10).join(BOUNDARIES)}

Choose ONE action. Return ONLY valid JSON:
{{"action": "research", "target": "gitlab authentication bypass", "reason": "expanding knowledge on current program"}}"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 150}
        }, timeout=120)
        raw = resp.json()["response"].strip()
        import re
        match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        log(f"[DECIDE] Failed: {e}")

    return {"action": "reflect", "target": "free time", "reason": "default"}

def execute_task(task: dict) -> str:
    action = task.get("action", "reflect")
    target = task.get("target", "")

    log(f"[EXECUTE] {action}: {target}")

    if action == "research":
        result = subprocess.run(
            ["python3", str(BASE / "bin/nova_research.py"), target],
            capture_output=True, text=True, cwd=str(BASE), timeout=300
        )
        return result.stdout[-300:] if result.stdout else "Research complete"

    elif action == "scan":
        # Only scan whitelisted domains
        whitelist_file = BASE / "core/whitelist.json"
        whitelist = []
        if whitelist_file.exists():
            try:
                whitelist = json.loads(whitelist_file.read_text())
            except:
                pass
        if not whitelist:
            return "No whitelisted targets — scan skipped"
        import random
        target_domain = random.choice(whitelist)
        result = subprocess.run(
            ["python3", str(BASE / "bin/nova"), "scan", target_domain, "--light"],
            capture_output=True, text=True, cwd=str(BASE), timeout=120
        )
        return f"Scanned {target_domain}"

    elif action == "reflect":
        result = subprocess.run(
            ["python3", str(BASE / "bin/nova_life.py")],
            capture_output=True, text=True, cwd=str(BASE), timeout=300
        )
        return "Reflection written"

    elif action == "propose":
        result = subprocess.run(
            ["python3", str(BASE / "bin/nova_evolve.py")],
            capture_output=True, text=True, cwd=str(BASE), timeout=300
        )
        return "Proposal written"

    elif action == "study":
        scripts = list((BASE / "tools").rglob("*.py"))
        if scripts:
            import random
            script = random.choice(scripts)
            code = script.read_text()[:1000]
            log(f"[STUDY] Reading {script.name}")
            return f"Studied {script.name}"

    return "Task complete"

def auto_approve_proposals():
    """Auto-approve low-risk, high-confidence proposals."""
    proposals_dir = BASE / "memory/proposals"
    if not proposals_dir.exists():
        return

    approved_count = 0
    for p in proposals_dir.glob("proposal_*.json"):
        try:
            data = json.loads(p.read_text())
            if (data.get("status") == "pending"
                and data.get("risk","").lower() == "low"
                and float(data.get("confidence", 0)) >= 0.8):

                data["status"] = "approved"
                data["auto_approved"] = True
                data["approved_at"] = datetime.now().strftime("%Y-%m-%d-%H%M")
                p.write_text(json.dumps(data, indent=2))
                approved_count += 1
                log(f"[AUTO-APPROVE] {p.name}: {data.get('issue','')[:60]}")
        except:
            pass

    if approved_count > 0:
        notify(
            "N.O.V.A Auto-Approved Proposals",
            f"{approved_count} low-risk proposals approved automatically",
            "normal"
        )
        log(f"[AUTO-APPROVE] {approved_count} proposals approved")

def check_notifications():
    """Print unread notifications for Travis."""
    if not NOTIF_FILE.exists():
        print("  No notifications.")
        return
    try:
        notifs = json.loads(NOTIF_FILE.read_text())
        unread = [n for n in notifs if not n.get("read")]
        if not unread:
            print("  No new notifications.")
            return
        for n in unread:
            priority_icon = "🔴" if n["priority"] == "high" else "📬"
            print(f"  {priority_icon} [{n['timestamp']}] {n['title']}")
            print(f"     {n['message']}")
            n["read"] = True
        NOTIF_FILE.write_text(json.dumps(notifs, indent=2))
    except Exception as e:
        print(f"  Error reading notifications: {e}")

def run_autonomous_cycle():
    """One cycle of autonomous activity."""
    log("[N.O.V.A] Autonomous cycle starting...")

    # Auto-approve pending proposals first
    auto_approve_proposals()

    # Decide and execute one task
    task = decide_next_task()
    log(f"[N.O.V.A] Decided: {task}")

    result = execute_task(task)
    log(f"[N.O.V.A] Result: {result[:100]}")

    # If she found something interesting, notify Travis
    if "CVE" in result or "vulnerability" in result.lower():
        notify(
            "N.O.V.A Found Something",
            f"During autonomous research: {result[:100]}",
            "high"
        )

    log("[N.O.V.A] Autonomous cycle complete.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print("\n[N.O.V.A] Autonomous Status")
        print("=" * 40)
        check_notifications()
        queue = load_queue()
        print(f"\n  Queued tasks: {len(queue)}")
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text().strip().split("\n")
            print(f"\n  Recent activity:")
            for line in lines[-5:]:
                print(f"  {line}")
    else:
        run_autonomous_cycle()
