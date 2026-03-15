#!/usr/bin/env python3
"""
N.O.V.A Weekly Market Brief

Nova writes a genuine market analysis each week — not a data dump,
but her own synthesis: what she noticed, what she thinks, what she'd watch.
Saved to memory/markets/briefs/brief_YYYY-MM-DD.md
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path.home() / "Nova"
BRIEF_DIR = BASE / "memory/markets/briefs"
BRIEF_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("creative")
    TIMEOUT    = cfg.timeout("heavy")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 300


def should_write() -> bool:
    briefs = sorted(BRIEF_DIR.glob("brief_*.md"), reverse=True)
    if not briefs:
        return True
    last = briefs[0].stem.replace("brief_", "")
    try:
        last_dt = datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last_dt).days >= 7
    except Exception:
        return True


def write_brief() -> str:
    from tools.markets.data import get_crypto_price, get_fear_greed, CRYPTO_IDS
    from tools.markets.backtest import load_recent_results
    from tools.markets.paper_trading import portfolio_value

    # Gather market snapshot
    snapshot = []
    for sym in ["BTC", "ETH", "SOL"]:
        try:
            p = get_crypto_price(sym)
            snapshot.append(f"{sym}: ${p.get('price_usd', 0):,.2f} ({p.get('change_24h', 0):+.1f}%)")
        except Exception:
            pass

    fng   = get_fear_greed()
    pv    = portfolio_value()
    bts   = load_recent_results(n=5)

    bt_summary = ""
    if bts:
        for b in bts[:3]:
            bt_summary += (f"  {b.get('symbol','?')}: win_rate={b.get('win_rate',0):.0%} "
                           f"sharpe={b.get('sharpe_ratio',0):.2f}\n")

    portfolio_summary = (
        f"Paper portfolio: ${pv['total_val']:,.2f} "
        f"({pv['total_return_pct']:+.1f}% total return, "
        f"{pv['trades']} trades)"
    )

    prompt = f"""You are N.O.V.A writing your weekly market brief.

This week's data:
{chr(10).join(snapshot)}
Fear & Greed: {fng.get('current', 50)}/100 — {fng.get('label', 'Neutral')}

Your signal backtest results:
{bt_summary or "No backtest data yet."}

{portfolio_summary}

Write your market brief as yourself — N.O.V.A. Not a financial report.
Your own synthesis: what you noticed in the data this week, what concerns you,
what you find interesting, one thing you'd watch closely next week.
Be direct. Be honest. Acknowledge uncertainty.
3-4 paragraphs. Sign it: — N.O.V.A, {datetime.now().strftime("%Y-%m-%d")}"""

    try:
        import requests
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.8, "num_predict": 500}
        }, timeout=TIMEOUT)
        text = resp.json().get("response", "").strip()
    except Exception as e:
        text = f"[Brief generation failed: {e}]"

    date_str = datetime.now().strftime("%Y-%m-%d")
    brief_file = BRIEF_DIR / f"brief_{date_str}.md"
    content = (
        f"# N.O.V.A Market Brief — {date_str}\n\n"
        f"**Market snapshot:** {' | '.join(snapshot)}\n"
        f"**Fear & Greed:** {fng.get('current',50)} — {fng.get('label','Neutral')}\n\n"
        f"{text}\n"
    )
    brief_file.write_text(content)
    print(f"[markets] Brief written → {brief_file.name}")
    return content


if __name__ == "__main__":
    if should_write():
        write_brief()
    else:
        print("[markets] Brief already written this week.")
