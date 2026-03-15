#!/usr/bin/env python3
"""
N.O.V.A Technical Analysis Engine

Computes indicators from OHLCV DataFrames:
  - Trend:     EMA (9/21/50/200), SMA, VWAP, ADX
  - Momentum:  RSI, MACD, Stochastic, Williams %R
  - Volatility: Bollinger Bands, ATR, Historical Volatility
  - Volume:    OBV, VWAP, Volume ratio

All computed in pure pandas/numpy — no ta-lib dependency.
Returns a dict of signals with direction + strength.
"""
import numpy as np
import pandas as pd
from typing import Optional


# ── Core indicator functions ───────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(com=period - 1, adjust=False).mean()
    avg_l = loss.ewm(com=period - 1, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series,
         fast: int = 12, slow: int = 26, signal: int = 9
         ) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema   = ema(series, fast)
    slow_ema   = ema(series, slow)
    macd_line  = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger(series: pd.Series, period: int = 20, std: float = 2.0
              ) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid   = sma(series, period)
    stdv  = series.rolling(window=period).std()
    upper = mid + std * stdv
    lower = mid - std * stdv
    return upper, mid, lower


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3
               ) -> tuple[pd.Series, pd.Series]:
    low_min  = df["low"].rolling(k).min()
    high_max = df["high"].rolling(k).max()
    k_pct    = 100 * (df["close"] - low_min) / (high_max - low_min + 1e-10)
    d_pct    = sma(k_pct, d)
    return k_pct, d_pct


def obv(df: pd.DataFrame) -> pd.Series:
    direction = df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    vol = df.get("volume", pd.Series(0, index=df.index))
    return (direction * vol).cumsum()


def historical_volatility(series: pd.Series, period: int = 20) -> pd.Series:
    log_ret = np.log(series / series.shift(1))
    return log_ret.rolling(period).std() * np.sqrt(252)  # annualized


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    tr_      = atr(df, period)
    plus_di  = 100 * ema(plus_dm, period) / tr_.replace(0, np.nan)
    minus_di = 100 * ema(minus_dm, period) / tr_.replace(0, np.nan)
    dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return ema(dx, period)


# ── Signal aggregator ──────────────────────────────────────────────────────────

def analyze(df: pd.DataFrame) -> dict:
    """
    Run full technical analysis on OHLCV DataFrame.
    Returns structured signals dict.
    """
    if df.empty or len(df) < 30:
        return {"error": "insufficient data", "signal": "neutral", "confidence": 0.0}

    df = df.copy()
    # Ensure numeric
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])
    close = df["close"]

    signals  = []   # list of (direction, weight) tuples
    details  = {}

    # ── Trend: EMA cross ──────────────────────────────────────────────────────
    e9   = ema(close, 9).iloc[-1]
    e21  = ema(close, 21).iloc[-1]
    e50  = ema(close, 50).iloc[-1]
    e200 = ema(close, 200).iloc[-1] if len(df) >= 200 else None
    price = close.iloc[-1]

    details["ema"] = {
        "9": round(e9, 4), "21": round(e21, 4),
        "50": round(e50, 4), "price": round(price, 4),
    }

    if e9 > e21:
        signals.append(("bull", 1.5))   # short-term bullish cross
    else:
        signals.append(("bear", 1.5))

    if price > e50:
        signals.append(("bull", 1.0))
    else:
        signals.append(("bear", 1.0))

    if e200 is not None:
        details["ema"]["200"] = round(e200, 4)
        if price > e200:
            signals.append(("bull", 2.0))  # above 200 EMA = major bullish
        else:
            signals.append(("bear", 2.0))

    # ── RSI ───────────────────────────────────────────────────────────────────
    rsi_val = rsi(close).iloc[-1]
    details["rsi"] = round(rsi_val, 2)
    if rsi_val < 30:
        signals.append(("bull", 2.0))   # oversold
    elif rsi_val > 70:
        signals.append(("bear", 2.0))   # overbought
    elif rsi_val > 55:
        signals.append(("bull", 0.5))
    elif rsi_val < 45:
        signals.append(("bear", 0.5))

    # ── MACD ──────────────────────────────────────────────────────────────────
    ml, sl, hist = macd(close)
    macd_val  = ml.iloc[-1]
    sig_val   = sl.iloc[-1]
    hist_val  = hist.iloc[-1]
    hist_prev = hist.iloc[-2] if len(hist) > 1 else 0
    details["macd"] = {
        "line": round(macd_val, 6),
        "signal": round(sig_val, 6),
        "hist": round(hist_val, 6),
    }
    if hist_val > 0 and hist_val > hist_prev:
        signals.append(("bull", 1.5))   # histogram growing bullish
    elif hist_val < 0 and hist_val < hist_prev:
        signals.append(("bear", 1.5))
    elif macd_val > sig_val:
        signals.append(("bull", 0.75))
    else:
        signals.append(("bear", 0.75))

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_upper, bb_mid, bb_lower = bollinger(close)
    bbu = bb_upper.iloc[-1]
    bbl = bb_lower.iloc[-1]
    bbm = bb_mid.iloc[-1]
    bb_pct = (price - bbl) / (bbu - bbl + 1e-10)  # 0 = lower band, 1 = upper
    details["bollinger"] = {
        "upper": round(bbu, 4), "mid": round(bbm, 4),
        "lower": round(bbl, 4), "pct_b": round(bb_pct, 4),
    }
    if bb_pct < 0.1:
        signals.append(("bull", 1.5))   # price near lower band — potential bounce
    elif bb_pct > 0.9:
        signals.append(("bear", 1.5))   # price near upper band — potential reversal

    # ── Stochastic ────────────────────────────────────────────────────────────
    if "high" in df.columns and "low" in df.columns:
        k_val, d_val = stochastic(df)
        k_now = k_val.iloc[-1]
        d_now = d_val.iloc[-1]
        details["stochastic"] = {"k": round(k_now, 2), "d": round(d_now, 2)}
        if k_now < 20 and d_now < 20:
            signals.append(("bull", 1.5))
        elif k_now > 80 and d_now > 80:
            signals.append(("bear", 1.5))

    # ── Volatility ────────────────────────────────────────────────────────────
    hv    = historical_volatility(close).iloc[-1]
    atr_v = atr(df).iloc[-1] if "high" in df.columns else 0
    details["volatility"] = {
        "hist_vol_annualized": round(float(hv), 4) if not np.isnan(hv) else None,
        "atr": round(float(atr_v), 4) if atr_v else None,
    }

    # ── ADX (trend strength) ──────────────────────────────────────────────────
    if "high" in df.columns:
        adx_val = adx(df).iloc[-1]
        details["adx"] = round(float(adx_val), 2)
        # Strong trend — weight existing signals more
        if adx_val > 25:
            signals = [(d, w * 1.3) for d, w in signals]

    # ── Aggregate ─────────────────────────────────────────────────────────────
    bull_score = sum(w for d, w in signals if d == "bull")
    bear_score = sum(w for d, w in signals if d == "bear")
    total      = bull_score + bear_score or 1

    bull_pct = bull_score / total
    bear_pct = bear_score / total

    if bull_pct > 0.65:
        direction   = "bullish"
        confidence  = round(bull_pct, 3)
    elif bear_pct > 0.65:
        direction   = "bearish"
        confidence  = round(bear_pct, 3)
    else:
        direction   = "neutral"
        confidence  = round(max(bull_pct, bear_pct), 3)

    # Regime context
    if rsi_val < 30 and bb_pct < 0.15:
        regime = "oversold_extreme"
    elif rsi_val > 70 and bb_pct > 0.85:
        regime = "overbought_extreme"
    elif "adx" in details and details["adx"] > 30:
        regime = f"strong_{direction}_trend"
    else:
        regime = "ranging"

    return {
        "signal":     direction,
        "confidence": confidence,
        "bull_score": round(bull_score, 2),
        "bear_score": round(bear_score, 2),
        "regime":     regime,
        "price":      round(price, 6),
        "details":    details,
    }
