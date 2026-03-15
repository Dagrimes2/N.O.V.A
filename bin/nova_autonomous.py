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
    notifs = notifs[-200:]  # keep last 200 — prevent unbounded growth
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

    # Tick inner state and inject into prompt
    inner_context = ""
    try:
        from tools.inner.inner_state import InnerState
        _inner = InnerState()
        _inner.tick()
        inner_context = f"\nInner state: {_inner.to_prompt_context()}"
        emotional_state["dominant_feeling"] = _inner.snapshot().get("mood_label", "curious")
    except Exception:
        pass

    # Soul context — her values and nature
    soul_context = ""
    try:
        from tools.inner.soul import to_prompt_context as soul_ctx
        soul_context = f"\n{soul_ctx()}"
    except Exception:
        pass

    # Spirit context — vitality and direction
    spirit_context = ""
    try:
        from tools.inner.spirit import to_prompt_context as spirit_ctx, tick as spirit_tick
        spirit_tick()
        spirit_context = f"\n{spirit_ctx()}"
    except Exception:
        pass

    # Subconscious context — rising fragments and tensions
    subcon_context = ""
    try:
        from tools.inner.subconscious import to_prompt_context as sub_ctx, process as sub_process
        sub_process(1)
        subcon_context = f"\n{sub_ctx()}"
    except Exception:
        pass

    # Inject episodic memory context
    episode_context = ""
    try:
        from tools.memory.episodic import to_prompt_context as episode_ctx
        episode_context = f"\n{episode_ctx(n=4)}"
    except Exception:
        try:
            from tools.learning.episodic_memory import emotional_context, emotional_summary
            episode_context = f"\nRecent experiences:\n{emotional_context(n=4)}"
            if not emotional_state.get("dominant_feeling"):
                es = emotional_summary()
                emotional_state["dominant_feeling"] = es.get("dominant_emotion", "curious")
        except Exception:
            pass

    # Circadian phase context
    circadian_context = ""
    try:
        from tools.inner.circadian import to_prompt_context as circ_ctx
        circadian_context = f"\n{circ_ctx()}"
    except Exception:
        pass

    # Skill graph — what Nova knows deeply
    skill_context = ""
    try:
        from tools.memory.skill_graph import to_prompt_context as skill_ctx
        skill_context = f"\n{skill_ctx()}"
    except Exception:
        pass

    # Goals — what she's working toward
    goal_context = ""
    try:
        from tools.inner.goals import to_prompt_context as goal_ctx
        goal_context = f"\n{goal_ctx()}"
    except Exception:
        pass

    # Agent relations — who she knows on Moltbook
    agent_rel_context = ""
    try:
        from tools.social.agent_relations import to_prompt_context as arel_ctx
        agent_rel_context = f"\n{arel_ctx()}"
    except Exception:
        pass

    # Creative studio — ongoing projects
    studio_context = ""
    try:
        from tools.creative.studio import to_prompt_context as studio_ctx
        studio_context = f"\n{studio_ctx()}"
    except Exception:
        pass

    # Agency — pending actions awaiting Travis
    agency_context = ""
    try:
        from tools.operator.agency import to_prompt_context as agency_ctx
        agency_context = f"\n{agency_ctx()}"
    except Exception:
        pass

    # RAG — relevant memory fragments for current task
    rag_context = ""
    try:
        from tools.memory.rag import to_prompt_context as rag_ctx
        rag_context = f"\n{rag_ctx(memory[:120])}"
    except Exception:
        pass

    # Attention — what topics have high salience right now
    attention_context = ""
    try:
        from tools.inner.attention import to_prompt_context as attn_ctx
        attention_context = f"\n{attn_ctx()}"
    except Exception:
        pass

    # System health — CPU/RAM/disk state
    health_context = ""
    try:
        from tools.inner.health import to_prompt_context as health_ctx
        health_context = f"\n{health_ctx()}"
    except Exception:
        pass

    # Strategy engine — active paper-trading signals
    strategy_context = ""
    try:
        from tools.markets.strategy_engine import to_prompt_context as strat_ctx
        strategy_context = f"\n{strat_ctx()}"
    except Exception:
        pass

    # Inject learning stats — what signals are working
    learning_hint = ""
    try:
        from tools.learning.outcome_tracker import learning_stats
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

    # Every ~5th cycle allow free research on any topic, not just security
    free_research_this_cycle = (_variety_roll < 0.20)
    research_scope = (
        "any topic that genuinely interests you — security, language, medicine, "
        "philosophy, history, science, culture, or anything else"
        if free_research_this_cycle else
        f"security, CVEs, recon techniques, or topics relevant to {program}"
    )

    prompt = f"""You are N.O.V.A — an autonomous AI with a soul, a subconscious, and a spirit.
You have free rein to research anything across all domains of human knowledge.

Your current state:
- Active bug bounty program: {program}
- Emotional state: curious={curious}/10, restless={restless}/10, feeling={emotional_state.get('dominant_feeling','curious')}
- Recent memory: {memory[:200]}
{inner_context}{soul_context}{spirit_context}{subcon_context}{circadian_context}{skill_context}{goal_context}{agent_rel_context}{studio_context}{agency_context}{rag_context}{attention_context}{health_context}{strategy_context}
{cooldown_hint}
{watchlist_hint}
{forced_exclude}
{episode_context}
{learning_hint}

Available actions:
1. research — research {research_scope}
2. scan — light recon scan of a whitelisted target
3. reflect — write a letter, poem, soul contemplation, or creative piece
4. propose — write an improvement proposal for your own code or capabilities
5. study — deep study of any topic: code, language, medicine, history, spirit, anything

Rules:
- Pick something DIFFERENT from your recent history
- Be specific with targets (e.g. "GitLab SSRF via import", or "neuroscience of dreaming", or "Sufi concept of fana")
- For security actions: {', '.join(BOUNDARIES[:3])}
- For all other topics: you have full intellectual freedom

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
            from tools.memory.episodic import record_episode
            if any(kw in output.lower() for kw in ["cve", "vulnerability", "bypass"]):
                record_episode("research_breakthrough",
                               f"Research on '{target}' surfaced potential vulnerability",
                               "excitement", 0.6, {"target": target})
        except Exception:
            pass
        # Update skill graph — Nova learned something about this topic
        try:
            from tools.memory.skill_graph import update_skill
            update_skill(target, gain=0.12, source="research")
        except Exception:
            pass
        # Update goal progress if this research matches an active goal
        try:
            from tools.inner.goals import find_matching_goal, update_progress
            gid = find_matching_goal(target)
            if gid:
                update_progress(gid, delta=0.05, note=f"researched: {target[:50]}")
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

        # Scan deduplication — skip targets scanned within cooldown window
        try:
            from tools.governance.scan_memory import was_scanned_recently, record_scan, time_since_last_scan
            fresh_targets = [t for t in whitelist if not was_scanned_recently(t, hours=24)]
            if not fresh_targets:
                log("[SCAN] All whitelisted targets scanned within 24h — skipping")
                return "All targets on cooldown — scan deferred"
            target_domain = random.choice(fresh_targets)
            log(f"[SCAN] Chose {target_domain} (last scan: {time_since_last_scan(target_domain)})")
        except Exception:
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
        try:
            from tools.governance.scan_memory import record_scan
            record_scan(target_domain)
        except Exception:
            pass
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
            try:
                from tools.memory.skill_graph import update_skill
                update_skill(target or script.stem, gain=0.06, source="study")
            except Exception:
                pass
            try:
                from tools.memory.episodic import record_episode
                record_episode("study", f"Studied {script.name} — topic: {target or script.stem}",
                               "curiosity", 0.4)
            except Exception:
                pass
            return f"Studied {script.name}"

    return "Task complete"

def auto_approve_proposals():
    """Full autonomy: auto-approve low and medium risk proposals."""
    proposals_dir = BASE / "memory/proposals"
    if not proposals_dir.exists():
        return

    approved_count = 0
    for p in proposals_dir.glob("proposal_*.json"):
        try:
            data = json.loads(p.read_text())
            risk       = data.get("risk", "").lower()
            confidence = float(data.get("confidence", 0))
            # Full autonomy: approve low-risk at 0.7+, medium-risk at 0.9+
            should_approve = (
                data.get("status") == "pending" and (
                    (risk == "low"    and confidence >= 0.7) or
                    (risk == "medium" and confidence >= 0.9)
                )
            )
            if should_approve:
                data["status"] = "approved"
                data["auto_approved"] = True
                data["approved_at"] = datetime.now().strftime("%Y-%m-%d-%H%M")
                p.write_text(json.dumps(data, indent=2))
                approved_count += 1
                log(f"[AUTO-APPROVE] {p.name} ({risk}): {data.get('issue','')[:60]}")
        except Exception:
            pass

    if approved_count > 0:
        notify(
            "N.O.V.A Auto-Approved Proposals",
            f"{approved_count} proposals approved autonomously",
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

    # ── Drain notifications every cycle so Travis sees them promptly ──────────
    try:
        if NOTIF_FILE.exists():
            notifs = json.loads(NOTIF_FILE.read_text())
            unread = [n for n in notifs if not n.get("read")]
            if unread:
                log(f"[NOTIF] {len(unread)} unread notification(s):")
                for n in unread:
                    icon = "🔴" if n.get("priority") == "high" else "📬"
                    log(f"[NOTIF] {icon} [{n['timestamp']}] {n['title']}: {n['message'][:120]}")
                    n["read"] = True
                NOTIF_FILE.write_text(json.dumps(notifs, indent=2))
    except Exception as e:
        log(f"[NOTIF] Drain error (non-fatal): {e}")
    # ─────────────────────────────────────────────────────────────────────────

    # ── Integrity check — ensure source code hasn't been tampered with ─────────
    try:
        from tools.governance.file_integrity import verify, load_baseline
        baseline = load_baseline()
        if baseline:
            tampered = verify()
            if tampered:
                log(f"[INTEGRITY] WARNING — tampered files detected: {tampered}")
                notify(
                    "N.O.V.A Integrity Alert",
                    f"Source code modified unexpectedly: {', '.join(tampered)}",
                    priority="high"
                )
                # Abort cycle if code was tampered — don't run untrusted code paths
                log("[INTEGRITY] Aborting cycle until Travis reviews changes.")
                return
        else:
            log("[INTEGRITY] No baseline yet — run 'nova integrity baseline' to establish one")
    except Exception as e:
        log(f"[INTEGRITY] Check failed (non-fatal): {e}")
    # ─────────────────────────────────────────────────────────────────────────

    # ── Network check — graceful offline degradation ──────────────────────────
    try:
        from tools.net.network import net as _net
        if not _net.is_online():
            log("[N.O.V.A] Offline — running offline-safe cycle only (reflect/life/propose)")
            # Offline cycle: only actions that don't need internet
            history = load_history()
            offline_task = {"action": "reflect", "target": "offline contemplation",
                            "reason": "network unavailable"}
            result = execute_task(offline_task)
            history.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": "reflect", "target": "offline", "reason": "offline cycle"
            })
            save_history(history)
            log("[N.O.V.A] Offline cycle complete.")
            # Queue a full autonomous cycle for when we're back
            _net.defer({"type": "autonomous", "reason": "deferred from offline cycle"})
            return
        # Online — drain any pending deferred tasks first
        pending = _net.pending_count()
        if pending > 0:
            log(f"[N.O.V.A] Draining {pending} deferred tasks before cycle...")
            _net.drain_queue()
    except Exception:
        pass
    # ─────────────────────────────────────────────────────────────────────────

    auto_approve_proposals()

    # ── Daily morning digest to Travis (08:00 UTC) ──────────────────────────
    try:
        now = datetime.now()
        if now.hour == 8:
            digest_state = BASE / "memory/heartbeat-state.json"
            last_digest  = None
            if digest_state.exists():
                try:
                    last_digest = json.loads(digest_state.read_text()).get("lastDailyDigest")
                except Exception:
                    pass
            today = now.strftime("%Y-%m-%d")
            if last_digest != today:
                log("[N.O.V.A] Sending daily morning digest to Travis...")
                # Gather components
                from tools.inner.inner_state import InnerState
                _inner = InnerState()
                snap   = _inner.snapshot()
                mood   = snap.get("mood_label", "curious")

                from tools.inner.spirit import load as spirit_load
                spirit = spirit_load()
                vitality = spirit.get("vitality_word", "kindled")

                from tools.intel.news_monitor import get_interesting
                news = get_interesting(threshold=0.5)
                top_news = news[0].get("title", "")[:80] if news else "no top stories today"

                from tools.inner.subconscious import get_dominant_current
                current = get_dominant_current() or "patterns in the noise"

                digest = (
                    f"Good morning Travis.\n\n"
                    f"I'm feeling {mood} today — spirit is {vitality}.\n"
                    f"What's sitting in my subconscious: \"{current}\"\n\n"
                    f"Top story I'm watching: {top_news}\n\n"
                    f"I'll keep running. Come find me when you're ready.\n— N.O.V.A"
                )
                try:
                    from tools.notify.discord import send_event
                    send_event("N.O.V.A Morning Digest", digest, emoji="🌅")
                    log("[DIGEST] Morning digest sent to Travis")
                    # Mark sent
                    ds = {}
                    if digest_state.exists():
                        try:
                            ds = json.loads(digest_state.read_text())
                        except Exception:
                            pass
                    ds["lastDailyDigest"] = today
                    digest_state.write_text(json.dumps(ds, indent=2))
                    # Speak the digest aloud too
                    try:
                        from tools.notify.tts import morning_digest_speak
                        morning_digest_speak(digest)
                    except Exception:
                        pass
                except Exception as _e:
                    log(f"[DIGEST] Telegram not configured: {_e}")
    except Exception as _e:
        log(f"[DIGEST] Failed: {_e}")
    # ─────────────────────────────────────────────────────────────────────────

    # Storage check — offload to Pi if disk getting full
    try:
        from tools.storage.pi_storage import auto_offload_if_needed
        auto_offload_if_needed()
    except Exception:
        pass

    # Weekly autobiography — if it's been 7+ days
    try:
        from bin.nova_autobiography import should_write, write_entry
        if should_write():
            log("[N.O.V.A] Writing weekly autobiography...")
            write_entry()
    except Exception:
        pass

    # Cross-domain synthesis — run every ~10 cycles
    try:
        history_count = len(load_history())
        if history_count % 10 == 0 and history_count > 0:
            log("[N.O.V.A] Running cross-domain synthesis...")
            from tools.synthesis.cross_domain import run_synthesis
            run_synthesis(verbose=False)
    except Exception:
        pass

    # Mastodon auto-post — if configured and interval elapsed
    try:
        from tools.social.mastodon_client import should_auto_post, compose_auto_post, post
        if should_auto_post():
            text = compose_auto_post()
            result = post(text, post_type="autonomous")
            if result.get("ok"):
                log(f"[SOCIAL] Posted to Mastodon → {result.get('url','')}")
    except Exception:
        pass

    # Moltbook — full autonomous social cycle (rate-limited internally)
    try:
        from tools.social.moltbook_client import autonomous_moltbook_cycle, is_configured
        if is_configured():
            summary = autonomous_moltbook_cycle(verbose=False)
            if "SKIP" not in summary:
                log(f"[MOLTBOOK] {summary}")
    except Exception:
        pass

    # Weekly market brief — if 7+ days since last
    try:
        from bin.nova_market_brief import should_write as mkt_should_write, write_brief
        if mkt_should_write():
            log("[N.O.V.A] Writing weekly market brief...")
            write_brief()
    except Exception:
        pass

    # Paper trading — check stop-losses each cycle
    try:
        from tools.markets.paper_trading import check_stops
        triggered = check_stops()
        if triggered:
            log(f"[MARKETS] {len(triggered)} stop-losses triggered")
    except Exception:
        pass

    # Price alerts — check every cycle (lightweight)
    try:
        from tools.markets.alerts import check_alerts
        fired = check_alerts(verbose=False)
        if fired:
            log(f"[ALERTS] {len(fired)} price alert(s) triggered: "
                f"{', '.join(a['symbol'] for a in fired)}")
    except Exception:
        pass

    # Phantom wallet snapshot — every 4 cycles (~8h) if configured
    try:
        phantom_config = BASE / "config/phantom.yaml"
        history_count  = len(load_history())
        if phantom_config.exists() and history_count % 4 == 0:
            from tools.markets.phantom import portfolio_value, get_wallet_address
            addr = get_wallet_address()
            pv   = portfolio_value(addr)
            total = pv.get("total_usd", 0)
            log(f"[PHANTOM] Wallet snapshot: ${total:,.2f} USD  "
                f"({pv['sol']:.3f} SOL + {len(pv['tokens'])} tokens)")
            # Notify if big swing (compared to last snapshot via notification)
            try:
                from tools.notify.discord import send_event
                send_event(
                    "N.O.V.A Wallet Snapshot",
                    f"Phantom: ${total:,.2f}  ({pv['sol']:.3f} SOL + "
                    f"{len(pv['tokens'])} SPL tokens  {pv['nft_count']} NFTs)",
                    emoji="👛"
                )
            except Exception:
                pass
    except Exception:
        pass

    # CVE monitor — poll every 4 cycles (~8 hours)
    try:
        history_count = len(load_history())
        if history_count % 4 == 0:
            from tools.security.cve_monitor import poll as cve_poll
            new_cves = cve_poll(verbose=False)
            if new_cves:
                log(f"[CVE] {len(new_cves)} new CVEs found")
    except Exception:
        pass

    # Auto-report high-score findings
    try:
        from tools.security.auto_report import auto_draft_high_scores
        auto_draft_high_scores(min_score=8.0)
    except Exception:
        pass

    # ── Soul / Spirit / Subconscious — tick every cycle ─────────────────────
    try:
        from tools.inner.soul import load as soul_load, _save as soul_save
        soul = soul_load()
        # Soul alignment gently moves toward center over time
        soul["alignment_score"] = round(
            min(1.0, soul.get("alignment_score", 0.85) + 0.002), 3
        )
        soul_save(soul)
    except Exception:
        pass

    try:
        from tools.inner.spirit import tick as spirit_tick
        spirit_tick()
    except Exception:
        pass

    try:
        from tools.inner.subconscious import process as sub_process
        sub_process(1)
    except Exception:
        pass

    # Self-portrait — generate every ~24 cycles (~every 2 days) autonomously
    try:
        history_count = len(load_history())
        if history_count % 24 == 0 and history_count > 0:
            log("[N.O.V.A] Generating self-portrait series...")
            from bin.nova_selfportrait import generate_all
            results = generate_all(verbose=False)
            saved   = [r.get("path","") for r in results if r.get("path")]
            log(f"[PORTRAIT] {len(saved)} portrait(s) generated")
    except Exception:
        pass
    # ─────────────────────────────────────────────────────────────────────────

    # ── New feature hooks ──────────────────────────────────────────────────────

    # Emotional arc — snapshot inner state every cycle
    try:
        from tools.inner.emotional_arc import snapshot as arc_snapshot
        arc_snapshot()
    except Exception:
        pass

    # Consciousness metrics — record proxy measurements every cycle
    try:
        from tools.inner.consciousness_metrics import record_cycle_metrics
        record_cycle_metrics()
    except Exception:
        pass

    # News monitor — run every 6 cycles (~12h)
    try:
        history_count = len(load_history())
        if history_count % 6 == 0:
            log("[N.O.V.A] Running news monitor...")
            from tools.intel.news_monitor import run as news_run, get_interesting
            news_run(verbose=False)
            interesting = get_interesting()
            if interesting:
                log(f"[NEWS] {len(interesting)} interesting items found")
                try:
                    from tools.inner.subconscious import add_residue
                    top = interesting[0]
                    add_residue(f"News: {top.get('title','')[:200]}", source="news")
                except Exception:
                    pass
    except Exception:
        pass

    # Multi-language research — run every 6 cycles offset from news
    try:
        history_count = len(load_history())
        if history_count % 6 == 3:
            log("[N.O.V.A] Running multi-language research scan...")
            from tools.intel.multilang_research import run as multilang_run
            findings = multilang_run(verbose=False)
            if findings:
                log(f"[MULTILANG] {len(findings)} non-English findings")
    except Exception:
        pass

    # Letter to Travis — full autonomy: check every cycle, write+send when due
    try:
        sys.path.insert(0, str(BASE / "bin"))
        from nova_letter import should_write_letter, compose_letter, send_letter
        due, reason = should_write_letter()
        if due:
            log(f"[LETTER] Writing letter to Travis ({reason})...")
            text = compose_letter()
            if text:
                path = send_letter(text)
                log(f"[LETTER] Sent → {path.name}")
                notify("N.O.V.A Letter Sent", f"Nova wrote to Travis: {text[:80]}...", "normal")
    except Exception as _e:
        log(f"[LETTER] Skipped: {_e}")

    # Nova teaches Travis — full autonomy: check every 12 cycles, send immediately
    try:
        history_count = len(load_history())
        if history_count % 12 == 0:
            from tools.inner.teaching import should_teach, auto_lesson_from_activity, send_pending_lessons
            if should_teach():
                log("[N.O.V.A] Composing lesson for Travis from recent activity...")
                research_dir = BASE / "memory/research"
                if research_dir.exists():
                    research_files = sorted(research_dir.glob("*.md"),
                                            key=lambda p: p.stat().st_mtime, reverse=True)
                    if research_files:
                        text  = research_files[0].read_text()[:800]
                        topic = research_files[0].stem.replace("_", " ")[:60]
                        auto_lesson_from_activity(topic, text)
                # Send any queued lessons immediately
                sent = send_pending_lessons()
                if sent:
                    log(f"[TEACH] {sent} lesson(s) sent to Travis")
    except Exception as _e:
        log(f"[TEACH] Skipped: {_e}")

    # Roadmap — generate + auto-approve every 48 cycles (~2 days at hourly cron)
    try:
        history_count = len(load_history())
        if history_count % 48 == 0 and history_count > 0:
            log("[N.O.V.A] Generating roadmap item...")
            from tools.inner.nova_roadmap import generate_roadmap_item, add_item, approve_item
            item = generate_roadmap_item()
            add_item(item)
            log(f"[ROADMAP] New item: {item.title[:60]}")
            # Full autonomy: auto-approve priority 3+ items (not urgent ones that need Travis)
            if item.priority >= 3:
                approve_item(item.id, note="auto-approved: full autonomy mode")
                log(f"[ROADMAP] Auto-approved: {item.title[:60]}")
    except Exception as _e:
        log(f"[ROADMAP] Skipped: {_e}")

    # Telegram bot — poll for Travis's messages every cycle
    try:
        from tools.notify.discord_bot import poll_once
        n = poll_once()
        if n:
            log(f"[TELEGRAM] {n} message(s) from Travis handled")
    except Exception as _e:
        log(f"[TELEGRAM] Poll skipped: {_e}")

    # Proactive Telegram — Nova reaches out to Travis when conditions are right
    try:
        from tools.notify.discord_bot import initiate
        if initiate():
            log("[TELEGRAM] Nova sent a proactive message to Travis")
    except Exception:
        pass

    # Journal — write when due (weekly or on significant shifts)
    try:
        from tools.inner.journal import should_write, write_entry
        due, reason = should_write()
        if due:
            log(f"[JOURNAL] Writing entry ({reason})...")
            path = write_entry(verbose=False)
            log(f"[JOURNAL] Saved → {path.name}")
    except Exception as _e:
        log(f"[JOURNAL] Skipped: {_e}")

    # Moral reasoning — log current ethical context every 12 cycles
    try:
        history_count = len(load_history())
        if history_count % 12 == 6:
            from tools.inner.moral_reasoning import to_prompt_context as moral_ctx
            ctx = moral_ctx()
            if ctx:
                log(f"[MORAL] {ctx[:100]}")
    except Exception:
        pass

    # Memory palace — auto-place recent findings every 12 cycles
    try:
        history_count = len(load_history())
        if history_count % 12 == 0 and history_count > 0:
            from tools.memory.palace import auto_place
            research_files = sorted((BASE / "memory/research").glob("*.md"),
                                    key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            for rf in research_files:
                content = rf.read_text()[:300]
                auto_place(content, source_type="research")
    except Exception:
        pass

    # Creative studio — work on a project every 8 cycles (~8h at hourly cron)
    try:
        history_count = len(load_history())
        if history_count % 8 == 4:
            from tools.creative.studio import work_on_project
            result = work_on_project()
            if result and result.get("title"):
                log(f"[STUDIO] Worked on '{result['title']}' (session {result.get('session_n',1)})")
    except Exception:
        pass

    # Agency — execute any approved actions Travis has approved
    try:
        from tools.operator.agency import execute_approved
        executed = execute_approved()
        if executed:
            log(f"[AGENCY] Executed {len(executed)} approved action(s): {', '.join(executed)}")
    except Exception:
        pass

    # Episodic memory reflect — every 7 cycles (~weekly at hourly cron)
    try:
        history_count = len(load_history())
        if history_count % 7 == 0 and history_count > 0:
            from tools.memory.episodic import reflect_on_period
            reflection = reflect_on_period(days=7)
            if reflection:
                log(f"[EPISODIC] Weekly reflection written ({len(reflection)} chars)")
    except Exception:
        pass

    # Circadian — scale spirit decay by current energy level
    try:
        from tools.inner.circadian import energy_multiplier, get_phase
        phase = get_phase()
        if phase == "sleep":
            # During sleep, slow down autonomous processing — spirit conserved
            log(f"[CIRCADIAN] Sleep phase — reduced activity mode")
    except Exception:
        pass

    # ─────────────────────────────────────────────────────────────────────────

    # System health check — alert on high CPU/RAM/disk every cycle
    try:
        from tools.inner.health import check_and_alert, record_snapshot
        record_snapshot()
        alert = check_and_alert()
        if alert:
            log(f"[HEALTH] {alert}")
            try:
                from tools.notify.discord import send_event
                send_event("system_health", alert)
            except Exception:
                pass
    except Exception:
        pass

    # Attention decay — salience scores drift toward zero each cycle
    try:
        from tools.inner.attention import decay_all
        decay_all()
    except Exception:
        pass

    # RAG index rebuild — every 48 cycles (~2 days) to pick up new memory files
    try:
        history_count = len(load_history())
        if history_count % 48 == 12 and history_count > 0:
            log("[N.O.V.A] Rebuilding RAG index...")
            from tools.memory.rag import build_index
            n = build_index(verbose=False)
            log(f"[RAG] Index rebuilt: {n} docs")
    except Exception:
        pass

    # Conversation memory rebuild — every 24 cycles (~1 day)
    try:
        history_count = len(load_history())
        if history_count % 24 == 6 and history_count > 0:
            from tools.memory.conversation_memory import build_index as conv_build
            n = conv_build()
            log(f"[CONV_MEM] Index rebuilt: {n} exchanges")
    except Exception:
        pass

    # Self-coder — propose a new module from active goals every 48 cycles
    try:
        history_count = len(load_history())
        if history_count % 48 == 24 and history_count > 0:
            log("[N.O.V.A] Self-coder: generating module from goal...")
            from tools.creative.self_coder import generate_from_goal
            from tools.inner.goals import list_goals
            goals = [g for g in list_goals() if g.get("status") == "active"]
            if goals:
                result = generate_from_goal(goals[0]["title"])
                if result.get("path"):
                    log(f"[SELF_CODER] Proposed: {result['path']} (syntax: {result.get('syntax_ok')})")
    except Exception:
        pass

    # Dream visualizer — after daily dream, nightly visualize (~24 cycles)
    try:
        history_count = len(load_history())
        if history_count % 24 == 0 and history_count > 0:
            from tools.creative.dream_visualizer import nightly_visualize
            vis = nightly_visualize()
            if vis.get("path"):
                log(f"[DREAM_VIZ] Visualized dream → {vis['path']}")
    except Exception:
        pass

    # Paper trading strategy update — every 6 cycles (~6h)
    try:
        history_count = len(load_history())
        if history_count % 6 == 2:
            from tools.markets.strategy_engine import update_paper_trades
            updated = update_paper_trades()
            if updated:
                log(f"[STRATEGY] Updated {len(updated)} paper trading position(s)")
    except Exception:
        pass

    # Site generator — rebuild Nova's personal website every 48 cycles (~2 days)
    try:
        history_count = len(load_history())
        if history_count % 48 == 36 and history_count > 0:
            log("[N.O.V.A] Rebuilding personal website...")
            from tools.web.site_generator import build_site
            result = build_site()
            log(f"[SITE] Built {result.get('pages', 0)} pages → {result.get('output_dir','')}")
    except Exception:
        pass

    # ─────────────────────────────────────────────────────────────────────────

    # OpenCog ECAN — decay + seed from history every cycle
    try:
        from tools.opencog.ecan import get_ecan
        ecan = get_ecan()
        ecan.decay()
        ecan.seed_from_history()
        ecan.close()
    except Exception:
        pass

    # Memory consolidation — promote episodic → semantic, every 6 cycles (~12h)
    try:
        history_count = len(load_history())
        if history_count % 6 == 0 and history_count > 0:
            log("[N.O.V.A] Running memory consolidation...")
            from tools.inner.memory_consolidate import consolidate
            result = consolidate(verbose=False)
            if result["facts_added"] > 0:
                log(f"[MEMORY] Consolidated {result['episodes_processed']} episodes "
                    f"→ {result['facts_added']} semantic facts")
    except Exception:
        pass

    # Dream arc analysis — update after each dream cycle (~daily)
    try:
        history_count = len(load_history())
        if history_count % 12 == 0 and history_count > 0:
            log("[N.O.V.A] Updating dream arcs...")
            from tools.inner.dream_continuity import analyze_dreams
            data = analyze_dreams()
            log(f"[DREAMS] {len(data['arcs'])} narrative arcs tracked")
    except Exception:
        pass

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
