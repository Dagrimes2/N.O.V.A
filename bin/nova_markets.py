#!/usr/bin/env python3
"""
N.O.V.A Market Intelligence

Sophisticated market analysis — technical + sentiment + Monte Carlo probability.
NOT a crystal ball. A systematic edge.

Usage:
    nova markets BTC
    nova markets ETH SOL BTC --horizon 14
    nova markets AAPL TSLA NVDA --type stock
    nova markets watchlist
    nova markets nft boredapeyachtclub

IMPORTANT DISCLAIMER:
    This is probabilistic analysis. Markets are adversarial and unpredictable.
    No model can guarantee returns. Use stop-losses. Never risk what you can't lose.
    Past signal performance does not guarantee future results.
"""
import json
import sys
import os
from pathlib import Path

BASE = Path.home() / "Nova"
_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

G   = "\033[32m";  R   = "\033[31m";  C  = "\033[36m"
W   = "\033[97m";  M   = "\033[35m";  Y  = "\033[33m"
DIM = "\033[2m";   NC  = "\033[0m";   B  = "\033[1m"
BG  = "\033[92m";  BR  = "\033[91m"

DEFAULT_WATCHLIST = [
    "BTC", "ETH", "SOL", "BNB",       # major crypto
    "AAPL", "NVDA", "MSFT",            # tech stocks
]

MARKET_FILE = BASE / "memory/markets/watchlist.json"
MARKET_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_watchlist() -> list[str]:
    if MARKET_FILE.exists():
        try:
            return json.loads(MARKET_FILE.read_text())
        except Exception:
            pass
    return DEFAULT_WATCHLIST


def save_watchlist(symbols: list[str]) -> None:
    MARKET_FILE.write_text(json.dumps(symbols, indent=2))


def bar(value: float, width: int = 16) -> str:
    """Conviction bar: negative=red, positive=green, center=0."""
    v     = max(-1.0, min(1.0, value))
    mid   = width // 2
    pos   = int(abs(v) * mid)
    if v > 0:
        return DIM + "░" * mid + NC + G + "█" * pos + NC + DIM + "░" * (mid - pos) + NC
    elif v < 0:
        return DIM + "░" * (mid - pos) + NC + R + "█" * pos + NC + DIM + "░" * mid + NC
    else:
        return DIM + "░" * width + NC


def analyze_asset(symbol: str, asset_type: str = "auto", horizon: int = 7) -> dict | None:
    """Full analysis pipeline for one asset."""
    from tools.markets.data import (
        get_crypto_price, get_crypto_history,
        get_stock_price, get_stock_history,
        get_fear_greed, CRYPTO_IDS,
    )
    from tools.markets.technicals import analyze as tech_analyze
    from tools.markets.sentiment import aggregate_sentiment
    from tools.markets.signals import compute_signal

    sym = symbol.upper()

    # Detect type
    is_crypto = (asset_type == "crypto") or (asset_type == "auto" and sym in CRYPTO_IDS)

    print(f"  {DIM}Fetching {sym}...{NC}", end="\r", flush=True)

    if is_crypto:
        price_data = get_crypto_price(sym)
        df         = get_crypto_history(sym, days=120)
    else:
        price_data = get_stock_price(sym)
        df         = get_stock_history(sym, period="6mo")

    if price_data.get("error") and df.empty:
        print(f"  {R}[{sym}] Data unavailable: {price_data.get('error','')}{NC}")
        return None

    # Technical analysis
    tech = tech_analyze(df)

    # Sentiment
    fng = get_fear_greed() if is_crypto else {"current": 50, "label": "N/A"}
    sent = aggregate_sentiment(fng=fng.get("current", 50), df=df)

    # Final signal
    signal = compute_signal(sym, tech, sent, price_data, days_horizon=horizon)
    signal["price_data"] = price_data
    signal["fng"]        = fng
    return signal


def print_signal(signal: dict) -> None:
    from tools.markets.signals import action_color

    sym    = signal.get("symbol", "?")
    action = signal.get("action", "HOLD")
    conv   = signal.get("conviction", 0.0)
    risk   = signal.get("risk_score", 0.5)
    pd_    = signal.get("price_data", {})
    mc     = signal.get("monte_carlo", {})
    tech   = signal.get("technical", {})
    sent   = signal.get("sentiment", {})
    fng    = signal.get("fng", {})

    price      = pd_.get("price_usd") or pd_.get("price", 0)
    change_24h = pd_.get("change_24h") or pd_.get("change_pct", 0)
    change_col = G if change_24h >= 0 else R

    act_col  = action_color(action)
    risk_col = R if risk > 0.7 else (Y if risk > 0.4 else G)

    print(f"\n  {B}{W}{sym:6s}{NC}  "
          f"${price:,.6g}  "
          f"{change_col}{change_24h:+.2f}%{NC}  "
          f"{act_col}{B}{action:12s}{NC}  "
          f"risk={risk_col}{risk:.2f}{NC}")

    print(f"  Conviction: {bar(conv)} {conv:+.3f}")

    p_up = mc.get("p_up", 0.5)
    p_col = G if p_up > 0.55 else (R if p_up < 0.45 else Y)
    horizon = signal.get("horizon_days", 7)

    print(f"  P(up {horizon}d):  {p_col}{p_up:.0%}{NC}  "
          f"median={mc.get('p50', 0):,.4g}  "
          f"[p5={mc.get('p5',0):,.4g} → p95={mc.get('p95',0):,.4g}]")

    print(f"  Technical: {C}{tech.get('signal','?')}{NC}  "
          f"regime={tech.get('regime','?')}  "
          f"Sentiment: {sent.get('label','?')}  "
          f"F&G={fng.get('current','?')}")

    # Key indicators
    det = signal.get("_tech_details") or {}
    rsi = (signal.get("_tech") or {})
    ctx = signal.get("context", "")
    if ctx:
        print(f"  {DIM}{ctx}{NC}")


def cmd_analyze(symbols: list[str], asset_type: str = "auto", horizon: int = 7) -> None:
    print(f"\n{B}{W}N.O.V.A Market Intelligence{NC}  {DIM}horizon={horizon}d{NC}")
    print(f"{DIM}{'─' * 60}{NC}")
    print(f"{Y}{DIM}DISCLAIMER: Probabilistic analysis only. Not financial advice.{NC}")

    results = []
    for sym in symbols:
        try:
            result = analyze_asset(sym, asset_type=asset_type, horizon=horizon)
            if result:
                results.append(result)
                print_signal(result)
        except Exception as e:
            print(f"  {R}[{sym}] Error: {e}{NC}")

    if len(results) > 1:
        print(f"\n{B}Summary{NC}")
        print(f"{'Symbol':8s} {'Action':14s} {'Conviction':12s} {'P(up)':8s}")
        print(f"{DIM}{'─'*50}{NC}")
        for r in sorted(results, key=lambda x: x.get("conviction", 0), reverse=True):
            from tools.markets.signals import action_color
            a  = r.get("action", "HOLD")
            c  = r.get("conviction", 0)
            pu = r.get("monte_carlo", {}).get("p_up", 0.5)
            ac = action_color(a)
            cc = G if c > 0 else R
            print(f"  {r['symbol']:6s}   {ac}{a:12s}{NC}   {cc}{c:+.3f}{NC}   {pu:.0%}")

    print(f"\n{DIM}Run 'nova markets <symbol>' to analyze specific assets{NC}\n")


def cmd_watchlist_add(symbols: list[str]) -> None:
    wl = load_watchlist()
    for s in symbols:
        s = s.upper()
        if s not in wl:
            wl.append(s)
            print(f"{G}+ {s} added to watchlist{NC}")
        else:
            print(f"{DIM}{s} already in watchlist{NC}")
    save_watchlist(wl)


def cmd_watchlist_remove(symbols: list[str]) -> None:
    wl = load_watchlist()
    for s in symbols:
        s = s.upper()
        if s in wl:
            wl.remove(s)
            print(f"{R}- {s} removed from watchlist{NC}")
    save_watchlist(wl)


def cmd_fear_greed() -> None:
    from tools.markets.data import get_fear_greed
    fng = get_fear_greed()
    val = fng.get("current", 50)
    lbl = fng.get("label", "Neutral")
    col = G if val > 60 else (R if val < 40 else Y)
    print(f"\n{B}Crypto Fear & Greed Index{NC}")
    print(f"  {col}{B}{val}/100 — {lbl}{NC}")
    history = fng.get("history", [])[:7]
    if len(history) > 1:
        print(f"  {DIM}7-day history:{NC}")
        for h in history[1:]:
            print(f"    {h.get('label','')} ({h.get('value','')})")
    print()


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    # Parse flags
    horizon = 7
    if "--horizon" in args:
        i = args.index("--horizon")
        if i + 1 < len(args):
            try:
                horizon = int(args[i + 1])
            except Exception:
                pass
            args = args[:i] + args[i + 2:]

    asset_type = "auto"
    if "--type" in args:
        i = args.index("--type")
        if i + 1 < len(args):
            asset_type = args[i + 1]
            args = args[:i] + args[i + 2:]

    cmd = args[0].lower() if args else "watchlist"

    if cmd == "watchlist":
        symbols = load_watchlist()
        print(f"{DIM}Watchlist: {', '.join(symbols)}{NC}")
        cmd_analyze(symbols, asset_type=asset_type, horizon=horizon)

    elif cmd in ("add",):
        cmd_watchlist_add(args[1:])

    elif cmd in ("remove", "rm"):
        cmd_watchlist_remove(args[1:])

    elif cmd == "fng":
        cmd_fear_greed()

    elif cmd == "nft":
        if len(args) < 2:
            print("Usage: nova markets nft <collection-slug>")
            return
        from tools.markets.data import get_nft_floor
        nft = get_nft_floor(args[1])
        print(f"\n{B}NFT Floor — {nft.get('name', args[1])}{NC}")
        print(f"  Floor: {G}{nft.get('floor_eth', '?')} ETH{NC}")
        print(f"  24h volume: {nft.get('volume_24h', '?')} ETH")
        print(f"  24h sales:  {nft.get('sales_24h', '?')}\n")

    else:
        # Treat all remaining args as symbols
        symbols = [a.upper() for a in args if not a.startswith("--")]
        if symbols:
            cmd_analyze(symbols, asset_type=asset_type, horizon=horizon)
        else:
            print(__doc__)


if __name__ == "__main__":
    main()
