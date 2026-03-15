#!/usr/bin/env python3
"""
N.O.V.A Market Sentiment Engine

Aggregates sentiment signals:
  - Fear & Greed index (crypto)
  - Price momentum vs 7/30/90 day averages
  - Volume spike detection
  - On-chain-style signals (via CoinGecko community data)
  - News headline sentiment (keyword-based, no API key)

Returns a normalized sentiment score: -1.0 (extreme fear) to +1.0 (extreme greed)
"""
import numpy as np
import pandas as pd
from pathlib import Path


BASE = Path.home() / "Nova"


# Keyword sentiment weights for news/social headlines
BULLISH_WORDS = {
    "surge": 2, "rally": 2, "breakout": 2, "all-time high": 3, "ath": 2,
    "adoption": 1, "partnership": 1, "upgrade": 1, "launch": 1, "bullish": 2,
    "accumulate": 1, "whale buying": 2, "institutional": 1, "etf approved": 3,
    "halving": 2, "positive": 1, "recovery": 1, "green": 1, "moon": 1,
}

BEARISH_WORDS = {
    "crash": 3, "dump": 2, "hack": 3, "exploit": 3, "ban": 2, "regulation": 1,
    "sec": 1, "lawsuit": 2, "fear": 2, "panic": 2, "sell-off": 2,
    "bearish": 2, "drop": 1, "collapse": 3, "scam": 3, "rug": 3,
    "delisted": 3, "negative": 1, "red": 1, "correction": 1,
}


def score_headline(text: str) -> float:
    """Score a headline -1 to +1 based on keyword sentiment."""
    text_lower = text.lower()
    bull = sum(w for kw, w in BULLISH_WORDS.items() if kw in text_lower)
    bear = sum(w for kw, w in BEARISH_WORDS.items() if kw in text_lower)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


def momentum_sentiment(df: pd.DataFrame) -> dict:
    """
    Price-action-based sentiment from historical data.
    Returns scores for 7d, 30d, 90d windows.
    """
    if df.empty or "close" not in df.columns:
        return {"7d": 0.0, "30d": 0.0, "90d": 0.0, "overall": 0.0}

    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    price = close.iloc[-1]

    def pct_from(n: int) -> float:
        if len(close) < n:
            return 0.0
        past = close.iloc[-n]
        return (price - past) / (past + 1e-10)

    ret7  = pct_from(7)
    ret30 = pct_from(30)
    ret90 = pct_from(90)

    # Normalize to -1..+1 via tanh (caps extremes gracefully)
    s7  = float(np.tanh(ret7  * 3))
    s30 = float(np.tanh(ret30 * 2))
    s90 = float(np.tanh(ret90 * 1.5))

    # Weighted: recent momentum matters more
    overall = round(0.5 * s7 + 0.3 * s30 + 0.2 * s90, 4)
    return {"7d": round(s7, 4), "30d": round(s30, 4), "90d": round(s90, 4), "overall": overall}


def volume_sentiment(df: pd.DataFrame) -> dict:
    """
    Detect volume spikes vs 20-day average.
    Rising volume on up days = bullish, rising volume on down days = bearish.
    """
    if df.empty or "volume" not in df.columns or len(df) < 20:
        return {"spike": False, "direction": "neutral", "score": 0.0}

    vol   = pd.to_numeric(df["volume"], errors="coerce").dropna()
    close = pd.to_numeric(df["close"],  errors="coerce").dropna()

    avg_vol   = vol.rolling(20).mean().iloc[-1]
    last_vol  = vol.iloc[-1]
    price_chg = close.diff().iloc[-1]

    spike = last_vol > avg_vol * 1.5
    ratio = float(last_vol / (avg_vol + 1e-10))

    if spike and price_chg > 0:
        score = min(1.0, (ratio - 1) * 0.5)
        direction = "bullish"
    elif spike and price_chg < 0:
        score = -min(1.0, (ratio - 1) * 0.5)
        direction = "bearish"
    else:
        score = 0.0
        direction = "neutral"

    return {"spike": spike, "direction": direction, "score": round(score, 4),
            "vol_ratio": round(ratio, 3)}


def fear_greed_sentiment(fng_value: int) -> float:
    """Convert 0-100 F&G index to -1..+1 sentiment score."""
    # 0-25: extreme fear → -1.0
    # 25-45: fear → -0.5
    # 45-55: neutral → 0
    # 55-75: greed → +0.5
    # 75-100: extreme greed → +1.0
    normalized = (fng_value - 50) / 50.0
    return round(float(np.tanh(normalized * 1.5)), 4)


def aggregate_sentiment(
    fng: int = 50,
    df: pd.DataFrame = None,
    headlines: list[str] = None,
) -> dict:
    """
    Combine all sentiment sources into a final score.
    Returns score (-1 to +1) + label + component breakdown.
    """
    components = {}

    # Fear & Greed (30% weight)
    fng_score = fear_greed_sentiment(fng)
    components["fear_greed"] = {"score": fng_score, "raw": fng, "weight": 0.30}

    # Momentum (40% weight)
    mom = momentum_sentiment(df if df is not None else pd.DataFrame())
    components["momentum"] = {"score": mom["overall"], "detail": mom, "weight": 0.40}

    # Volume (20% weight)
    if df is not None and not df.empty:
        vol = volume_sentiment(df)
        components["volume"] = {"score": vol["score"], "detail": vol, "weight": 0.20}
    else:
        components["volume"] = {"score": 0.0, "weight": 0.20}

    # News headlines (10% weight)
    if headlines:
        hl_scores  = [score_headline(h) for h in headlines]
        hl_avg     = float(np.mean(hl_scores)) if hl_scores else 0.0
        components["news"] = {"score": round(hl_avg, 4), "headlines": len(headlines), "weight": 0.10}
    else:
        components["news"] = {"score": 0.0, "weight": 0.10}

    # Weighted aggregate
    final = sum(c["score"] * c["weight"] for c in components.values())
    final = round(max(-1.0, min(1.0, final)), 4)

    if final > 0.5:
        label = "extreme_greed"
    elif final > 0.2:
        label = "greed"
    elif final > -0.2:
        label = "neutral"
    elif final > -0.5:
        label = "fear"
    else:
        label = "extreme_fear"

    return {
        "score":      final,
        "label":      label,
        "components": components,
    }
