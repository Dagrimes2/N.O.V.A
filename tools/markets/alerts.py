#!/usr/bin/env python3
"""
N.O.V.A Price Alert System

Set target prices — Nova checks every cycle and fires Telegram + TTS when hit.
Alerts persist across restarts. One-shot (fires once, then removes itself).

Usage:
    nova markets alert add BTC 65000 below    — alert when BTC drops below $65k
    nova markets alert add ETH 3000 above     — alert when ETH exceeds $3k
    nova markets alert list
    nova markets alert remove BTC
    nova markets alert check                  — check all alerts now
"""
import json
from datetime import datetime, timezone
from pathlib import Path

BASE        = Path.home() / "Nova"
ALERTS_FILE = BASE / "memory/markets/price_alerts.json"
ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> list[dict]:
    if not ALERTS_FILE.exists():
        return []
    try:
        return json.loads(ALERTS_FILE.read_text())
    except Exception:
        return []


def _save(alerts: list[dict]) -> None:
    ALERTS_FILE.write_text(json.dumps(alerts, indent=2))


def add_alert(symbol: str, target: float, direction: str = "below") -> dict:
    """
    Add a price alert.
    direction: 'above' (alert when price goes above target)
               'below' (alert when price drops below target)
    """
    symbol    = symbol.upper()
    direction = direction.lower()
    if direction not in ("above", "below"):
        return {"error": "direction must be 'above' or 'below'"}

    alerts = _load()
    # Remove existing alert for same symbol+direction
    alerts = [a for a in alerts
              if not (a["symbol"] == symbol and a["direction"] == direction)]
    alerts.append({
        "symbol":    symbol,
        "target":    target,
        "direction": direction,
        "created":   datetime.now(timezone.utc).isoformat(),
        "triggered": False,
    })
    _save(alerts)
    return {"ok": True, "symbol": symbol, "target": target, "direction": direction}


def remove_alert(symbol: str, direction: str = None) -> int:
    """Remove alert(s) for a symbol. Returns count removed."""
    symbol = symbol.upper()
    alerts = _load()
    before = len(alerts)
    if direction:
        alerts = [a for a in alerts
                  if not (a["symbol"] == symbol and a["direction"] == direction)]
    else:
        alerts = [a for a in alerts if a["symbol"] != symbol]
    _save(alerts)
    return before - len(alerts)


def check_alerts(verbose: bool = True) -> list[dict]:
    """
    Check all active alerts against current prices.
    Fires notifications for triggered alerts and removes them.
    """
    from tools.markets.data import get_crypto_price, get_stock_price, CRYPTO_IDS

    alerts    = _load()
    triggered = []
    remaining = []

    for alert in alerts:
        if alert.get("triggered"):
            continue

        sym    = alert["symbol"]
        target = alert["target"]
        dirn   = alert["direction"]

        try:
            if sym in CRYPTO_IDS:
                p = get_crypto_price(sym)
            else:
                p = get_stock_price(sym)
            price = float(p.get("price_usd") or p.get("price", 0))
        except Exception:
            remaining.append(alert)
            continue

        hit = (dirn == "below" and price <= target) or \
              (dirn == "above" and price >= target)

        if hit:
            alert["triggered"]    = True
            alert["triggered_at"] = datetime.now(timezone.utc).isoformat()
            alert["price_at"]     = price
            triggered.append(alert)

            msg = (f"🚨 Price Alert: {sym} is ${price:,.4g} — "
                   f"{'below' if dirn=='below' else 'above'} target ${target:,.4g}")

            if verbose:
                col = "\033[32m" if dirn == "above" else "\033[31m"
                print(f"  {col}{msg}\033[0m")

            # Telegram
            try:
                from tools.notify.telegram import send
                send(msg)
            except Exception:
                pass

            # TTS
            try:
                from tools.notify.tts import speak
                speak(f"Price alert: {sym} has reached {price:,.0f} dollars")
            except Exception:
                pass
        else:
            remaining.append(alert)

    # Keep untriggered alerts
    _save(remaining)
    return triggered


def list_alerts() -> list[dict]:
    return _load()


def main():
    import sys
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "list"

    if cmd == "add" and len(args) >= 3:
        sym    = args[1].upper()
        target = float(args[2])
        dirn   = args[3] if len(args) > 3 else "below"
        r = add_alert(sym, target, dirn)
        if r.get("ok"):
            col = G if dirn == "above" else R
            print(f"{col}Alert set: {sym} {dirn} ${target:,.4g}{NC}")
        else:
            print(f"{R}{r.get('error')}{NC}")

    elif cmd == "remove" and len(args) >= 2:
        n = remove_alert(args[1], args[2] if len(args) > 2 else None)
        print(f"{G}{n} alert(s) removed.{NC}" if n else f"{DIM}No alerts found.{NC}")

    elif cmd == "list":
        alerts = list_alerts()
        if not alerts:
            print(f"{DIM}No active alerts.{NC}")
            return
        print(f"\n{B}Active Price Alerts{NC}")
        for a in alerts:
            dirn = a["direction"]
            col  = G if dirn == "above" else R
            print(f"  {col}{a['symbol']:6s}{NC} {dirn:5s} ${a['target']:>12,.4g}  "
                  f"{DIM}set {a['created'][:10]}{NC}")

    elif cmd == "check":
        triggered = check_alerts(verbose=True)
        if not triggered:
            print(f"{DIM}No alerts triggered.{NC}")
        else:
            print(f"{G}{len(triggered)} alert(s) triggered.{NC}")

    else:
        print("Usage: nova markets alert [add SYM TARGET above|below | remove SYM | list | check]")


if __name__ == "__main__":
    main()
