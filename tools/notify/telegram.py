#!/usr/bin/env python3
"""
N.O.V.A Telegram Alerts

Sends Telegram messages for high-score findings and critical events.
Token and chat_id stored in config/telegram.yaml (never committed).

Setup:
    1. Create a bot via @BotFather on Telegram — get TOKEN
    2. Get your chat_id: message your bot, then visit:
       https://api.telegram.org/bot<TOKEN>/getUpdates
    3. Add to config/telegram.yaml:
         enabled: true
         token: "YOUR_BOT_TOKEN"
         chat_id: "YOUR_CHAT_ID"
         min_score: 7.0    # only alert if score >= this
    4. Test: nova notify telegram "hello"

Usage:
    from tools.notify.telegram import send, send_finding
    send("Nova found something interesting")
    send_finding(host="gitlab.com", score=8.5, summary="SSRF via import endpoint")
"""
import json
import os
import sys
from pathlib import Path

BASE        = Path.home() / "Nova"
CONFIG_FILE = BASE / "config/telegram.yaml"

_cfg_cache: dict | None = None


def _load_config() -> dict:
    global _cfg_cache
    if _cfg_cache is not None:
        return _cfg_cache
    if not CONFIG_FILE.exists():
        return {}
    try:
        import yaml
        _cfg_cache = yaml.safe_load(CONFIG_FILE.read_text()) or {}
    except Exception:
        # Minimal YAML parser for flat keys
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
    return bool(cfg.get("enabled") and cfg.get("token") and cfg.get("chat_id"))


def send(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message. Returns True on success."""
    cfg = _load_config()
    if not cfg.get("enabled"):
        return False
    token   = cfg.get("token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or not chat_id:
        return False

    try:
        import urllib.request, urllib.parse
        url     = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id":    str(chat_id),
            "text":       text[:4096],
            "parse_mode": parse_mode,
        }).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"[telegram] send failed: {e}", file=sys.stderr)
        return False


def send_finding(host: str, score: float, summary: str, program: str = "") -> bool:
    """Send a formatted finding alert if score meets threshold."""
    cfg = _load_config()
    min_score = float(cfg.get("min_score", 7.0))
    if score < min_score:
        return False

    severity = "🔴 CRITICAL" if score >= 9 else "🟠 HIGH" if score >= 7 else "🟡 MEDIUM"
    prog_line = f"\n*Program:* `{program}`" if program else ""
    msg = (
        f"{severity} — N.O.V.A Finding\n\n"
        f"*Host:* `{host}`{prog_line}\n"
        f"*Score:* `{score:.1f}/10`\n\n"
        f"{summary[:300]}"
    )
    return send(msg)


def send_event(title: str, body: str, emoji: str = "📡") -> bool:
    """Send a general event notification."""
    msg = f"{emoji} *{title}*\n\n{body[:500]}"
    return send(msg)


def main():
    import sys
    cfg = _load_config()
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"
    NC = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"

    if not CONFIG_FILE.exists():
        print(f"{C}[telegram] Config not found. Create config/telegram.yaml:{NC}")
        print("  enabled: true")
        print("  token: \"YOUR_BOT_TOKEN\"")
        print("  chat_id: \"YOUR_CHAT_ID\"")
        print("  min_score: 7.0")
        return

    if not is_configured():
        print(f"{R}[telegram] Not configured or disabled. Check config/telegram.yaml{NC}")
        return

    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "N.O.V.A test message 🤖"
    ok  = send(msg)
    if ok:
        print(f"{G}[telegram] Message sent.{NC}")
    else:
        print(f"{R}[telegram] Send failed. Check token/chat_id.{NC}")


if __name__ == "__main__":
    main()
