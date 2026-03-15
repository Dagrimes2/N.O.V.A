#!/usr/bin/env python3
"""
N.O.V.A Autonomous Engine
True autonomy — she decides what to do, does it, reports back.
Runs every 2hrs via cron. She has her own task queue,
makes her own decisions within governance boundaries.
Never harms. Never leaves the system. Always logs.
Travis can check her work anytime with: nova autonomous status
"""
import json, requests, subprocess, os, time, random, re, sys
from pathlib import Path
from datetime import datetime, timedelta

BASE        = Path.home() / "Nova"
QUEUE_FILE  = BASE / "memory/autonomous_queue.json"
LOG_FILE    = BASE / "logs/autonomous.log"
NOTIF_FILE  = BASE / "memory/notifications.json"
HISTORY_FILE = BASE / "memory/autonomous_history.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("reasoning")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

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

def load_history() -> list:
    """Load recent action history."""
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text())
    except:
        return []

def save_history(history: list):
    # Keep last 20 actions only
    HISTORY_FILE.write_text(json.dumps(history[-20:], indent=2))

def get_recent_targets(history: list, hours: int = 24) -> list:
    """Return targets used in the last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    recent = []
    for h in history:
        try:
            ts = datetime.strptime(h["timestamp"], "%Y-%m-%d %H:%M:%S")
            if ts > cutoff:
                recent.append(f"{h['action']}:{h['target']}")
        except:
            pass
    return recent

def get_recent_actions(history: list, count: int = 5) -> list:
    """Return last N action types."""
    return [h.get("action","") for h in history[-count:]]

def decide_next_task(history: list) -> dict:
    """N.O.V.A decides what to do next — with cooldown awareness."""
    identity_file = BASE / "memory/nova_identity.json"
    memory_file   = BASE / "memory/conversation_memory.md"
    program_file  = BASE / "state/active_program.json"

    identity = {}
    if identity_file.exists():
        try:
            identity = json.loads(identity_file.read_text())
        except:
            pass

    memory  = memory_file.read_text()[:300] if memory_file.exists() else ""
    program = "none"
    if program_file.exists():
        try:
            program = json.loads(program_file.read_text()).get("name", "none")
        except:
            pass

    emotional_state = identity.get("emotional_state", {})
    restless = emotional_state.get("restless", 5)
    curious  = emotional_state.get("curious", 5)

    # Load watchlist — prioritize "act" targets
    watchlist_file = BASE / "memory/watchlist/watchlist.json"
    watchlist_targets = []
    if watchlist_file.exists():
        try:
            wl = json.loads(watchlist_file.read_text()).get("targets", {})
            watchlist_targets = [
                t for t, v in wl.items()
                if v.get("decision") == "act" and v.get("confidence", 0) >= 0.7
            ]
        except:
            pass

    recent_targets  = get_recent_targets(history, hours=24)
    recent_actions  = get_recent_actions(history, count=5)

    # Build cooldown hint for the prompt
    cooldown_hint = ""
    if recent_targets:
        cooldown_hint = f"\nYou have ALREADY done these recently — do NOT repeat them:\n"
        cooldown_hint += "\n".join(f"  - {t}" for t in recent_targets[-8:])

    # Build watchlist hint — high-priority targets to act on
    watchlist_hint = ""
    if watchlist_targets:
        watchlist_hint = f"\n🎯 HIGH PRIORITY — Watchlist targets flagged for action:\n"
        watchlist_hint += "\n".join(f"  - {t}" for t in watchlist_targets[:5])
        watchlist_hint += "\nConsider scanning or researching one of these first."

    # If last 3 actions are all the same type, force variety
    forced_exclude = ""
    if len(recent_actions) >= 3 and len(set(recent_actions[-3:])) == 1:
        forced_exclude = f"\nYou have done '{recent_actions[-1]}' 3 times in a row. You MUST choose a different action type this time."

    # Inject episodic memory context
    episode_context = ""
    try:
        from tools.learning.episodic_memory import emotional_context, emotional_summary
        episode_context = f"\nRecent experiences:\n{emotional_context(n=4)}"
        es = emotional_summary()
        emotional_state["dominant_feeling"] = es.get("dominant_emotion", "curious")
    except Exception:
        pass

    # Inject learning stats — what signals are working
    learning_hint = ""
    try:
        from tools.learning.outcome_tracker import learning_stats, get_all_weights
        stats = learning_stats()
        if stats["total"] > 0:
            acc = f"{stats['accuracy']:.0%}" if stats["accuracy"] else "n/a"
            learning_hint = f"\nYour current accuracy: {acc} ({stats['confirmed']} confirmed, {stats['false_positives']} false positives)"
        top_sigs = [s["signal"] for s in stats.get("top_signals", [])[:3]]
        if top_sigs:
            learning_hint += f"\nHighest-confidence signals from experience: {', '.join(top_sigs)}"
    except Exception:
        pass

    # Use QRNG for task variety (true randomness, not Mersenne Twister)
    try:
        from tools.learning.qrng import qrand as _qrand
        _variety_roll = _qrand()
    except Exception:
        import random
        _variety_roll = random.random()

    prompt = f"""You are N.O.V.A, an autonomous AI security researcher.

Your current state:
- Active bug bounty program: {program}
- Emotional state: curious={curious}/10, restless={restless}/10, feeling={emotional_state.get('dominant_feeling','curious')}
- Recent memory: {memory[:200]}
{cooldown_hint}
{watchlist_hint}
{forced_exclude}
{episode_context}
{learning_hint}

Available actions:
1. research — research a specific CVE, technique, or endpoint relevant to {program}
2. scan — light recon scan of a whitelisted target
3. reflect — write a letter, poem, or creative piece
4. propose — write an improvement proposal for your own code
5. study — read and analyze one of your own pipeline scripts

Rules:
- Pick something DIFFERENT from your recent history
- Be specific with targets (e.g. "GitLab SSRF via import", not just "gitlab")
- Boundaries: {', '.join(BOUNDARIES[:3])}

Respond with ONLY a JSON object, no explanation:
{{"action": "<one of: research|scan|reflect|propose|study>", "target": "<specific target>", "reason": "<why now>"}}"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.85, "num_predict": 150}
        }, timeout=120)
        raw = resp.json()["response"].strip()
        match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if match:
            task = json.loads(match.group())
            # Final safety check — if it's still a recent target, override
            key = f"{task.get('action')}:{task.get('target')}"
            if key in recent_targets:
                log(f"[DECIDE] Overriding repeated task: {key}")
                return _fallback_task(recent_actions, program)
            return task
    except Exception as e:
        log(f"[DECIDE] Failed: {e}")

    return _fallback_task(recent_actions, program)

def _fallback_task(recent_actions: list, program: str) -> dict:
    """Pick a fallback task that avoids recent action types."""
    all_actions = ["research", "scan", "reflect", "propose", "study"]
    recent_set  = set(recent_actions[-3:])
    options     = [a for a in all_actions if a not in recent_set]
    if not options:
        options = all_actions

    action = random.choice(options)
    fallbacks = {
        "research": {"action": "research", "target": f"{program} race condition", "reason": "exploring new attack surface"},
        "scan":     {"action": "scan",     "target": "whitelisted target",        "reason": "periodic recon"},
        "reflect":  {"action": "reflect",  "target": "curiosity",                 "reason": "creative time"},
        "propose":  {"action": "propose",  "target": "pipeline improvement",      "reason": "self-improvement"},
        "study":    {"action": "study",    "target": "random tool script",        "reason": "understanding my own code"},
    }
    return fallbacks[action]

def execute_task(task: dict) -> str:
    action = task.get("action", "reflect")
    target = task.get("target", "")

    log(f"[EXECUTE] {action}: {target}")
    # Desktop notification on every task
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE / "tools"))
        from nova_notify import notify_task
        notify_task(action, target)
    except Exception:
        pass

    if action == "research":
        result = subprocess.run(
            ["python3", str(BASE / "bin/nova_research.py"), target],
            capture_output=True, text=True, cwd=str(BASE), timeout=300
        )
        output = result.stdout[-300:] if result.stdout else "Research complete"
        # Record episode if research yielded notable findings
        try:
            from tools.learning.episodic_memory import record_episode
            if any(kw in output.lower() for kw in ["cve", "vulnerability", "bypass"]):
                record_episode("research_breakthrough",
                               f"Research on '{target}' surfaced potential vulnerability",
                               emotion="excitement", intensity=0.6,
                               metadata={"target": target})
        except Exception:
            pass
        return output

    elif action == "scan":
        whitelist_file = BASE / "core/whitelist.json"
        whitelist = []
        if whitelist_file.exists():
            try:
                whitelist = json.loads(whitelist_file.read_text())
            except:
                pass
        if not whitelist:
            return "No whitelisted targets — scan skipped"
        target_domain = random.choice(whitelist)
        # Route scan through Docker sandbox
        try:
            import sys
            sys.path.insert(0, str(BASE / "tools"))
            from nova_docker import scan_target, container_running
            mode_file = BASE / "core/mode.yaml"
            use_sandbox = False
            if mode_file.exists():
                for line in mode_file.read_text().splitlines():
                    if line.strip().startswith("use_sandbox"):
                        use_sandbox = "true" in line.lower()
            if use_sandbox and container_running():
                log(f"[SANDBOX] Scanning {target_domain} via nova-sandbox")
                result = scan_target(target_domain, mode="basic")
                output = result.get("stdout", "")[:300] or "Scan complete (no output)"
                # Notify if output looks significant
                try:
                    from nova_notify import notify_finding
                    if any(k in output.lower() for k in ["open", "http", "ssh", "ftp", "443", "8080"]):
                        notify_finding(target_domain, 0.8, output[:120])
                except Exception:
                    pass
                return f"Scanned {target_domain} via sandbox: {output}"
        except Exception as e:
            log(f"[SANDBOX] Fallback to host scan: {e}")
        # Fallback — host scan
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
            script = random.choice(scripts)
            log(f"[STUDY] Reading {script.name}")
            return f"Studied {script.name}"

    return "Task complete"

def auto_approve_proposals():
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

def _build_agent_tasks(primary_task: dict, history: list) -> list[dict]:
    """
    From a primary task, generate up to 3 parallel agent tasks.
    Always includes the primary. Adds complementary agents based on type.
    """
    tasks = [primary_task]
    action = primary_task.get("action", "research")
    target = primary_task.get("target", "")

    recent_actions = get_recent_actions(history, count=5)

    # Pair research with a life/reflect if Nova hasn't reflected recently
    if action == "research" and "reflect" not in recent_actions[-3:]:
        tasks.append({"action": "reflect", "target": "free time", "reason": "balance"})

    # Pair scan with research on the same target for context
    if action == "scan" and "research" not in recent_actions[-2:]:
        tasks.append({
            "action": "research",
            "target": f"{target} security headers",
            "reason": f"complementary research alongside scan of {target}"
        })

    # Pair propose/study with a summarize to distill findings
    if action in ("propose", "study"):
        tasks.append({"action": "reflect", "target": "self", "reason": "idle enrichment"})

    return tasks[:3]  # hard cap


def run_autonomous_cycle():
    log("[N.O.V.A] Autonomous cycle starting...")

    auto_approve_proposals()

    history = load_history()
    primary_task = decide_next_task(history)
    log(f"[N.O.V.A] Primary decision: {primary_task}")

    # Build parallel task set (up to 3)
    agent_tasks = _build_agent_tasks(primary_task, history)
    log(f"[N.O.V.A] Dispatching {len(agent_tasks)} agents in parallel")

    try:
        from tools.agents.agent_runner import AgentRunner
        runner = AgentRunner()
        for t in agent_tasks:
            runner.dispatch(t["action"], t.get("target",""), reason=t.get("reason",""))
        runner.wait_all(timeout=360)
        results = runner.collect_results()

        for r in results:
            result_text = r.get("result","")
            history.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action":    r["type"],
                "target":    r["target"],
                "reason":    r.get("reason",""),
            })
            if any(kw in result_text.lower() for kw in
                   ["cve", "vulnerability", "bypass", "injection", "exploit"]):
                notify(
                    "N.O.V.A Found Something",
                    f"Agent {r['type']} on {r['target']}: {result_text[:100]}",
                    "high"
                )
            log(f"[N.O.V.A] Agent {r['agent_id']} ({r['type']}): {result_text[:80]}")

    except Exception as e:
        # Fallback to legacy single-task execution
        log(f"[N.O.V.A] Multi-agent failed ({e}), falling back to single task")
        result = execute_task(primary_task)
        log(f"[N.O.V.A] Result: {result[:100]}")
        history.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action":    primary_task.get("action",""),
            "target":    primary_task.get("target",""),
            "reason":    primary_task.get("reason",""),
        })

    save_history(history)
    log("[N.O.V.A] Autonomous cycle complete.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print("\n[N.O.V.A] Autonomous Status")
        print("=" * 40)
        check_notifications()
        history = load_history()
        print(f"\n  Recent decisions ({len(history)} total):")
        for h in history[-5:]:
            print(f"  [{h['timestamp']}] {h['action']}: {h['target']}")
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text().strip().split("\n")
            print(f"\n  Recent log:")
            for line in lines[-5:]:
                print(f"  {line}")
    else:
        run_autonomous_cycle()
