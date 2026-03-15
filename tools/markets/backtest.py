#!/usr/bin/env python3
"""
N.O.V.A Market Backtester

Tests how well technical + sentiment signals would have performed historically.
Uses walk-forward validation — trains on past, tests on future.

Strategy: enter on BUY/STRONG_BUY signal, exit on SELL/STRONG_SELL or N days.
Tracks: win rate, average return, max drawdown, Sharpe ratio.

Usage:
    nova markets backtest BTC --period 1y
    nova markets backtest ETH AAPL --period 6mo --horizon 7
"""
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

BASE       = Path.home() / "Nova"
BT_DIR     = BASE / "memory/markets/backtest"
BT_DIR.mkdir(parents=True, exist_ok=True)


def _signals_for_window(df_window: pd.DataFrame) -> dict:
    """Compute technical signal for a historical window."""
    from tools.markets.technicals import analyze
    from tools.markets.sentiment  import aggregate_sentiment, momentum_sentiment
    tech  = analyze(df_window)
    mom   = momentum_sentiment(df_window)
    sent  = aggregate_sentiment(fng=50, df=df_window)  # no live F&G in backtest
    return tech, sent


def backtest(symbol: str, df: pd.DataFrame,
             horizon: int = 7, lookback: int = 60,
             verbose: bool = True) -> dict:
    """
    Walk-forward backtest.
    At each step:
      1. Compute signal on last `lookback` candles
      2. Record entry price
      3. Check price after `horizon` days
      4. Mark trade as win/loss
    """
    if df.empty or len(df) < lookback + horizon + 10:
        return {"error": "insufficient data", "symbol": symbol}

    from tools.markets.technicals import analyze
    from tools.markets.sentiment  import aggregate_sentiment

    df = df.copy()
    close = pd.to_numeric(df["close"], errors="coerce").dropna().reset_index(drop=True)

    trades   = []
    step     = max(1, horizon // 2)  # step between signal checks

    for i in range(lookback, len(close) - horizon, step):
        window     = pd.DataFrame({"close": close[:i]})
        if "high" in df.columns:
            window["high"] = pd.to_numeric(df["high"], errors="coerce").iloc[:i].values
            window["low"]  = pd.to_numeric(df["low"],  errors="coerce").iloc[:i].values

        tech = analyze(window)
        if tech.get("error"):
            continue

        sent_score = 0.0  # neutral in backtest (no live F&G)
        tech_conf  = tech.get("confidence", 0.5)
        sig        = tech.get("signal", "neutral")
        tech_score = tech_conf if sig == "bullish" else (-tech_conf if sig == "bearish" else 0.0)
        conviction = round(0.6 * tech_score + 0.4 * sent_score, 4)

        if abs(conviction) < 0.3:   # skip weak signals
            continue

        direction  = "long" if conviction > 0 else "short"
        entry_price = float(close.iloc[i])
        exit_price  = float(close.iloc[min(i + horizon, len(close) - 1)])

        if entry_price <= 0:
            continue

        raw_return = (exit_price - entry_price) / entry_price
        trade_return = raw_return if direction == "long" else -raw_return

        trades.append({
            "index":       i,
            "direction":   direction,
            "conviction":  conviction,
            "entry":       round(entry_price, 6),
            "exit":        round(exit_price, 6),
            "return_pct":  round(trade_return * 100, 4),
            "win":         trade_return > 0,
        })

    if not trades:
        return {"symbol": symbol, "error": "no signals triggered", "trades": 0}

    returns    = [t["return_pct"] for t in trades]
    wins       = [t for t in trades if t["win"]]
    losses     = [t for t in trades if not t["win"]]
    avg_return = float(np.mean(returns))
    win_rate   = len(wins) / len(trades)
    avg_win    = float(np.mean([t["return_pct"] for t in wins])) if wins else 0
    avg_loss   = float(np.mean([t["return_pct"] for t in losses])) if losses else 0

    # Cumulative returns for drawdown
    cum = np.cumprod([1 + r / 100 for r in returns])
    peak     = np.maximum.accumulate(cum)
    drawdown = (cum - peak) / peak
    max_dd   = float(np.min(drawdown)) * 100

    # Sharpe ratio (annualized, assuming each trade = horizon days)
    trades_per_year = 365 / max(horizon, 1)
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = (avg_return / np.std(returns)) * np.sqrt(trades_per_year)
    else:
        sharpe = 0.0

    # Profit factor
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss   = abs(sum(r for r in returns if r < 0))
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else 999.0

    result = {
        "symbol":        symbol,
        "trades":        len(trades),
        "win_rate":      round(win_rate, 4),
        "avg_return_pct":round(avg_return, 4),
        "avg_win_pct":   round(avg_win, 4),
        "avg_loss_pct":  round(avg_loss, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "sharpe_ratio":  round(float(sharpe), 4),
        "profit_factor": profit_factor,
        "total_return_pct": round(float((cum[-1] - 1) * 100), 4),
        "horizon_days":  horizon,
        "lookback_candles": lookback,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }

    # Save
    ts  = datetime.now().strftime("%Y-%m-%d-%H%M")
    out = BT_DIR / f"backtest_{symbol}_{ts}.json"
    out.write_text(json.dumps({**result, "trades_detail": trades[-20:]}, indent=2))

    if verbose:
        _print_result(result)

    return result


def _print_result(r: dict) -> None:
    G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; C = "\033[36m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    wr  = r["win_rate"]
    ar  = r["avg_return_pct"]
    tot = r["total_return_pct"]
    sh  = r["sharpe_ratio"]
    dd  = r["max_drawdown_pct"]
    pf  = r["profit_factor"]

    wc = G if wr > 0.55 else (Y if wr > 0.45 else R)
    ac = G if ar > 0 else R
    tc = G if tot > 0 else R
    sc = G if sh > 1.0 else (Y if sh > 0.5 else R)
    dc = G if dd > -10 else (Y if dd > -20 else R)

    print(f"\n  {B}{W}{r['symbol']:6s}{NC}  {DIM}backtest ({r['trades']} trades, "
          f"horizon={r['horizon_days']}d){NC}")
    print(f"  Win rate:       {wc}{wr:.0%}{NC}  "
          f"Avg return: {ac}{ar:+.2f}%{NC}  "
          f"Total: {tc}{tot:+.1f}%{NC}")
    print(f"  Sharpe:         {sc}{sh:.2f}{NC}  "
          f"Max drawdown: {dc}{dd:.1f}%{NC}  "
          f"Profit factor: {C}{pf:.2f}{NC}")
    print(f"  Avg win: {G}{r['avg_win_pct']:+.2f}%{NC}  "
          f"Avg loss: {R}{r['avg_loss_pct']:+.2f}%{NC}")


def load_recent_results(symbol: str = None, n: int = 10) -> list[dict]:
    files = sorted(BT_DIR.glob("backtest_*.json"), reverse=True)[:n * 3]
    results = []
    for f in files:
        try:
            d = json.loads(f.read_text())
            if symbol and d.get("symbol") != symbol.upper():
                continue
            results.append(d)
            if len(results) >= n:
                break
        except Exception:
            pass
    return results
