#!/usr/bin/env python3
"""
N.O.V.A Market Data Layer

Fetches OHLCV history + current price for crypto, stocks, and NFT floor prices.
Sources (all free, no API key required for basic tier):
  - CoinGecko  : crypto prices + history
  - yfinance   : stocks, ETFs, indices, forex
  - Alternative.me : Fear & Greed index
  - Reservoir  : NFT floor prices (free tier)

Cache: memory/markets/cache/ — TTL per asset type
"""
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import yfinance as yf
import pandas as pd

BASE       = Path.home() / "Nova"
CACHE_DIR  = BASE / "memory/markets/cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

COINGECKO  = "https://api.coingecko.com/api/v3"
ALT_FNG    = "https://api.alternative.me/fng/"
RESERVOIR  = "https://api.reservoir.tools/collections/v7"

# Cache TTL in seconds
TTL = {
    "price":   300,    # 5 min
    "history": 3600,   # 1 hour
    "fng":     3600,   # 1 hour
    "nft":     1800,   # 30 min
}

CRYPTO_IDS = {
    "BTC":  "bitcoin",      "ETH":  "ethereum",      "SOL":  "solana",
    "BNB":  "binancecoin",  "XRP":  "ripple",         "DOGE": "dogecoin",
    "ADA":  "cardano",      "AVAX": "avalanche-2",    "DOT":  "polkadot",
    "LINK": "chainlink",    "MATIC":"matic-network",   "UNI":  "uniswap",
    # Solana ecosystem (Phantom wallet tokens)
    "JUP":  "jupiter-exchange-solana",
    "BONK": "bonk",
    "WIF":  "dogwifcoin",
    "ORCA": "orca",
    "RAY":  "raydium",
    "MSOL": "msol",
}


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cache_path(key: str) -> Path:
    safe = key.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{safe}.json"


def _cache_get(key: str, ttl: int) -> dict | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        age  = time.time() - data.get("_ts", 0)
        if age < ttl:
            return data
    except Exception:
        pass
    return None


def _cache_set(key: str, data: dict) -> None:
    data["_ts"] = time.time()
    _cache_path(key).write_text(json.dumps(data))


# ── Crypto ─────────────────────────────────────────────────────────────────────

def get_crypto_price(symbol: str) -> dict:
    """Current price + 24h change for a crypto symbol (e.g. 'BTC')."""
    symbol = symbol.upper()
    cid    = CRYPTO_IDS.get(symbol, symbol.lower())
    cached = _cache_get(f"crypto_price_{symbol}", TTL["price"])
    if cached:
        return cached

    try:
        resp = requests.get(
            f"{COINGECKO}/simple/price",
            params={"ids": cid, "vs_currencies": "usd",
                    "include_24hr_change": "true", "include_market_cap": "true"},
            timeout=10
        )
        raw = resp.json().get(cid, {})
        result = {
            "symbol":      symbol,
            "price_usd":   raw.get("usd", 0),
            "change_24h":  raw.get("usd_24h_change", 0),
            "market_cap":  raw.get("usd_market_cap", 0),
            "source":      "coingecko",
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }
        _cache_set(f"crypto_price_{symbol}", result)
        return result
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def get_crypto_history(symbol: str, days: int = 90) -> pd.DataFrame:
    """OHLCV history as DataFrame via yfinance (BTC-USD style tickers)."""
    symbol = symbol.upper()
    key    = f"crypto_hist_{symbol}_{days}"
    cached = _cache_get(key, TTL["history"])
    if cached:
        return pd.DataFrame(cached["rows"])

    # Convert days to yfinance period
    period = "1y" if days >= 300 else ("6mo" if days >= 150 else ("3mo" if days >= 60 else "1mo"))
    ticker = f"{symbol}-USD"
    try:
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        # Flatten MultiIndex columns from yfinance
        df.columns = [
            c[0].lower() if isinstance(c, tuple) else c.lower()
            for c in df.columns
        ]
        cols = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[cols]
        for c in cols:
            if c != "date":
                df[c] = pd.to_numeric(df[c], errors="coerce")
        rows = []
        for _, row in df.iterrows():
            r = row.to_dict()
            if hasattr(r.get("date"), "strftime"):
                r["date"] = r["date"].strftime("%Y-%m-%d")
            rows.append(r)
        _cache_set(key, {"rows": rows})
        return pd.DataFrame(rows)
    except Exception as e:
        return pd.DataFrame()


# ── Stocks ─────────────────────────────────────────────────────────────────────

def get_stock_price(ticker: str) -> dict:
    """Current price + info for a stock/ETF ticker."""
    cached = _cache_get(f"stock_price_{ticker}", TTL["price"])
    if cached:
        return cached
    try:
        t    = yf.Ticker(ticker)
        info = t.fast_info
        result = {
            "symbol":     ticker.upper(),
            "price_usd":  round(float(info.last_price or 0), 4),
            "prev_close": round(float(info.previous_close or 0), 4),
            "change_pct": round(
                (float(info.last_price or 0) - float(info.previous_close or 1))
                / float(info.previous_close or 1) * 100, 4
            ),
            "market_cap": info.market_cap,
            "source":     "yfinance",
            "timestamp":  datetime.now(timezone.utc).isoformat(),
        }
        _cache_set(f"stock_price_{ticker}", result)
        return result
    except Exception as e:
        return {"symbol": ticker, "error": str(e)}


def get_stock_history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """OHLCV history. period: 1mo 3mo 6mo 1y 2y 5y max"""
    key    = f"stock_hist_{ticker}_{period}"
    cached = _cache_get(key, TTL["history"])
    if cached:
        return pd.DataFrame(cached["rows"])
    try:
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        df = df.reset_index()
        df.columns = [
            c[0].lower() if isinstance(c, tuple) else c.lower()
            for c in df.columns
        ]
        avail = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
        rows = df[avail].to_dict("records")
        for r in rows:
            if hasattr(r["date"], "strftime"):
                r["date"] = r["date"].strftime("%Y-%m-%d")
        _cache_set(key, {"rows": rows})
        return pd.DataFrame(rows)
    except Exception as e:
        return pd.DataFrame()


# ── Fear & Greed ───────────────────────────────────────────────────────────────

def get_fear_greed() -> dict:
    """Crypto Fear & Greed index (0=Extreme Fear, 100=Extreme Greed)."""
    cached = _cache_get("fear_greed", TTL["fng"])
    if cached:
        return cached
    try:
        resp = requests.get(ALT_FNG, params={"limit": 7}, timeout=10)
        data = resp.json().get("data", [])
        result = {
            "current":  int(data[0]["value"]) if data else 50,
            "label":    data[0]["value_classification"] if data else "Neutral",
            "history":  [{"value": int(d["value"]), "label": d["value_classification"],
                          "date": d["timestamp"]} for d in data],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _cache_set("fear_greed", result)
        return result
    except Exception as e:
        return {"current": 50, "label": "Neutral", "error": str(e)}


# ── NFT floors ─────────────────────────────────────────────────────────────────

def get_nft_floor(collection_slug: str) -> dict:
    """Floor price for an NFT collection via Reservoir (no key needed for basic)."""
    key    = f"nft_{collection_slug}"
    cached = _cache_get(key, TTL["nft"])
    if cached:
        return cached
    try:
        resp = requests.get(
            RESERVOIR,
            params={"slug": collection_slug, "limit": 1},
            timeout=10
        )
        colls = resp.json().get("collections", [])
        if not colls:
            return {"slug": collection_slug, "error": "not found"}
        c = colls[0]
        result = {
            "slug":         collection_slug,
            "name":         c.get("name", ""),
            "floor_eth":    c.get("floorAsk", {}).get("price", {}).get("amount", {}).get("decimal", 0),
            "volume_24h":   c.get("volume", {}).get("1day", 0),
            "sales_24h":    c.get("salesCount", {}).get("1day", 0),
            "timestamp":    datetime.now(timezone.utc).isoformat(),
        }
        _cache_set(key, result)
        return result
    except Exception as e:
        return {"slug": collection_slug, "error": str(e)}


# ── Convenience ────────────────────────────────────────────────────────────────

def get_market_snapshot(assets: list[str]) -> list[dict]:
    """
    Quick snapshot for a list of tickers/symbols.
    Auto-detects crypto vs stock by checking CRYPTO_IDS.
    """
    results = []
    for a in assets:
        a = a.upper()
        if a in CRYPTO_IDS or len(a) <= 5 and a.isalpha():
            # Try crypto first
            data = get_crypto_price(a)
            if "error" not in data or not data.get("price_usd"):
                results.append(data)
                continue
        results.append(get_stock_price(a))
    return results


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    if sym.upper() in CRYPTO_IDS:
        p = get_crypto_price(sym)
    else:
        p = get_stock_price(sym)
    print(json.dumps(p, indent=2, default=str))
