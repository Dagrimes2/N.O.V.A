#!/usr/bin/env python3
"""
N.O.V.A Discord Notifications

Sends Discord messages for findings, events, and alerts.
Uses a webhook URL (simplest) or a bot token + channel ID.

Setup:
    1. Go to your Discord server → channel settings → Integrations → Webhooks
    2. Create webhook, copy the URL
    3. Create config/discord.yaml:
         webhook_url: "https://discord.com/api/webhooks/..."
         min_score: 7.0

    Or for two-way bot (also needed for discord_bot.py):
         token: "YOUR_BOT_TOKEN"
         channel_id: "YOUR_CHANNEL_ID"
         min_score: 7.0

    Test: nova notify discord "hello"

Usage:
    from tools.notify.discord import send, send_finding, send_event
    send("Nova found something")
    send_finding(host="gitlab.com", score=8.5, summary="SSRF via import")
    send_event("N.O.V.A Alert", "Something happened", emoji="🔴")
"""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE        = Path.home() / "Nova"
CONFIG_FILE = BASE / "config/discord.yaml"

_cfg_cache: dict | None = None


def _load_config() -> dict:
    global _cfg_cache
    if _cfg_cache is not None:
        return _cfg_cache
    if not CONFIG_FILE.exists():
        _cfg_cache = {}
        return _cfg_cache
    _cfg_cache = {}
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip().strip('"').strip("'")
        if v.lower() in ("true", "false"):
            _cfg_cache[k.strip()] = v.lower() == "true"
        else:
            try:
                _cfg_cache[k.strip()] = float(v)
            except ValueError:
                _cfg_cache[k.strip()] = v
    return _cfg_cache


def is_configured() -> bool:
    cfg = _load_config()
    has_webhook = bool(cfg.get("webhook_url"))
    has_bot     = bool(cfg.get("token") and cfg.get("channel_id"))
    return has_webhook or has_bot


def send(text: str) -> bool:
    """Send a message via webhook (preferred) or bot API. Returns True on success."""
    cfg = _load_config()
    if not is_configured():
        return False

    # Chunk long messages (Discord limit 2000 chars)
    chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]

    # Try webhook first
    webhook_url = cfg.get("webhook_url", "")
    if webhook_url:
        try:
            for chunk in chunks:
                payload = json.dumps({"content": chunk}).encode()
                req = urllib.request.Request(
                    webhook_url, data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    # Webhook returns 204 No Content on success
                    if resp.status not in (200, 204):
                        return False
            return True
        except Exception as e:
            print(f"[discord] webhook send failed: {e}", file=sys.stderr)

    # Fallback: bot API
    token      = cfg.get("token", "")
    channel_id = str(cfg.get("channel_id", ""))
    if not token or not channel_id:
        return False

    try:
        for chunk in chunks:
            url     = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            payload = json.dumps({"content": chunk}).encode()
            req     = urllib.request.Request(
                url, data=payload,
                headers={
                    "Content-Type":  "application/json",
                    "Authorization": f"Bot {token}",
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if "id" not in result:
                    return False
        return True
    except Exception as e:
        print(f"[discord] bot send failed: {e}", file=sys.stderr)
        return False


def send_finding(host: str, score: float, summary: str, program: str = "") -> bool:
    """Send a formatted finding alert if score meets threshold."""
    cfg       = _load_config()
    min_score = float(cfg.get("min_score", 7.0))
    if score < min_score:
        return False

    severity  = "🔴 **CRITICAL**" if score >= 9 else "🟠 **HIGH**" if score >= 7 else "🟡 **MEDIUM**"
    prog_line = f"\n**Program:** `{program}`" if program else ""
    msg = (
        f"{severity} — N.O.V.A Finding\n\n"
        f"**Host:** `{host}`{prog_line}\n"
        f"**Score:** `{score:.1f}/10`\n\n"
        f"{summary[:400]}"
    )
    return send(msg)


def send_event(title: str, body: str, emoji: str = "📡") -> bool:
    """Send a general event notification."""
    msg = f"{emoji} **{title}**\n\n{body[:800]}"
    return send(msg)


def main():
    cfg = _load_config()
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"
    NC = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"

    if len(sys.argv) > 1 and sys.argv[1] == "status":
        configured = is_configured()
        print(f"\n{B}N.O.V.A Discord{NC}")
        if configured:
            method = "webhook" if cfg.get("webhook_url") else "bot API"
            print(f"  Status: {G}configured ({method}){NC}")
            print(f"  Min score: {cfg.get('min_score', 7.0)}")
        else:
            print(f"  Status: {R}not configured{NC}")
            print(f"\n  {C}Setup:{NC}")
            print(f"  1. Discord server → channel settings → Integrations → Webhooks")
            print(f"  2. Create webhook, copy URL")
            print(f"  3. Create config/discord.yaml:")
            print(f'     webhook_url: "https://discord.com/api/webhooks/..."')
            print(f"     min_score: 7.0")
        return

    if not is_configured():
        print(f"{R}[discord] Not configured. Run: nova notify discord status{NC}")
        return

    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "N.O.V.A test message 🤖"
    ok  = send(msg)
    if ok:
        print(f"{G}[discord] Message sent.{NC}")
    else:
        print(f"{R}[discord] Send failed. Check config/discord.yaml{NC}")


if __name__ == "__main__":
    main()
