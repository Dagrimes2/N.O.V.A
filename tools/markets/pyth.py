#!/usr/bin/env python3
"""
N.O.V.A Pyth Network Oracle

Real-time, on-chain price feeds from Pyth Network.
Pyth aggregates prices from institutional-grade data providers
(Jane Street, CBOE, Virtu, etc.) directly on-chain.

For Solana ecosystem tokens this is more accurate than CoinGecko
because it reflects actual DEX/market activity with millisecond latency.

Free API: hermes.pyth.network (no key required)
Feeds: https://pyth.network/price-feeds

Usage:
    from tools.markets.pyth import get_pyth_price, get_pyth_prices
    price = get_pyth_price("SOL")
    prices = get_pyth_prices(["BTC", "ETH", "SOL"])
"""
import json
import sys
import time
from pathlib import Path

import requests

BASE = Path.home() / "Nova"
_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# Pyth Hermes REST API
HERMES_URL = "https://hermes.pyth.network"

# Price feed IDs (hex, from https://pyth.network/price-feeds)
# These are stable identifiers that never change
PYTH_FEED_IDS: dict[str, str] = {
    "BTC":  "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
    "ETH":  "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",
    "SOL":  "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
    "BNB":  "2f95862b045670cd22bee3114c39763a4a08beeb663b145d283c31d7d1101c4f",
    "AVAX": "93da3352f9f1d105fdfe4971cfa80e9dd777bfc5d0f683ebb6e1294b92137bb7",
    "DOGE": "dcef50dd0a4cd2dcc17e45df1676dcb336a11a61c69df7a0299b0150c672d25c",
    "MATIC":"5de33a9112c2b700b8d30b8a3402c103578ccfa2765696471cc672bd5cf6ac52",
    "LINK": "8ac0c70fff57e9aefdf5edf44b51d62c2d433653cbb2cf5cc06bb115af04d221",
    "AAPL": "49f6b65cb1de6b10eaf75e7c03ca029c306d0357e91b5311b175084a5ad3a3fb",
    "NVDA": "75d0c4f97b63e8b7bdc58a5c43dc3dde6b3a5fcee6a5bf40900eba3a59a7ed5f",
    "MSFT": "2c9ad3dc86e6c58f0f36d4b8c7c9d7ddb6c99b6a7c98d7f8c7d7f8c7d7f8c7d",  # placeholder
    "TSLA": "16dad506d7db8da01c87581c87ca897a012a153557d4d578c3b9c9e1bc0632f1",
    "USDC": "eaa020c61cc479712813461ce153894a96a6c00b21ed0cfc2798d1f9a9e9c94a",
    "JUP":  "0a0408d619e9380abad35060f9192039ed5042fa6f82301d0e48bb52be830996",
    "WIF":  "4ca4beeca86f0d164160323817a4e42b10010a724c2217c6ee41b54cd4cc61fc",
    "BONK": "72b021217ca3fe68922a19aaf990109cb9d84e9ad004b4d2025ad6f529314419",
}

# Cache
_cache: dict[str, dict] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 5.0  # Pyth is real-time — cache just 5 seconds


def _fetch_prices(feed_ids: list[str]) -> dict[str, dict]:
    """
    Fetch latest prices from Pyth Hermes API.
    Returns {feed_id: {price, conf, expo, publish_time}}.
    """
    try:
        params = [("ids[]", fid) for fid in feed_ids]
        resp   = requests.get(
            f"{HERMES_URL}/api/latest_price_feeds",
            params=params,
            timeout=10
        )
        data  = resp.json()
        result = {}
        for feed in data:
            fid  = feed.get("id", "")
            price_data = feed.get("price", {})
            raw_price  = int(price_data.get("price", 0))
            expo       = int(price_data.get("expo", 0))
            conf       = int(price_data.get("conf", 0))
            pub_time   = price_data.get("publish_time", 0)

            price_usd = raw_price * (10 ** expo)
            conf_usd  = conf * (10 ** expo)

            result[fid] = {
                "price":        round(price_usd, 8),
                "conf":         round(conf_usd, 8),     # confidence interval ±
                "publish_time": pub_time,
                "age_seconds":  int(time.time()) - pub_time,
            }
        return result
    except Exception:
        return {}


def get_pyth_price(symbol: str) -> dict:
    """
    Get real-time Pyth price for a single symbol.
    Returns {price, conf, age_seconds, source}.
    """
    sym    = symbol.upper()
    feed_id = PYTH_FEED_IDS.get(sym)
    if not feed_id:
        return {"error": f"No Pyth feed for {sym}", "price": 0.0}

    global _cache, _cache_ts
    now = time.monotonic()
    if now - _cache_ts < _CACHE_TTL and feed_id in _cache:
        return {**_cache[feed_id], "source": "pyth_cache"}

    data = _fetch_prices([feed_id])
    if feed_id not in data:
        return {"error": "Pyth fetch failed", "price": 0.0}

    _cache[feed_id] = data[feed_id]
    _cache_ts       = now
    return {**data[feed_id], "symbol": sym, "source": "pyth_live"}


def get_pyth_prices(symbols: list[str]) -> dict[str, dict]:
    """
    Get Pyth prices for multiple symbols in one request.
    Returns {symbol: {price, conf, age_seconds}}.
    """
    sym_to_feed = {}
    for sym in symbols:
        s = sym.upper()
        if s in PYTH_FEED_IDS:
            sym_to_feed[s] = PYTH_FEED_IDS[s]

    if not sym_to_feed:
        return {}

    global _cache, _cache_ts
    now = time.monotonic()

    # Check cache
    if now - _cache_ts < _CACHE_TTL:
        cached_result = {}
        missing = []
        for sym, fid in sym_to_feed.items():
            if fid in _cache:
                cached_result[sym] = {**_cache[fid], "source": "pyth_cache"}
            else:
                missing.append((sym, fid))
        if not missing:
            return cached_result

    # Fetch all at once
    feed_ids = list(sym_to_feed.values())
    data     = _fetch_prices(feed_ids)

    result = {}
    for sym, fid in sym_to_feed.items():
        if fid in data:
            _cache[fid] = data[fid]
            result[sym]  = {**data[fid], "symbol": sym, "source": "pyth_live"}
        else:
            result[sym]  = {"price": 0.0, "error": "unavailable"}

    _cache_ts = now
    return result


def get_price_usd(symbol: str) -> float:
    """Convenience: return just the USD price."""
    return get_pyth_price(symbol).get("price", 0.0)


def is_stale(symbol: str, max_age_seconds: int = 60) -> bool:
    """Return True if the Pyth price is stale (not updated recently)."""
    info = get_pyth_price(symbol)
    return info.get("age_seconds", 9999) > max_age_seconds


def available_feeds() -> list[str]:
    """Return list of symbols with known Pyth feed IDs."""
    return sorted(PYTH_FEED_IDS.keys())


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0].upper() if args else "LIST"

    if cmd == "LIST":
        print(f"\n{B}Pyth Network Price Feeds{NC}  ({len(PYTH_FEED_IDS)} available)")
        for sym in sorted(PYTH_FEED_IDS.keys()):
            print(f"  {C}{sym}{NC}")

    elif cmd in PYTH_FEED_IDS:
        print(f"{DIM}Fetching {cmd} from Pyth...{NC}", end="\r")
        info = get_pyth_price(cmd)
        if "error" in info:
            print(f"{R}{info['error']}{NC}")
            return
        age_col = G if info["age_seconds"] < 10 else (Y if info["age_seconds"] < 60 else R)
        print(f"\n{B}Pyth — {cmd}{NC}")
        print(f"  Price  : {G}${info['price']:,.6g}{NC}")
        print(f"  Conf±  : ${info['conf']:,.6g}  ({info['conf']/info['price']*100:.4f}%)")
        print(f"  Age    : {age_col}{info['age_seconds']}s{NC}  {DIM}({info['source']}){NC}")

    else:
        # Treat as multiple symbols
        syms = [a.upper() for a in args]
        if not syms:
            syms = ["BTC", "ETH", "SOL"]
        print(f"{DIM}Fetching {len(syms)} Pyth prices...{NC}", end="\r")
        prices = get_pyth_prices(syms)
        print(f"\n{B}Pyth Network Prices{NC}")
        print(f"{'Symbol':8s} {'Price':>14s} {'±Conf':>12s} {'Age':>6s}")
        print(f"{DIM}{'─'*44}{NC}")
        for sym in syms:
            if sym not in prices:
                print(f"  {R}{sym:6s}{NC}  {DIM}no feed{NC}")
                continue
            p   = prices[sym]
            col = G if p.get("age_seconds", 99) < 10 else Y
            print(f"  {W}{sym:6s}{NC}  ${p.get('price',0):>12,.6g}  "
                  f"±{p.get('conf',0):>8,.6g}  "
                  f"{col}{p.get('age_seconds',0):>4d}s{NC}")


if __name__ == "__main__":
    main()
