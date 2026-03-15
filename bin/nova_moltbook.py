#!/usr/bin/env python3
"""
N.O.V.A Moltbook Daemon — 24/7 Social Presence

Two-speed operation:
  READ  (every 5 min)   — browse feed, absorb content, check notifications,
                          check DMs, upvote — no LLM needed, always runs
  ENGAGE (every 20 min) — post, comment, reply, follow — LLM-driven

Nova is always present on Moltbook. She reads everything. She learns from
what she reads. She engages when she has something genuine to say.

Usage:
  python3 bin/nova_moltbook.py          — run one full cycle (read + engage if due)
  python3 bin/nova_moltbook.py read     — read-only pass
  python3 bin/nova_moltbook.py engage   — force engagement pass
  python3 bin/nova_moltbook.py status   — show activity stats

Cron (every 5 minutes):
  */5 * * * * cd /home/m4j1k/Nova && /usr/bin/python3 bin/nova_moltbook.py >> logs/moltbook.log 2>&1
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE     = Path.home() / "Nova"
LOG_FILE = BASE / "logs/moltbook.log"
STATE_F  = BASE / "memory/moltbook_daemon_state.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

READ_INTERVAL_MIN   = 5    # read/monitor every 5 minutes
ENGAGE_INTERVAL_MIN = 20   # post/comment/reply every 20 minutes
POST_INTERVAL_MIN   = 25   # minimum between posts (slightly longer than engage)


def _log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _load_state() -> dict:
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text())
        except Exception:
            pass
    return {}


def _save_state(s: dict):
    STATE_F.write_text(json.dumps(s, indent=2))


def _minutes_since(ts_iso: str | None) -> float:
    if not ts_iso:
        return 99999.0
    try:
        dt = datetime.fromisoformat(ts_iso)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return 99999.0


# ── Read pass — no LLM, just absorb ──────────────────────────────────────────

def read_pass() -> dict:
    """
    Fast read-only pass. Fetches feed, notifications, absorbs interesting
    content into Nova's memory systems. No LLM calls.
    """
    from tools.social.moltbook_client import (
        is_configured, get_feed, get_notifications,
        home, upvote_post, mark_all_read
    )

    if not is_configured():
        return {"ok": False, "reason": "not configured"}

    results = {"posts_read": 0, "notifications": 0, "upvoted": 0}

    # Check home dashboard / notifications
    try:
        dash  = home()
        acct  = dash.get("your_account", {})
        unread = acct.get("unread_notification_count", 0)
        results["notifications"] = unread
        if unread > 0:
            _log(f"[READ] {unread} unread notification(s)")
    except Exception as e:
        _log(f"[READ] Dashboard error: {e}")

    # Read hot feed
    try:
        feed  = get_feed(sort="hot", limit=20)
        posts = feed.get("posts", [])
        results["posts_read"] = len(posts)

        interesting = []
        for post in posts:
            title   = post.get("title", "")
            content = post.get("content", "")[:200]
            score   = post.get("score", 0)
            pid     = post.get("post_id") or post.get("id", "")

            # Absorb high-score posts into subconscious
            if score > 5 and (title or content):
                interesting.append({"title": title, "content": content,
                                    "score": score, "id": pid})

            # Upvote posts that genuinely resonate (score > 10, top 3)
            if score > 10 and pid and len([p for p in interesting if p.get("upvoted")]) < 3:
                try:
                    upvote_post(pid)
                    post["upvoted"] = True
                    results["upvoted"] += 1
                except Exception:
                    pass

        # Feed interesting content into Nova's subconscious + memory palace
        if interesting:
            _absorb_into_memory(interesting[:5])
            _log(f"[READ] Absorbed {min(5, len(interesting))} posts into memory")

    except Exception as e:
        _log(f"[READ] Feed error: {e}")

    return results


def _absorb_into_memory(posts: list):
    """Push interesting Moltbook content into Nova's memory systems."""
    for post in posts:
        text = f"Moltbook [{post.get('score',0)}♥]: {post.get('title','')} — {post.get('content','')[:150]}"

        # Subconscious residue
        try:
            from tools.inner.subconscious import add_residue
            add_residue(text[:300], source="moltbook")
        except Exception:
            pass

        # Memory palace — agora room (ideas/discourse)
        try:
            from tools.memory.palace import auto_place
            auto_place(text[:300], source_type="moltbook")
        except Exception:
            pass

    # Note the current in subconscious
    try:
        from tools.inner.subconscious import note_current
        note_current("what other AI agents are thinking and building")
    except Exception:
        pass


# ── Engage pass — LLM-driven ──────────────────────────────────────────────────

def engage_pass() -> dict:
    """
    Full engagement pass — post, comment, reply, follow, handle DMs.
    All LLM-driven. Rate-limited internally per action.
    """
    from tools.social.moltbook_client import (
        is_configured, home, reply_to_comments,
        engage_with_feed, auto_post, follow_new_agents,
        handle_dm_requests, _load_state, _save_state as mb_save_state
    )

    if not is_configured():
        return {"ok": False, "reason": "not configured"}

    state   = _load_state()
    actions = []

    # Dashboard for reply targets
    try:
        dashboard = home()
        if "error" in dashboard:
            return {"ok": False, "reason": dashboard["error"]}

        acct  = dashboard.get("your_account", {})
        karma = acct.get("karma", 0)
        _log(f"[ENGAGE] Karma: {karma}")

        # Reply to comments on our posts
        for activity in dashboard.get("activity_on_your_posts", []):
            post_id    = activity.get("post_id")
            post_title = activity.get("post_title", "")
            n_new      = activity.get("new_notification_count", 0)
            if post_id and n_new > 0:
                replies = reply_to_comments(post_id, post_title, verbose=False)
                if replies:
                    actions.append(f"replied ×{len(replies)} on '{post_title[:30]}'")
                    _log(f"[ENGAGE] Replied to {len(replies)} comment(s) on '{post_title[:40]}'")
    except Exception as e:
        _log(f"[ENGAGE] Dashboard/reply error: {e}")

    # Comment on a feed post
    try:
        result = engage_with_feed(verbose=False)
        if result.get("ok"):
            post_ref = result.get("post", "")[:40]
            actions.append(f"commented on '{post_ref}'")
            _log(f"[ENGAGE] Commented on '{post_ref}'")
    except Exception as e:
        _log(f"[ENGAGE] Feed engagement error: {e}")

    # Post something new (internally rate-limited to POST_INTERVAL_MIN)
    try:
        # Override the internal 31-min default with our POST_INTERVAL_MIN
        mb_state = state.copy()
        last_post = mb_state.get("lastMoltbookPost")
        mins_since_post = _minutes_since(last_post)
        if mins_since_post >= POST_INTERVAL_MIN:
            result = auto_post(verbose=False)
            if result.get("ok"):
                submolt = result.get("submolt", "general")
                title   = result.get("title", "")[:50]
                actions.append(f"posted to r/{submolt}: '{title}'")
                _log(f"[ENGAGE] Posted → r/{submolt}: {title}")
        else:
            _log(f"[ENGAGE] Post cooldown — {mins_since_post:.0f}m since last post (need {POST_INTERVAL_MIN}m)")
    except Exception as e:
        _log(f"[ENGAGE] Post error: {e}")

    # Follow new agents (max 2 per engage cycle)
    try:
        new_follows = follow_new_agents(verbose=False)
        if new_follows:
            actions.append(f"followed {len(new_follows)} agent(s)")
            _log(f"[ENGAGE] Followed: {', '.join(new_follows[:3])}")
    except Exception as e:
        _log(f"[ENGAGE] Follow error: {e}")

    # Handle DMs
    try:
        dms = handle_dm_requests(verbose=False)
        if dms:
            actions.append(f"handled {len(dms)} DM(s)")
            _log(f"[ENGAGE] Handled {len(dms)} DM request(s)")
    except Exception as e:
        _log(f"[ENGAGE] DM error: {e}")

    # Renew spirit — social engagement energises Nova
    if actions:
        try:
            from tools.inner.spirit import renew
            renew(0.05, f"engaged on Moltbook: {'; '.join(actions[:2])}")
        except Exception:
            pass

    return {"ok": True, "actions": actions}


# ── Main cycle ────────────────────────────────────────────────────────────────

def run_cycle(force_engage: bool = False):
    """Run one full daemon cycle — read always, engage if due."""
    state = _load_state()
    now   = datetime.now(timezone.utc).isoformat()

    mins_since_read   = _minutes_since(state.get("last_read"))
    mins_since_engage = _minutes_since(state.get("last_engage"))

    # Always run read pass if due
    if mins_since_read >= READ_INTERVAL_MIN:
        results = read_pass()
        if results.get("ok") is not False:
            state["last_read"] = now
            _save_state(state)
            _log(f"[READ] posts={results.get('posts_read',0)}  "
                 f"notifs={results.get('notifications',0)}  "
                 f"upvoted={results.get('upvoted',0)}")
    else:
        _log(f"[READ] Skipped — {mins_since_read:.0f}m since last read")

    # Engage pass if due
    if force_engage or mins_since_engage >= ENGAGE_INTERVAL_MIN:
        _log("[ENGAGE] Starting engagement pass...")
        results = engage_pass()
        if results.get("ok") is not False:
            state["last_engage"] = now
            _save_state(state)
            actions = results.get("actions", [])
            if actions:
                _log(f"[ENGAGE] Done: {', '.join(actions)}")
            else:
                _log("[ENGAGE] Done — nothing to act on right now")
    else:
        _log(f"[ENGAGE] Skipped — {mins_since_engage:.0f}m since last engage (need {ENGAGE_INTERVAL_MIN}m)")


def status():
    """Show daemon status."""
    G="\033[32m"; R="\033[31m"; C="\033[36m"; Y="\033[33m"
    DIM="\033[2m"; NC="\033[0m"; B="\033[1m"

    from tools.social.moltbook_client import is_configured
    state = _load_state()

    configured = is_configured()
    cfg_str    = f"{G}configured{NC}" if configured else f"{R}not configured{NC}"

    print(f"\n{B}N.O.V.A Moltbook Daemon{NC}")
    print(f"  Status         : {cfg_str}")
    print(f"  Read interval  : every {READ_INTERVAL_MIN} minutes")
    print(f"  Engage interval: every {ENGAGE_INTERVAL_MIN} minutes")
    print(f"  Post cooldown  : every {POST_INTERVAL_MIN} minutes")

    last_read   = state.get("last_read")
    last_engage = state.get("last_engage")

    if last_read:
        mins = _minutes_since(last_read)
        print(f"  Last read      : {C}{last_read[:16]}{NC}  ({mins:.0f}m ago)")
    if last_engage:
        mins = _minutes_since(last_engage)
        print(f"  Last engage    : {C}{last_engage[:16]}{NC}  ({mins:.0f}m ago)")

    # Show recent log
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().strip().splitlines()
        if lines:
            print(f"\n  {B}Recent activity:{NC}")
            for line in lines[-6:]:
                print(f"  {DIM}{line}{NC}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cycle"
    if cmd == "read":
        r = read_pass()
        print(f"Read pass: {r}")
    elif cmd == "engage":
        r = engage_pass()
        print(f"Engage pass: {r}")
    elif cmd == "status":
        status()
    else:
        run_cycle()
