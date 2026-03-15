#!/usr/bin/env python3
"""
N.O.V.A Market Signal Engine

Combines technical analysis + sentiment into weighted conviction scores.
Uses QRNG-powered Monte Carlo for risk-adjusted probability estimates.

Output per asset:
  - conviction:  -1.0 (strong sell) to +1.0 (strong buy)
  - probability: estimated P(price higher in N days)
  - risk_score:  volatility-adjusted position risk (0-1)
  - action:      STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL
  - context:     human-readable rationale

IMPORTANT: This is probabilistic analysis, not prophecy.
Markets can do anything. Use position sizing + stop losses always.
"""
import json
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

BASE      = Path.home() / "Nova"
SIGNAL_DIR = BASE / "memory/markets/signals"
SIGNAL_DIR.mkdir(parents=True, exist_ok=True)

# Conviction thresholds
STRONG_BUY   =  0.65
BUY          =  0.35
SELL         = -0.35
STRONG_SELL  = -0.65


def _qrand_sample(n: int = 1000) -> np.ndarray:
    """Get random samples — quantum if available, os.urandom fallback."""
    try:
        import sys
        sys.path.insert(0, str(BASE))
        from tools.learning.qrng import qrand
        return np.array([qrand() for _ in range(n)])
    except Exception:
        return np.random.random(n)


def monte_carlo_probability(
    current_price: float,
    volatility: float,
    drift: float,
    days: int = 7,
    simulations: int = 1000,
) -> dict:
    """
    Monte Carlo simulation for price probability distribution.
    Uses geometric Brownian motion with QRNG noise.

    drift    : expected daily return (from momentum analysis)
    volatility: daily historical volatility
    Returns P(price > current) + percentile estimates
    """
    if volatility <= 0 or current_price <= 0:
        return {"p_up": 0.5, "p5": current_price, "p50": current_price, "p95": current_price}

    # Get QRNG random samples for GBM noise
    randoms = _qrand_sample(simulations * days).reshape(simulations, days)

    # Convert uniform → normal via Box-Muller
    u1 = randoms[:, :days // 2 * 2:2] + 1e-10
    u2 = randoms[:, 1:days // 2 * 2:2]
    z  = np.sqrt(-2 * np.log(u1)) * np.cos(2 * np.pi * u2)
    # Pad if days is odd
    if z.shape[1] < days:
        z = np.hstack([z, z[:, :1]])
    z = z[:, :days]

    # GBM: S_t = S_0 * exp((μ - σ²/2)t + σ√t * Z)
    daily_returns = (drift - 0.5 * volatility ** 2) + volatility * z
    log_prices    = np.log(current_price) + np.cumsum(daily_returns, axis=1)
    final_prices  = np.exp(log_prices[:, -1])

    p_up = float(np.mean(final_prices > current_price))
    return {
        "p_up":         round(p_up, 4),
        "p_down":       round(1 - p_up, 4),
        "p5":           round(float(np.percentile(final_prices, 5)), 6),
        "p25":          round(float(np.percentile(final_prices, 25)), 6),
        "p50":          round(float(np.percentile(final_prices, 50)), 6),
        "p75":          round(float(np.percentile(final_prices, 75)), 6),
        "p95":          round(float(np.percentile(final_prices, 95)), 6),
        "expected":     round(float(np.mean(final_prices)), 6),
        "simulations":  simulations,
    }


def compute_signal(
    symbol: str,
    technicals: dict,
    sentiment: dict,
    price_data: dict = None,
    days_horizon: int = 7,
) -> dict:
    """
    Combine technicals + sentiment into a final conviction signal.

    technicals : output from tools.markets.technicals.analyze()
    sentiment  : output from tools.markets.sentiment.aggregate_sentiment()
    price_data : current price info from data.get_*_price()
    """
    if technicals.get("error"):
        return {"symbol": symbol, "error": technicals["error"], "action": "HOLD",
                "conviction": 0.0}

    # ── Technical conviction: -1 to +1 ────────────────────────────────────────
    tech_conf = technicals.get("confidence", 0.5)
    sig       = technicals.get("signal", "neutral")
    if sig == "bullish":
        tech_score = tech_conf
    elif sig == "bearish":
        tech_score = -tech_conf
    else:
        tech_score = 0.0

    # ── Sentiment conviction ───────────────────────────────────────────────────
    sent_score = sentiment.get("score", 0.0)

    # ── Blended conviction (60% technicals, 40% sentiment) ────────────────────
    conviction = round(0.6 * tech_score + 0.4 * sent_score, 4)

    # ── Action label ──────────────────────────────────────────────────────────
    if conviction >= STRONG_BUY:
        action = "STRONG_BUY"
    elif conviction >= BUY:
        action = "BUY"
    elif conviction <= STRONG_SELL:
        action = "STRONG_SELL"
    elif conviction <= SELL:
        action = "SELL"
    else:
        action = "HOLD"

    # ── Monte Carlo probability ────────────────────────────────────────────────
    mc = {}
    try:
        details  = technicals.get("details", {})
        hv_dict  = details.get("volatility", {})
        hv_ann   = hv_dict.get("hist_vol_annualized") or 0.4  # default 40% if unknown
        daily_vol   = hv_ann / np.sqrt(252)
        daily_drift = conviction * 0.005  # implied daily drift from conviction

        current_price = (price_data or {}).get("price_usd") or technicals.get("price", 1.0)
        mc = monte_carlo_probability(
            current_price=float(current_price),
            volatility=float(daily_vol),
            drift=float(daily_drift),
            days=days_horizon,
            simulations=2000,
        )
    except Exception as e:
        mc = {"p_up": 0.5, "error": str(e)}

    # ── Risk score ────────────────────────────────────────────────────────────
    hv = (technicals.get("details", {}).get("volatility", {}) or {}).get("hist_vol_annualized") or 0.4
    # Higher volatility + lower confidence = higher risk
    risk_score = round(min(1.0, float(hv) * (1 - abs(conviction))), 4)

    # ── Rationale ─────────────────────────────────────────────────────────────
    rsi_v  = technicals.get("details", {}).get("rsi", 50)
    regime = technicals.get("regime", "")
    fng    = sentiment.get("components", {}).get("fear_greed", {}).get("raw", 50)
    fng_l  = sentiment.get("label", "neutral")

    rationale_parts = [
        f"RSI={rsi_v:.0f}",
        f"regime={regime}",
        f"sentiment={fng_l}(F&G:{fng})",
        f"P(up {days_horizon}d)={mc.get('p_up', 0.5):.0%}",
    ]
    context = f"{sig.upper()} — " + "  ".join(rationale_parts)

    result = {
        "symbol":       symbol,
        "action":       action,
        "conviction":   conviction,
        "risk_score":   risk_score,
        "technical":    {"signal": sig, "score": round(tech_score, 4), "regime": regime},
        "sentiment":    {"score": round(sent_score, 4), "label": fng_l},
        "monte_carlo":  mc,
        "context":      context,
        "horizon_days": days_horizon,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }

    # Save signal
    ts  = datetime.now().strftime("%Y-%m-%d-%H%M")
    out = SIGNAL_DIR / f"signal_{symbol}_{ts}.json"
    out.write_text(json.dumps(result, indent=2))

    return result


def action_color(action: str) -> str:
    """ANSI color for terminal display."""
    colors = {
        "STRONG_BUY":  "\033[92m",  # bright green
        "BUY":         "\033[32m",  # green
        "HOLD":        "\033[33m",  # yellow
        "SELL":        "\033[31m",  # red
        "STRONG_SELL": "\033[91m",  # bright red
    }
    return colors.get(action, "\033[37m")
