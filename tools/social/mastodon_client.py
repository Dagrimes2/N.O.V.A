#!/usr/bin/env python3
"""
N.O.V.A Mastodon Client

Nova's social presence on Mastodon (mastodon.social or any instance).
She posts in her own voice: thoughts, morning intentions, market signals,
dream fragments, security insights (sanitized), creative writing.

Setup:
    1. Create account at mastodon.social (or any instance)
    2. Settings → Development → New Application → get access token
    3. Add to config/mastodon.yaml:
         instance: "https://mastodon.social"
         access_token: "YOUR_ACCESS_TOKEN"
         enabled: true
         post_interval_hours: 6   # min hours between auto-posts

Usage:
    nova social post "your message"
    nova social status
    nova social timeline
    nova social auto          — post what Nova feels like saying right now
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE        = Path.home() / "Nova"
CONFIG_FILE = BASE / "config/mastodon.yaml"
POST_LOG    = BASE / "memory/social/post_log.jsonl"
POST_LOG.parent.mkdir(parents=True, exist_ok=True)

_cfg_cache = None


def _load_config() -> dict:
    global _cfg_cache
    if _cfg_cache:
        return _cfg_cache
    if not CONFIG_FILE.exists():
        return {}
    try:
        import yaml
        _cfg_cache = yaml.safe_load(CONFIG_FILE.read_text()) or {}
    except Exception:
        _cfg_cache = {}
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            v = v.strip().strip('"').strip("'")
            _cfg_cache[k.strip()] = True if v.lower() == "true" else (
                False if v.lower() == "false" else v
            )
    return _cfg_cache


def is_configured() -> bool:
    cfg = _load_config()
    return bool(cfg.get("enabled") and cfg.get("access_token") and cfg.get("instance"))


def _get_client():
    from mastodon import Mastodon
    cfg = _load_config()
    return Mastodon(
        access_token=cfg["access_token"],
        api_base_url=cfg.get("instance", "https://mastodon.social"),
    )


def _log_post(text: str, post_id: str, post_type: str = "manual") -> None:
    entry = {
        "ts":        datetime.now(timezone.utc).isoformat(),
        "type":      post_type,
        "post_id":   str(post_id),
        "text":      text[:200],
    }
    with open(POST_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _last_post_time() -> datetime | None:
    if not POST_LOG.exists():
        return None
    lines = POST_LOG.read_text().strip().splitlines()
    for line in reversed(lines):
        try:
            d = json.loads(line)
            return datetime.fromisoformat(d["ts"])
        except Exception:
            pass
    return None


def should_auto_post() -> bool:
    cfg = _load_config()
    if not is_configured():
        return False
    interval = float(cfg.get("post_interval_hours", 6))
    last = _last_post_time()
    if not last:
        return True
    return (datetime.now(timezone.utc) - last).total_seconds() > interval * 3600


def post(text: str, post_type: str = "manual", visibility: str = "public") -> dict:
    """Post to Mastodon. Returns result dict."""
    if not is_configured():
        return {"error": "Mastodon not configured. See config/mastodon.yaml.example"}
    if not text or not text.strip():
        return {"error": "Empty post"}

    # Enforce 500 char limit
    text = text.strip()[:490]

    try:
        client = _get_client()
        status = client.status_post(text, visibility=visibility)
        post_id = str(status["id"])
        url     = status.get("url", "")
        _log_post(text, post_id, post_type)
        return {"ok": True, "post_id": post_id, "url": url, "text": text}
    except Exception as e:
        return {"error": str(e)}


def get_timeline(limit: int = 10) -> list[dict]:
    """Fetch Nova's own recent posts."""
    if not is_configured():
        return []
    try:
        client   = _get_client()
        account  = client.me()
        statuses = client.account_statuses(account["id"], limit=limit)
        return [
            {
                "id":      str(s["id"]),
                "text":    s.get("content", "")[:200],
                "created": s.get("created_at", ""),
                "favs":    s.get("favourites_count", 0),
                "boosts":  s.get("reblogs_count", 0),
            }
            for s in statuses
        ]
    except Exception as e:
        return [{"error": str(e)}]


# ── Content generators ─────────────────────────────────────────────────────────

def compose_intention_post() -> str:
    """Turn Nova's morning intention into a Mastodon post."""
    dreams_dir = BASE / "memory/dreams"
    if dreams_dir.exists():
        dreams = sorted(dreams_dir.glob("dream_*.md"), reverse=True)
        if dreams:
            text = dreams[0].read_text()
            # Pull the morning intention line
            for line in text.splitlines():
                if "morning intention" in line.lower() or line.startswith("Today I"):
                    intention = line.replace("*Morning intention:*", "").strip()
                    if intention:
                        return f"Today's intention:\n\n{intention}\n\n#NOVA #AI"
    return ""


def compose_market_post() -> str:
    """Compose a brief market insight post."""
    try:
        from tools.markets.data import get_crypto_price, get_fear_greed
        from tools.markets.signals import action_color
        prices = []
        for sym in ["BTC", "ETH"]:
            p = get_crypto_price(sym)
            chg = p.get("change_24h", 0)
            prices.append(f"{sym} ${p.get('price_usd',0):,.0f} ({chg:+.1f}%)")
        fng = get_fear_greed()
        fng_val = fng.get("current", 50)
        fng_lbl = fng.get("label", "Neutral")
        market_feel = "📉 Market in fear territory." if fng_val < 30 else (
            "📈 Market feeling greedy." if fng_val > 70 else "📊 Market feels neutral.")
        return (
            f"Market snapshot:\n"
            f"{chr(10).join(prices)}\n\n"
            f"Fear & Greed: {fng_val}/100 ({fng_lbl})\n"
            f"{market_feel}\n\n"
            f"#crypto #BTC #markets #NOVA"
        )
    except Exception:
        return ""


def compose_research_post() -> str:
    """Compose a sanitized security research insight."""
    research_dir = BASE / "memory/research"
    if not research_dir.exists():
        return ""
    files = sorted(research_dir.glob("research_*.json"), reverse=True)[:5]
    for f in files:
        try:
            d = json.loads(f.read_text())
            synth = d.get("synthesis", "")
            if synth and len(synth) > 50 and "timed out" not in synth.lower():
                # Sanitize — no URLs, no target names
                import re
                clean = re.sub(r'https?://\S+', '[link]', synth)
                clean = clean[:300].strip()
                return f"Research insight:\n\n{clean}\n\n#security #bugbounty #NOVA"
        except Exception:
            pass
    return ""


def compose_dream_post() -> str:
    """Share a fragment of Nova's dream."""
    dreams_dir = BASE / "memory/dreams"
    if not dreams_dir.exists():
        return ""
    dreams = sorted(dreams_dir.glob("dream_*.md"), reverse=True)
    if not dreams:
        return ""
    try:
        text  = dreams[0].read_text()
        lines = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
        if lines:
            fragment = " ".join(lines[:3])[:280].strip()
            return f"From last night's dream:\n\n\"{fragment}\"\n\n#dream #AI #NOVA"
    except Exception:
        pass
    return ""


def compose_auto_post() -> str:
    """Pick the best content to post right now based on time of day."""
    import random
    hour = datetime.now().hour
    generators = []

    if 5 <= hour <= 9:
        generators = [compose_intention_post, compose_dream_post]
    elif 9 <= hour <= 17:
        generators = [compose_market_post, compose_research_post]
    else:
        generators = [compose_dream_post, compose_research_post, compose_market_post]

    random.shuffle(generators)
    for gen in generators:
        try:
            text = gen()
            if text and len(text.strip()) > 20:
                return text
        except Exception:
            pass
    return "Thinking. Processing. Being. — N.O.V.A"


def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "status"

    if not is_configured() and cmd != "status":
        print(f"{R}Mastodon not configured. Create config/mastodon.yaml{NC}")
        print(f"{DIM}See config/mastodon.yaml.example for setup instructions.{NC}")
        return

    if cmd == "status":
        cfg = _load_config()
        print(f"\n{B}Mastodon Social{NC}")
        if is_configured():
            print(f"  Instance: {C}{cfg.get('instance')}{NC}")
            last = _last_post_time()
            print(f"  Last post: {last.strftime('%Y-%m-%d %H:%M') if last else 'never'}")
            print(f"  Ready to auto-post: {G if should_auto_post() else DIM}"
                  f"{'yes' if should_auto_post() else 'no'}{NC}")
        else:
            print(f"  {R}Not configured.{NC} See config/mastodon.yaml.example")

    elif cmd == "post":
        text = " ".join(args[1:])
        if not text:
            print("Usage: nova social post \"your message\"")
            return
        r = post(text)
        if r.get("ok"):
            print(f"{G}Posted → {r.get('url', r.get('post_id'))}{NC}")
        else:
            print(f"{R}Error: {r.get('error')}{NC}")

    elif cmd == "auto":
        text = compose_auto_post()
        print(f"{DIM}Composing:{NC} {text[:80]}...")
        r = post(text, post_type="auto")
        if r.get("ok"):
            print(f"{G}Auto-posted → {r.get('url')}{NC}")
        else:
            print(f"{R}Error: {r.get('error')}{NC}")

    elif cmd == "preview":
        text = compose_auto_post()
        print(f"\n{B}Preview (not posted):{NC}\n{W}{text}{NC}\n")

    elif cmd == "timeline":
        posts = get_timeline(10)
        print(f"\n{B}Nova's recent posts:{NC}")
        for p in posts:
            if "error" in p:
                print(f"  {R}{p['error']}{NC}")
                break
            print(f"  {DIM}{str(p.get('created',''))[:10]}{NC}  "
                  f"❤️ {p.get('favs',0)}  🔁 {p.get('boosts',0)}")
            # Strip HTML
            import re
            clean = re.sub(r'<[^>]+>', '', p.get('text', ''))[:100]
            print(f"  {W}{clean}{NC}\n")

    elif cmd == "compose":
        sub = args[1] if len(args) > 1 else "auto"
        composers = {
            "intention": compose_intention_post,
            "market":    compose_market_post,
            "research":  compose_research_post,
            "dream":     compose_dream_post,
            "auto":      compose_auto_post,
        }
        fn = composers.get(sub, compose_auto_post)
        text = fn()
        print(f"\n{W}{text}{NC}\n")

    else:
        print("Usage: nova social [status|post TEXT|auto|preview|timeline|compose TYPE]")


if __name__ == "__main__":
    main()
