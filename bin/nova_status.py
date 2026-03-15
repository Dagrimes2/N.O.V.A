#!/usr/bin/env python3
"""
N.O.V.A Status Dashboard

Single-command overview of Nova's complete state.
Usage: nova status
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path.home() / "Nova"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# ── Colors ────────────────────────────────────────────────────────────────────
G   = "\033[32m";  R  = "\033[31m";  C  = "\033[36m"
W   = "\033[97m";  M  = "\033[35m";  Y  = "\033[33m"
DIM = "\033[2m";   NC = "\033[0m";   B  = "\033[1m"
BG  = "\033[42m";  BR = "\033[41m"


def bar(value: float, width: int = 20, color: str = G) -> str:
    filled = int(value * width)
    return color + "█" * filled + DIM + "░" * (width - filled) + NC


def section(title: str) -> None:
    print(f"\n{B}{C}{'─' * 4} {title} {'─' * (44 - len(title))}{NC}")


def main():
    now = datetime.now()
    print(f"\n{B}{W}╔══════════════════════════════════════════════════╗")
    print(f"║          N.O.V.A  STATUS  DASHBOARD             ║")
    print(f"║          {DIM}{now.strftime('%Y-%m-%d  %H:%M:%S')}{W}                  ║")
    print(f"╚══════════════════════════════════════════════════╝{NC}")

    # ── Inner State ───────────────────────────────────────────────────────────
    section("INNER STATE")
    try:
        from tools.inner.inner_state import InnerState
        inner  = InnerState()
        snap   = inner.snapshot()
        valence = snap.get("valence", 0)
        arousal = snap.get("arousal", 0.5)
        mood    = snap.get("mood_label", "neutral")
        v_col   = G if valence > 0.2 else (R if valence < -0.2 else Y)
        print(f"  Mood:    {B}{v_col}{mood}{NC}  "
              f"valence={v_col}{valence:+.3f}{NC}  arousal={C}{arousal:.3f}{NC}")
        print(f"  Valence: {bar(max(0, (valence+1)/2), 24, v_col)}")

        needs = snap.get("needs", {})
        if needs:
            print(f"\n  {DIM}Needs:{NC}")
            for need, val in sorted(needs.items(), key=lambda x: x[1], reverse=True):
                col = R if val > 0.75 else (Y if val > 0.4 else G)
                print(f"    {need:12s} {bar(val, 16, col)} {col}{val:.2f}{NC}")
    except Exception as e:
        print(f"  {DIM}Inner state unavailable: {e}{NC}")

    # ── Network ───────────────────────────────────────────────────────────────
    section("NETWORK")
    try:
        from tools.net.network import net
        online  = net.is_online()
        pending = net.pending_count()
        col     = G if online else R
        status  = "ONLINE" if online else "OFFLINE"
        print(f"  Status:  {B}{col}{status}{NC}")
        if pending > 0:
            print(f"  Queued:  {Y}{pending} deferred tasks{NC}")
        try:
            from tools.llm.llm_cache import cache_stats
            cs = cache_stats()
            print(f"  LLM cache: {G}{cs.get('size',0)} entries{NC}  "
                  f"hits={cs.get('hits',0)}  misses={cs.get('misses',0)}")
        except Exception:
            pass
    except Exception as e:
        print(f"  {DIM}Network unavailable: {e}{NC}")

    # ── Knowledge Graph ───────────────────────────────────────────────────────
    section("KNOWLEDGE GRAPH")
    try:
        from tools.knowledge.graph import stats as _graph_stats
        gs = _graph_stats()
        print(f"  Nodes:  {G}{gs.get('nodes', 0)}{NC}   "
              f"Edges: {C}{gs.get('edges', 0)}{NC}")
        by_type = gs.get("by_type", {})
        if by_type:
            top = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:6]
            print(f"  {DIM}" + "  ".join(f"{k}={v}" for k, v in top) + NC)
    except Exception as e:
        print(f"  {DIM}Graph unavailable: {e}{NC}")

    # ── Learning ──────────────────────────────────────────────────────────────
    section("LEARNING")
    try:
        from tools.learning.outcome_tracker import learning_stats
        ls    = learning_stats()
        total = ls.get("total", 0)
        if total > 0:
            acc = ls.get("accuracy", 0)
            col = G if acc > 0.7 else (Y if acc > 0.5 else R)
            print(f"  Outcomes:  {total}  accuracy={col}{acc:.0%}{NC}  "
                  f"confirmed={G}{ls.get('confirmed',0)}{NC}  "
                  f"false_pos={R}{ls.get('false_positives',0)}{NC}")
            top_sigs = ls.get("top_signals", [])[:3]
            if top_sigs:
                sigs = ", ".join(f"{s['signal']}({s['confidence']:.0%})" for s in top_sigs)
                print(f"  Top signals: {C}{sigs}{NC}")
        else:
            print(f"  {DIM}No outcomes tracked yet. Run: nova learn mark <ID> confirmed{NC}")
    except Exception as e:
        print(f"  {DIM}Learning unavailable: {e}{NC}")

    try:
        from tools.inner.instinct import list_instincts
        instincts = list_instincts()
        if instincts:
            print(f"  Instincts: {G}{len(instincts)} learned{NC}")
        else:
            print(f"  Instincts: {DIM}none yet (emerge from confirmed outcomes){NC}")
    except Exception:
        pass

    # ── Recent Activity ───────────────────────────────────────────────────────
    section("RECENT ACTIVITY")
    hist_file = BASE / "memory/autonomous_history.json"
    try:
        history = json.loads(hist_file.read_text()) if hist_file.exists() else []
        recent  = history[-5:]
        if recent:
            for h in reversed(recent):
                ts     = h.get("timestamp", "")[:16]
                action = h.get("action", "?")
                target = h.get("target", "")[:35]
                col    = C if action == "research" else (G if action == "scan" else M)
                print(f"  {DIM}{ts}{NC}  {col}{action:8s}{NC}  {target}")
        else:
            print(f"  {DIM}No autonomous history yet.{NC}")
    except Exception:
        print(f"  {DIM}History unavailable.{NC}")

    # ── Scan Deduplication ────────────────────────────────────────────────────
    section("SCAN MEMORY")
    try:
        from tools.governance.scan_memory import stats as scan_stats, list_recent
        ss = scan_stats()
        print(f"  Targets seen: {G}{ss['total_targets']}{NC}  "
              f"Total scans: {ss['total_scans']}  "
              f"Last 24h: {ss['recent_24h']}")
        recent_scans = list_recent(hours=24)
        if recent_scans:
            for s in recent_scans[:3]:
                age = "recently"
                print(f"  {DIM}→{NC} {s['target']:35s} score={s.get('last_score',0)}")
    except Exception as e:
        print(f"  {DIM}Scan memory unavailable: {e}{NC}")

    # ── Integrity ─────────────────────────────────────────────────────────────
    section("FILE INTEGRITY")
    try:
        from tools.governance.file_integrity import verify, load_baseline
        baseline = load_baseline()
        if not baseline:
            print(f"  {Y}No baseline set. Run: nova integrity baseline{NC}")
        else:
            tampered = verify()
            if tampered:
                print(f"  {R}{B}TAMPERED: {', '.join(tampered)}{NC}")
            else:
                print(f"  {G}All {len(baseline)} protected files intact.{NC}")
    except Exception as e:
        print(f"  {DIM}Integrity check unavailable: {e}{NC}")

    # ── Simulation ────────────────────────────────────────────────────────────
    section("SIMULATION")
    try:
        from tools.simulation.world import WorldState
        world = WorldState()
        state = world._data
        loc   = state.get("location", "?")
        day   = state.get("day", 1)
        wx    = state.get("weather", "?")
        mems  = len(state.get("memories", []))
        print(f"  Day {day}  Location: {C}{loc}{NC}  Weather: {wx}  Memories: {mems}")
    except Exception as e:
        print(f"  {DIM}Simulation unavailable: {e}{NC}")

    # ── Travis Model ──────────────────────────────────────────────────────────
    section("TRAVIS MODEL")
    try:
        from tools.symbiosis.travis_model import TravisModel
        tm   = TravisModel()
        snap = tm.snapshot()
        n    = snap.get("interactions", 0)
        tone = snap.get("dominant_tone", "?")
        ints = tm.dominant_interests(3)
        print(f"  Interactions: {G}{n}{NC}  Tone: {C}{tone}{NC}")
        if ints:
            print(f"  Top interests: {M}{', '.join(ints)}{NC}")
    except Exception as e:
        print(f"  {DIM}Travis model unavailable: {e}{NC}")

    # ── Notifications ─────────────────────────────────────────────────────────
    notif_file = BASE / "memory/notifications.json"
    try:
        notifs = json.loads(notif_file.read_text()) if notif_file.exists() else []
        unread = [n for n in notifs if not n.get("read")]
        if unread:
            section("NOTIFICATIONS")
            for n in unread[-5:]:
                icon = f"{R}🔴{NC}" if n.get("priority") == "high" else "📬"
                print(f"  {icon} {Y}{n.get('title','')}{NC}")
                print(f"    {DIM}{n.get('message','')[:80]}{NC}")
    except Exception:
        pass

    # ── Storage ───────────────────────────────────────────────────────────────
    section("STORAGE")
    try:
        from tools.storage.pi_storage import disk_usage
        usage = disk_usage()
        pct   = usage.get("percent", 0)
        col   = R if pct > 85 else (Y if pct > 70 else G)
        print(f"  Disk: {bar(pct/100, 20, col)} {col}{pct:.1f}%{NC}  "
              f"free={usage.get('free_gb', 0):.1f}GB")
    except Exception as e:
        print(f"  {DIM}Storage unavailable: {e}{NC}")

    print(f"\n{DIM}{'─' * 50}{NC}")
    print(f"{DIM}nova learn mark <ID> confirmed  |  nova memory search <query>{NC}")
    print(f"{DIM}nova simulate run               |  nova integrity baseline{NC}\n")


if __name__ == "__main__":
    main()
