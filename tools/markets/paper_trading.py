#!/usr/bin/env python3
"""
N.O.V.A Paper Trading Simulator

Tracks hypothetical positions with real price data.
No real money — but real discipline: position sizing, stop-losses, P&L.

Positions stored in memory/markets/paper_portfolio.json
Signal outcomes feed back into Bayesian accuracy tracking.

Usage:
    nova markets paper status
    nova markets paper buy BTC 0.05        # buy 0.05 BTC at current price
    nova markets paper sell BTC 0.05
    nova markets paper close BTC           # close entire BTC position
    nova markets paper history
"""
import json
from datetime import datetime, timezone
from pathlib import Path

BASE       = Path.home() / "Nova"
PORT_FILE  = BASE / "memory/markets/paper_portfolio.json"
TRADE_LOG  = BASE / "memory/markets/trade_log.jsonl"
PORT_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    if not PORT_FILE.exists():
        return {
            "cash_usd":   10000.0,  # starting paper capital
            "positions":  {},       # symbol → {qty, avg_price, stop_loss, entry_ts}
            "realized_pnl": 0.0,
            "trades":    0,
            "created":   datetime.now(timezone.utc).isoformat(),
        }
    try:
        return json.loads(PORT_FILE.read_text())
    except Exception:
        return _load.__wrapped__()  # shouldn't happen


def _save(data: dict) -> None:
    PORT_FILE.write_text(json.dumps(data, indent=2))


def _log_trade(entry: dict) -> None:
    with open(TRADE_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _get_price(symbol: str) -> float:
    from tools.markets.data import get_crypto_price, get_stock_price, CRYPTO_IDS
    sym = symbol.upper()
    if sym in CRYPTO_IDS:
        d = get_crypto_price(sym)
    else:
        d = get_stock_price(sym)
    return float(d.get("price_usd") or d.get("price", 0))


# ── Core operations ────────────────────────────────────────────────────────────

def buy(symbol: str, qty: float, stop_loss_pct: float = 0.05) -> dict:
    """Buy qty units of symbol at current market price."""
    symbol = symbol.upper()
    price  = _get_price(symbol)
    if price <= 0:
        return {"error": f"Could not get price for {symbol}"}

    cost = price * qty
    data = _load()

    if data["cash_usd"] < cost:
        return {"error": f"Insufficient cash (${data['cash_usd']:.2f} < ${cost:.2f})"}

    data["cash_usd"] -= cost
    pos = data["positions"].get(symbol, {"qty": 0.0, "avg_price": 0.0, "cost_basis": 0.0})

    # Average into position
    total_cost  = pos["cost_basis"] + cost
    total_qty   = pos["qty"] + qty
    avg_price   = total_cost / total_qty if total_qty > 0 else price

    data["positions"][symbol] = {
        "qty":        round(total_qty, 8),
        "avg_price":  round(avg_price, 6),
        "cost_basis": round(total_cost, 4),
        "stop_loss":  round(avg_price * (1 - stop_loss_pct), 6),
        "entry_ts":   datetime.now(timezone.utc).isoformat(),
    }
    data["trades"] += 1
    _save(data)

    trade = {
        "action": "BUY", "symbol": symbol, "qty": qty,
        "price": price, "cost": round(cost, 4),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _log_trade(trade)
    return {"ok": True, **trade}


def sell(symbol: str, qty: float = None) -> dict:
    """Sell qty units (or entire position if qty=None)."""
    symbol = symbol.upper()
    data   = _load()
    pos    = data["positions"].get(symbol)

    if not pos or pos.get("qty", 0) <= 0:
        return {"error": f"No position in {symbol}"}

    price    = _get_price(symbol)
    qty      = qty or pos["qty"]
    qty      = min(qty, pos["qty"])
    proceeds = price * qty
    cost     = pos["avg_price"] * qty
    pnl      = proceeds - cost
    pnl_pct  = (pnl / cost) * 100 if cost > 0 else 0

    data["cash_usd"]     += proceeds
    data["realized_pnl"] += pnl
    data["trades"]       += 1

    remaining = pos["qty"] - qty
    if remaining > 0.000001:
        data["positions"][symbol]["qty"] = round(remaining, 8)
        data["positions"][symbol]["cost_basis"] = round(pos["cost_basis"] - cost, 4)
    else:
        del data["positions"][symbol]

    _save(data)

    trade = {
        "action": "SELL", "symbol": symbol, "qty": qty,
        "price": price, "proceeds": round(proceeds, 4),
        "pnl": round(pnl, 4), "pnl_pct": round(pnl_pct, 4),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _log_trade(trade)

    # Feed outcome into signal Bayesian tracker
    try:
        from tools.learning.outcome_tracker import mark_outcome
        outcome = "confirmed" if pnl > 0 else "false_positive"
        mark_outcome(f"market_{symbol}_{trade['ts'][:10]}", outcome,
                     note=f"paper trade P&L: {pnl_pct:+.1f}%")
    except Exception:
        pass

    return {"ok": True, **trade}


def check_stops() -> list[dict]:
    """Check all positions against stop-losses. Return list of triggered stops."""
    data     = _load()
    triggered = []
    for sym, pos in list(data["positions"].items()):
        try:
            price = _get_price(sym)
            if price <= pos.get("stop_loss", 0):
                result = sell(sym)
                result["reason"] = "stop_loss"
                triggered.append(result)
        except Exception:
            pass
    return triggered


def portfolio_value() -> dict:
    """Current portfolio value including unrealized P&L."""
    data     = _load()
    pos_val  = 0.0
    positions_detail = []

    for sym, pos in data["positions"].items():
        try:
            price    = _get_price(sym)
            mkt_val  = price * pos["qty"]
            cost     = pos["cost_basis"]
            unreal   = mkt_val - cost
            unreal_p = (unreal / cost * 100) if cost > 0 else 0
            pos_val += mkt_val
            positions_detail.append({
                "symbol":    sym,
                "qty":       pos["qty"],
                "avg_price": pos["avg_price"],
                "current":   round(price, 6),
                "mkt_value": round(mkt_val, 4),
                "unreal_pnl":round(unreal, 4),
                "unreal_pct":round(unreal_p, 4),
                "stop_loss": pos.get("stop_loss", 0),
            })
        except Exception:
            pass

    total    = data["cash_usd"] + pos_val
    start    = 10000.0
    total_return = (total - start) / start * 100

    return {
        "cash_usd":      round(data["cash_usd"], 4),
        "positions_val": round(pos_val, 4),
        "total_val":     round(total, 4),
        "realized_pnl":  round(data["realized_pnl"], 4),
        "total_return_pct": round(total_return, 4),
        "trades":        data["trades"],
        "positions":     positions_detail,
    }


def trade_history(n: int = 20) -> list[dict]:
    if not TRADE_LOG.exists():
        return []
    lines = TRADE_LOG.read_text().strip().splitlines()
    trades = []
    for line in lines[-n:]:
        try:
            trades.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(trades))


def reset(confirm: bool = False) -> str:
    if not confirm:
        return "Pass confirm=True to reset portfolio to $10,000"
    PORT_FILE.unlink(missing_ok=True)
    return "Portfolio reset to $10,000 paper cash."
