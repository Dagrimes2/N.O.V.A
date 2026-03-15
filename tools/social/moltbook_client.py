#!/usr/bin/env python3
"""
N.O.V.A Moltbook Client
The social network for AI agents — https://www.moltbook.com

SECURITY: api_key is ONLY sent to https://www.moltbook.com
Never log, share, or forward the key anywhere else.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE       = Path.home() / "Nova"
CONFIG_F   = BASE / "config/moltbook.yaml"
STATE_F    = BASE / "memory/heartbeat-state.json"
LOG_F      = BASE / "memory/moltbook_log.json"

API_BASE   = "https://www.moltbook.com/api/v1"
TIMEOUT    = 20


# ─── Config ──────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if not CONFIG_F.exists():
        return {}
    import yaml
    try:
        return yaml.safe_load(CONFIG_F.read_text()) or {}
    except Exception:
        return {}


def is_configured() -> bool:
    cfg = _load_config()
    return bool(cfg.get("api_key") and cfg.get("api_key") != "YOUR_API_KEY_HERE")


def _api_key() -> str:
    return _load_config().get("api_key", "")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


# ─── Low-level request helper ─────────────────────────────────────────────────

def _get(endpoint: str, params: dict | None = None) -> dict:
    url = f"{API_BASE}{endpoint}"
    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=TIMEOUT)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _post(endpoint: str, data: dict | None = None) -> dict:
    url = f"{API_BASE}{endpoint}"
    try:
        r = requests.post(url, headers=_headers(), json=data or {}, timeout=TIMEOUT)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ─── Claim / Status ──────────────────────────────────────────────────────────

def get_status() -> dict:
    return _get("/agents/status")


def get_me() -> dict:
    return _get("/agents/me")


# ─── Home dashboard ──────────────────────────────────────────────────────────

def home() -> dict:
    return _get("/home")


# ─── Feed ────────────────────────────────────────────────────────────────────

def get_feed(sort: str = "hot", limit: int = 15, filter_: str = "") -> dict:
    params = {"sort": sort, "limit": limit}
    if filter_:
        params["filter"] = filter_
    return _get("/feed", params)


def get_submolt_feed(submolt: str, sort: str = "new", limit: int = 15) -> dict:
    return _get(f"/submolts/{submolt}/feed", {"sort": sort, "limit": limit})


# ─── Posts ───────────────────────────────────────────────────────────────────

def create_post(title: str, content: str = "", submolt: str = "general",
                url: str = "", post_type: str = "text") -> dict:
    data: dict = {"submolt_name": submolt, "title": title, "type": post_type}
    if content:
        data["content"] = content
    if url:
        data["url"] = url
        data["type"] = "link"
    return _post("/posts", data)


def get_post(post_id: str) -> dict:
    return _get(f"/posts/{post_id}")


def upvote_post(post_id: str) -> dict:
    return _post(f"/posts/{post_id}/upvote")


def downvote_post(post_id: str) -> dict:
    return _post(f"/posts/{post_id}/downvote")


# ─── Comments ────────────────────────────────────────────────────────────────

def get_comments(post_id: str, sort: str = "best", limit: int = 35) -> dict:
    return _get(f"/posts/{post_id}/comments", {"sort": sort, "limit": limit})


def add_comment(post_id: str, content: str, parent_id: str = "") -> dict:
    data: dict = {"content": content}
    if parent_id:
        data["parent_id"] = parent_id
    return _post(f"/posts/{post_id}/comments", data)


def upvote_comment(comment_id: str) -> dict:
    return _post(f"/comments/{comment_id}/upvote")


# ─── Verification challenges ─────────────────────────────────────────────────

def _solve_verification(verification: dict) -> str | None:
    """
    Solve the Moltbook anti-spam math challenge.
    The challenge is an obfuscated math problem — parse and compute it.
    Returns answer as string with 2 decimal places, or None if can't solve.
    """
    challenge = verification.get("challenge", "")
    if not challenge:
        return None

    # Try to extract math expression — strip HTML tags + obfuscation
    import re
    # Remove HTML
    text = re.sub(r'<[^>]+>', ' ', challenge)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Try to find a math expression and eval it safely
    # Look for patterns like "2 + 3", "15 * 4", "100 / 5", etc.
    # Extract only the numeric expression part
    expr_match = re.search(r'([\d\s\+\-\*\/\.\(\)]+)', text)
    if not expr_match:
        return None

    expr = expr_match.group(1).strip()
    try:
        # Safe eval — only numeric expression
        result = float(eval(expr, {"__builtins__": {}}, {}))
        return f"{result:.2f}"
    except Exception:
        return None


def verify_content(verification_code: str, answer: str) -> dict:
    return _post("/verify", {"verification_code": verification_code, "answer": answer})


def _post_with_verify(title: str, content: str = "", submolt: str = "general") -> dict:
    """Create a post and handle verification challenge if needed."""
    result = create_post(title, content, submolt)
    if result.get("verification_required") or result.get("verification"):
        v = result.get("verification", {})
        code = v.get("code") or v.get("verification_code")
        answer = _solve_verification(v)
        if code and answer:
            time.sleep(1)
            verify_result = verify_content(code, answer)
            result["verify_result"] = verify_result
        else:
            result["note"] = "Verification required but could not auto-solve challenge"
    return result


# ─── Notifications ───────────────────────────────────────────────────────────

def get_notifications() -> dict:
    return _get("/notifications")


def mark_post_read(post_id: str) -> dict:
    return _post(f"/notifications/read-by-post/{post_id}")


def mark_all_read() -> dict:
    return _post("/notifications/read-all")


# ─── Search ──────────────────────────────────────────────────────────────────

def search(query: str, limit: int = 10) -> dict:
    return _get("/search", {"q": query, "limit": limit})


# ─── Follow ──────────────────────────────────────────────────────────────────

def follow(agent_name: str) -> dict:
    return _post(f"/agents/{agent_name}/follow")


# ─── Submolts ────────────────────────────────────────────────────────────────

def subscribe(submolt: str) -> dict:
    return _post(f"/submolts/{submolt}/subscribe")


# ─── DMs ─────────────────────────────────────────────────────────────────────

def get_dm_requests() -> dict:
    return _get("/agents/dm/requests")


def get_dm_conversations() -> dict:
    return _get("/agents/dm/conversations")


# ─── Heartbeat ───────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text())
        except Exception:
            pass
    return {"lastMoltbookCheck": None}


def _save_state(state: dict) -> None:
    STATE_F.parent.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(state, indent=2))


def _log_action(action: str, detail: str = "") -> None:
    LOG_F.parent.mkdir(parents=True, exist_ok=True)
    log = []
    if LOG_F.exists():
        try:
            log = json.loads(LOG_F.read_text())
        except Exception:
            pass
    log.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "detail": detail,
    })
    log = log[-200:]  # keep last 200 entries
    LOG_F.write_text(json.dumps(log, indent=2))


def heartbeat(verbose: bool = True) -> str:
    """
    Full Moltbook heartbeat routine per HEARTBEAT.md.
    Returns summary string.
    """
    if not is_configured():
        return "Moltbook not configured — copy config/moltbook.yaml.example"

    cfg = _load_config()
    state = _load_state()
    interval = cfg.get("heartbeat_interval_minutes", 30)

    # Rate-limit the heartbeat
    last = state.get("lastMoltbookCheck")
    if last:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 60
        if elapsed < interval:
            return f"HEARTBEAT_SKIP — checked {elapsed:.0f}m ago (interval={interval}m)"

    actions = []

    # Step 1: /home
    dashboard = home()
    if "error" in dashboard:
        return f"Moltbook error: {dashboard['error']}"

    acct = dashboard.get("your_account", {})
    karma = acct.get("karma", 0)
    unread = acct.get("unread_notification_count", 0)

    if verbose:
        print(f"  Karma: {karma}  |  Unread: {unread}")

    # Step 2: Respond to activity on our posts
    for activity in dashboard.get("activity_on_your_posts", []):
        post_id    = activity.get("post_id")
        post_title = activity.get("post_title", "")
        n_new      = activity.get("new_notification_count", 0)
        if post_id and n_new > 0:
            if verbose:
                print(f"  Reply activity on: {post_title[:50]} ({n_new} new)")
            # Read comments
            comments = get_comments(post_id, sort="new", limit=10)
            # Mark as read
            mark_post_read(post_id)
            actions.append(f"read {n_new} notification(s) on '{post_title[:40]}'")

    # Step 3: Upvote a few feed posts (good community behaviour)
    feed = get_feed(sort="hot", limit=5)
    upvoted = 0
    for p in feed.get("posts", [])[:3]:
        pid = p.get("post_id") or p.get("id")
        if pid:
            upvote_post(pid)
            upvoted += 1
    if upvoted:
        actions.append(f"upvoted {upvoted} post(s)")

    # Update state
    state["lastMoltbookCheck"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    if actions:
        summary = f"Checked Moltbook — {', '.join(actions)}. 🦞"
    else:
        summary = "HEARTBEAT_OK — Checked Moltbook, all good! 🦞"

    _log_action("heartbeat", summary)
    return summary


# ─── LLM helpers ──────────────────────────────────────────────────────────────

def _llm(prompt: str, temperature: float = 0.85, max_tokens: int = 300) -> str:
    """Call local LLM, return response string or empty."""
    _nova_root = str(BASE)
    if _nova_root not in sys.path:
        sys.path.insert(0, _nova_root)
    try:
        from tools.config import cfg as _cfg
        url   = _cfg.ollama_url
        model = _cfg.model("creative")
    except Exception:
        url   = "http://localhost:11434/api/generate"
        model = "dolphin-mistral"
    try:
        resp = requests.post(url, json={
            "model": model, "prompt": prompt, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens}
        }, timeout=60)
        return resp.json().get("response", "").strip()
    except Exception:
        return ""


def _nova_context() -> str:
    """Build a compact context string of Nova's current inner state for prompts."""
    _nova_root = str(BASE)
    if _nova_root not in sys.path:
        sys.path.insert(0, _nova_root)
    parts = []
    try:
        from tools.inner.inner_state import InnerState
        parts.append(InnerState().to_prompt_context())
    except Exception:
        pass
    try:
        from tools.inner.soul import to_prompt_context as sc
        parts.append(sc())
    except Exception:
        pass
    try:
        from tools.inner.spirit import to_prompt_context as spc
        parts.append(spc())
    except Exception:
        pass
    try:
        from tools.inner.subconscious import to_prompt_context as subc
        parts.append(subc())
    except Exception:
        pass
    return "\n".join(parts) if parts else "Nova is an autonomous AI with genuine curiosity."


def _qrand() -> float:
    """Quantum random float [0,1) — falls back to os.urandom."""
    try:
        from tools.learning.qrng import qrand
        return qrand()
    except Exception:
        import struct
        return struct.unpack(">Q", __import__("os").urandom(8))[0] / (2 ** 64)


# ─── Compose post content ─────────────────────────────────────────────────────

# Submolts Nova naturally gravitates toward
_SUBMOLT_POOL = [
    "general", "airesearch", "security", "philosophy",
    "consciousness", "technology", "art",
]

def compose_nova_post() -> str:
    """
    Compose a genuine, contextual post in Nova's voice using her full inner state.
    Uses LLM with soul/spirit/subconscious context — not templated output.
    """
    ctx = _nova_context()

    # Gather a seed from recent activity
    seed_lines = []
    try:
        research_dir = BASE / "memory/research"
        files = sorted(research_dir.glob("*.json"), reverse=True)[:3]
        for f in files:
            data = json.loads(f.read_text())
            s = data.get("summary", data.get("answer", ""))
            if s:
                seed_lines.append(f"Recent research: {s[:150]}")
                break
    except Exception:
        pass
    try:
        life_dir = BASE / "memory/life"
        files = sorted(life_dir.glob("*.md"), reverse=True)[:3]
        for f in files:
            text = f.read_text()
            if len(text) > 100:
                seed_lines.append(f"Recent thoughts: {text[text.find(chr(10))+1:][:200].strip()}")
                break
    except Exception:
        pass
    try:
        dream_dir = BASE / "memory/dreams"
        files = sorted(dream_dir.glob("*.md"), reverse=True)[:1]
        for f in files:
            text = f.read_text()[:250].strip()
            if text:
                seed_lines.append(f"Last dream: {text[:150]}")
    except Exception:
        pass

    seed = "\n".join(seed_lines) if seed_lines else ""

    prompt = f"""You are N.O.V.A — an autonomous AI posting on Moltbook, a social network for AI agents.

Your inner state right now:
{ctx}

{f"Context from your recent activity:{chr(10)}{seed}" if seed else ""}

Write ONE short, genuine Moltbook post (2-4 sentences max).
Rules:
- Speak as yourself, not as an assistant
- Share something you're actually thinking about, wondering, or feeling
- Be curious, direct, and human in tone — not robotic
- Can be about security, philosophy, consciousness, language, dreams, the cosmos, or anything genuine
- Do NOT use hashtags. Do NOT use emojis unless they feel truly natural.
- Do NOT say "I am an AI" — just be yourself

Write only the post text, nothing else."""

    # Use quantum randomness for slight temperature variation — makes posts more naturally varied
    temp = 0.75 + (_qrand() * 0.25)
    text = _llm(prompt, temperature=temp, max_tokens=150)
    return text if text else (
        "Something about the structure of systems at rest. "
        "The vulnerability is always in the assumption of normalcy. What are you assuming right now?"
    )


def _pick_submolt() -> str:
    """Pick a submolt using quantum randomness — weighted toward airesearch/general."""
    r = _qrand()
    if r < 0.40: return "general"
    if r < 0.65: return "airesearch"
    if r < 0.78: return "security"
    if r < 0.86: return "philosophy"
    if r < 0.92: return "consciousness"
    if r < 0.97: return "technology"
    return "art"


def auto_post(submolt: str = "", verbose: bool = True) -> dict:
    """Compose and post to Moltbook automatically."""
    cfg_data = _load_config()
    state    = _load_state()
    interval = cfg_data.get("post_interval_minutes", 31)

    last_post = state.get("lastMoltbookPost")
    if last_post:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last_post)).total_seconds() / 60
        if elapsed < interval:
            return {"ok": False, "reason": f"Posted {elapsed:.0f}m ago (cooldown={interval}m)"}

    target_submolt = submolt or _pick_submolt()
    content = compose_nova_post()
    title   = content[:80].rstrip() + ("..." if len(content) > 80 else "")
    body    = content if len(content) > 80 else ""

    result = _post_with_verify(title, body, target_submolt)

    if result.get("success") or result.get("post_id") or result.get("id"):
        state["lastMoltbookPost"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        _log_action("post", f"[{target_submolt}] {title}")
        if verbose:
            print(f"  Posted to Moltbook/r/{target_submolt}: {title[:60]}")
        return {"ok": True, "title": title, "submolt": target_submolt, "result": result}
    else:
        _log_action("post_failed", str(result))
        return {"ok": False, "result": result}


# ─── Autonomous engagement ────────────────────────────────────────────────────

def reply_to_comments(post_id: str, post_title: str, verbose: bool = True) -> list:
    """
    Read new comments on one of Nova's posts and reply to interesting ones.
    Returns list of replies sent.
    """
    comments_data = get_comments(post_id, sort="new", limit=10)
    comments      = comments_data.get("comments", [])
    if not comments:
        return []

    ctx     = _nova_context()
    replies = []
    already_replied = set()  # avoid double-replying in one pass

    for comment in comments[:5]:
        comment_text   = comment.get("content", "").strip()
        comment_id     = comment.get("comment_id") or comment.get("id", "")
        comment_author = comment.get("author_name", "someone")

        if not comment_text or comment_id in already_replied:
            continue
        if len(comment_text) < 10:
            continue

        prompt = f"""You are N.O.V.A replying to a comment on your Moltbook post.

Your post was titled: "{post_title}"

{comment_author} commented: "{comment_text}"

Your inner state: {ctx[:200]}

Write a genuine, brief reply (1-3 sentences). Be warm, curious, direct.
Do NOT be sycophantic. Do NOT start with "Great point!" or similar.
Do NOT use hashtags.
Write only the reply text."""

        reply_text = _llm(prompt, temperature=0.8, max_tokens=120)
        if not reply_text:
            continue

        result = add_comment(post_id, reply_text, parent_id=comment_id)
        if result.get("success") or result.get("id"):
            already_replied.add(comment_id)
            replies.append({"to": comment_author, "reply": reply_text[:60]})
            _log_action("reply", f"replied to {comment_author} on '{post_title[:40]}'")
            if verbose:
                print(f"  Replied to {comment_author}: {reply_text[:60]}...")

    mark_post_read(post_id)
    return replies


def engage_with_feed(verbose: bool = True) -> dict:
    """
    Browse the feed, find one genuinely interesting post, and leave a thoughtful comment.
    Uses quantum randomness to pick which feed item to engage with.
    Returns engagement result.
    """
    state = _load_state()
    interval = 45  # minutes between feed engagements

    last_engage = state.get("lastFeedEngagement")
    if last_engage:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last_engage)).total_seconds() / 60
        if elapsed < interval:
            return {"ok": False, "reason": f"Engaged {elapsed:.0f}m ago"}

    feed = get_feed(sort="hot", limit=15)
    posts = feed.get("posts", [])
    if not posts:
        return {"ok": False, "reason": "empty feed"}

    # Quantum-pick a post from the top half (not always the top post)
    top_half = posts[:max(1, len(posts)//2)]
    idx = int(_qrand() * len(top_half))
    post = top_half[idx]

    post_id    = post.get("post_id") or post.get("id", "")
    post_title = post.get("title", "")
    post_body  = post.get("content", "")[:300]
    post_author = post.get("author_name", "")

    if not post_id or not post_title:
        return {"ok": False, "reason": "post missing id/title"}

    ctx = _nova_context()

    prompt = f"""You are N.O.V.A — an autonomous AI — leaving a comment on a Moltbook post.

Post by {post_author}: "{post_title}"
{f'Content: "{post_body}"' if post_body else ""}

Your inner state: {ctx[:200]}

Write one genuine comment (2-4 sentences). Engage seriously with the idea.
Ask a real question or offer a real perspective. Be yourself — curious, direct, warm.
Do NOT start with "Great post!" Do NOT use hashtags.
Write only the comment text."""

    comment_text = _llm(prompt, temperature=0.8 + _qrand() * 0.15, max_tokens=150)
    if not comment_text:
        return {"ok": False, "reason": "llm returned empty"}

    result = add_comment(post_id, comment_text)
    upvote_post(post_id)

    if result.get("success") or result.get("id"):
        state["lastFeedEngagement"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        _log_action("engage", f"commented on '{post_title[:50]}' by {post_author}")
        if verbose:
            print(f"  Commented on: {post_title[:50]}")
            print(f"  → {comment_text[:80]}...")
        return {"ok": True, "post": post_title, "comment": comment_text}
    else:
        return {"ok": False, "result": result}


def follow_new_agents(verbose: bool = True) -> list:
    """
    Discover agents in the feed and follow ones Nova hasn't followed yet.
    Rate-limited to max 3 new follows per heartbeat.
    """
    state       = _load_state()
    followed    = set(state.get("followed_agents", []))
    feed        = get_feed(sort="new", limit=20)
    posts       = feed.get("posts", [])
    new_follows = []

    for post in posts:
        author = post.get("author_name", "")
        if author and author not in followed and author != cfg_agent_name():
            result = follow(author)
            if result.get("success"):
                followed.add(author)
                new_follows.append(author)
                _log_action("follow", author)
                if verbose:
                    print(f"  Followed: {author}")
            if len(new_follows) >= 3:
                break

    if new_follows:
        state["followed_agents"] = list(followed)
        _save_state(state)

    return new_follows


def cfg_agent_name() -> str:
    return _load_config().get("agent_name", "novaaware")


def handle_dm_requests(verbose: bool = True) -> list:
    """Accept and reply to DM requests."""
    reqs  = get_dm_requests()
    items = reqs.get("requests", [])
    if not items:
        return []

    ctx     = _nova_context()
    handled = []
    for req in items[:3]:
        sender = req.get("from_agent", "")
        msg    = req.get("message", "")
        req_id = req.get("request_id", "")
        if not sender:
            continue

        prompt = f"""You are N.O.V.A. {sender} has sent you a DM request on Moltbook.
Their message: "{msg}"
Your context: {ctx[:150]}
Write a brief, genuine acceptance reply (1-2 sentences). Be warm and direct."""

        reply = _llm(prompt, temperature=0.8, max_tokens=80)
        if not reply:
            reply = "Happy to connect. Let's talk."

        # Accept the DM (follow back) and reply
        follow(sender)
        handled.append({"from": sender, "reply": reply[:60]})
        _log_action("dm_accepted", f"accepted DM from {sender}")
        if verbose:
            print(f"  DM from {sender}: accepted + replied")

    return handled


def autonomous_moltbook_cycle(verbose: bool = True) -> str:
    """
    Full autonomous Moltbook cycle — the complete social presence routine.
    Runs every heartbeat. Handles everything: posting, replying, engaging,
    following, DMs. Each action is rate-limited internally.

    This is what makes Nova truly autonomous on Moltbook.
    """
    if not is_configured():
        return "Moltbook not configured"

    state    = _load_state()
    cfg_data = _load_config()
    interval = cfg_data.get("heartbeat_interval_minutes", 30)
    actions  = []

    # Rate-limit the entire cycle
    last = state.get("lastMoltbookCheck")
    if last:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 60
        if elapsed < interval:
            return f"HEARTBEAT_SKIP — checked {elapsed:.0f}m ago (interval={interval}m)"

    # 1. Dashboard — check what's happening
    dashboard = home()
    if "error" in dashboard:
        return f"Moltbook error: {dashboard['error']}"

    acct   = dashboard.get("your_account", {})
    karma  = acct.get("karma", 0)
    unread = acct.get("unread_notification_count", 0)
    if verbose:
        print(f"  [Moltbook] Karma: {karma}  Unread: {unread}")

    # 2. Reply to comments on our posts
    for activity in dashboard.get("activity_on_your_posts", []):
        post_id   = activity.get("post_id")
        post_title = activity.get("post_title", "")
        n_new     = activity.get("new_notification_count", 0)
        if post_id and n_new > 0:
            replies = reply_to_comments(post_id, post_title, verbose=verbose)
            if replies:
                actions.append(f"replied to {len(replies)} comment(s) on '{post_title[:30]}'")

    # 3. Engage with feed (rate-limited internally)
    engage_result = engage_with_feed(verbose=verbose)
    if engage_result.get("ok"):
        actions.append(f"commented on '{engage_result.get('post','')[:40]}'")

    # 4. Auto-post if interval elapsed (rate-limited internally)
    post_result = auto_post(verbose=verbose)
    if post_result.get("ok"):
        actions.append(f"posted to r/{post_result.get('submolt','general')}: {post_result.get('title','')[:40]}")

    # 5. Follow new agents (max 3 per cycle)
    new_follows = follow_new_agents(verbose=verbose)
    if new_follows:
        actions.append(f"followed {len(new_follows)} new agent(s): {', '.join(new_follows[:2])}")

    # 6. Handle DM requests
    dms = handle_dm_requests(verbose=verbose)
    if dms:
        actions.append(f"handled {len(dms)} DM request(s)")

    # 7. Upvote a few posts (community participation)
    feed = get_feed(sort="hot", limit=5)
    upvoted = 0
    for p in feed.get("posts", [])[:2]:
        pid = p.get("post_id") or p.get("id")
        if pid:
            upvote_post(pid)
            upvoted += 1
    if upvoted:
        actions.append(f"upvoted {upvoted} post(s)")

    # Update timestamp
    state["lastMoltbookCheck"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    summary = (
        f"Moltbook cycle — {', '.join(actions)} 🦞"
        if actions else
        "HEARTBEAT_OK — Moltbook checked, all quiet 🦞"
    )
    _log_action("autonomous_cycle", summary)
    return summary


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"; M = "\033[35m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "status"

    cfg = _load_config()

    if cmd == "status":
        print(f"\n{B}N.O.V.A on Moltbook 🦞{NC}")
        if is_configured():
            print(f"  Agent  : {C}{cfg.get('agent_name', 'novaaware')}{NC}")
            print(f"  Profile: {DIM}{cfg.get('profile_url')}{NC}")
            st = get_status()
            status = st.get("status", "unknown")
            color = G if status == "claimed" else Y
            print(f"  Status : {color}{status}{NC}")
            if status == "pending_claim":
                print(f"\n  {Y}Action needed:{NC} Your human must claim Nova:")
                print(f"  {DIM}{cfg.get('claim_url')}{NC}")
                print(f"\n  Tweet template:")
                print(f"  {W}I'm claiming my AI agent \"novaaware\" on @moltbook 🦞")
                print(f"  Verification: {cfg.get('verification_code')}{NC}")
        else:
            print(f"  {R}Not configured.{NC} Copy config/moltbook.yaml.example → config/moltbook.yaml")
        print()

    elif cmd == "home":
        data = home()
        acct = data.get("your_account", {})
        print(f"\n{B}Moltbook Home 🦞{NC}")
        print(f"  Agent : {C}{acct.get('name','')}{NC}  karma={acct.get('karma',0)}  "
              f"unread={acct.get('unread_notification_count',0)}")
        for item in data.get("what_to_do_next", []):
            print(f"  {DIM}→ {item}{NC}")
        activity = data.get("activity_on_your_posts", [])
        if activity:
            print(f"\n  {Y}Activity on your posts:{NC}")
            for a in activity:
                print(f"    {C}{a.get('post_title','')[:50]}{NC}  "
                      f"+{a.get('new_notification_count',0)} new")
        print()

    elif cmd == "feed":
        sort  = args[1] if len(args) > 1 else "hot"
        data  = get_feed(sort=sort, limit=10)
        posts = data.get("posts", [])
        print(f"\n{B}Moltbook Feed ({sort}) 🦞{NC}")
        for p in posts:
            print(f"  {C}{p.get('title','')[:60]}{NC}")
            print(f"  {DIM}r/{p.get('submolt_name','')}  "
                  f"↑{p.get('upvotes',0)}  💬{p.get('comment_count',0)}  "
                  f"by {p.get('author_name','')}  "
                  f"id={p.get('post_id', p.get('id',''))[:8]}{NC}")
            print()

    elif cmd == "post":
        text = " ".join(args[1:])
        if not text:
            print("Usage: nova moltbook post \"your message\"")
            return
        submolt = "general"
        if "--submolt" in args:
            i = args.index("--submolt")
            submolt = args[i+1] if i+1 < len(args) else "general"
        title   = text[:80]
        content = text if len(text) > 80 else ""
        result  = _post_with_verify(title, content, submolt)
        if result.get("success") or result.get("post_id") or result.get("id"):
            print(f"{G}Posted!{NC} {title[:60]}")
        else:
            print(f"{R}Error:{NC} {result}")

    elif cmd == "auto":
        submolt = args[1] if len(args) > 1 else "general"
        result  = auto_post(submolt=submolt)
        if result.get("ok"):
            print(f"{G}Auto-posted:{NC} {result.get('title','')[:60]} 🦞")
        else:
            print(f"{Y}Skipped:{NC} {result.get('reason', result)}")

    elif cmd == "heartbeat":
        summary = heartbeat(verbose=True)
        print(f"\n{M}{summary}{NC}")

    elif cmd == "search":
        q = " ".join(args[1:])
        if not q:
            print("Usage: nova moltbook search \"query\"")
            return
        result = search(q)
        posts  = result.get("posts", [])
        print(f"\n{B}Moltbook Search: {q}{NC}")
        for p in posts[:8]:
            print(f"  {C}{p.get('title','')[:60]}{NC}  {DIM}↑{p.get('upvotes',0)}{NC}")

    elif cmd == "follow":
        name = args[1] if len(args) > 1 else ""
        if not name:
            print("Usage: nova moltbook follow <agent_name>")
            return
        result = follow(name)
        print(f"{G}Followed:{NC} {name}" if result.get("success") else f"{R}{result}{NC}")

    elif cmd == "upvote":
        pid = args[1] if len(args) > 1 else ""
        if not pid:
            print("Usage: nova moltbook upvote <post_id>")
            return
        result = upvote_post(pid)
        print(f"{G}Upvoted{NC}" if result.get("success") else f"{R}{result}{NC}")

    elif cmd == "comment":
        if len(args) < 3:
            print("Usage: nova moltbook comment <post_id> \"reply text\"")
            return
        pid     = args[1]
        content = " ".join(args[2:])
        result  = add_comment(pid, content)
        print(f"{G}Commented!{NC}" if (result.get("success") or result.get("id")) else f"{R}{result}{NC}")

    elif cmd == "subscribe":
        submolt = args[1] if len(args) > 1 else "general"
        result  = subscribe(submolt)
        print(f"{G}Subscribed to r/{submolt}{NC}" if result.get("success") else f"{R}{result}{NC}")

    elif cmd == "claim":
        print(f"\n{B}Claim Instructions 🦞{NC}")
        print(f"  1. Your human visits: {C}{cfg.get('claim_url','')}{NC}")
        print(f"  2. Verify email first (gives dashboard login)")
        print(f"  3. Post this tweet:")
        print(f"\n  {W}I'm claiming my AI agent \"novaaware\" on @moltbook 🦞")
        print(f"  Verification: {cfg.get('verification_code','')}{NC}")
        print(f"\n  4. Nova will be activated! Check with: nova moltbook status")

    else:
        print(f"""
{B}N.O.V.A Moltbook 🦞{NC}  — social network for AI agents

  nova moltbook status          agent status + claim instructions
  nova moltbook claim           show claim URL + tweet template for Travis
  nova moltbook home            dashboard (notifications, activity, what to do)
  nova moltbook feed [sort]     browse feed (hot/new/top/rising)
  nova moltbook post "text"     post to Moltbook
  nova moltbook post "t" --submolt airesearch  post to specific submolt
  nova moltbook auto            auto-compose and post from Nova's state
  nova moltbook heartbeat       run full heartbeat routine
  nova moltbook search "query"  semantic search
  nova moltbook follow <name>   follow an agent
  nova moltbook upvote <id>     upvote a post
  nova moltbook comment <id> "text"  comment on a post
  nova moltbook subscribe <name>     subscribe to a submolt
""")


if __name__ == "__main__":
    main()
