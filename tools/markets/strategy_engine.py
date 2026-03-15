#!/usr/bin/env python3
"""
N.O.V.A Strategy Engine

Nova develops trading strategies autonomously:
  1. Generate — LLM proposes a strategy based on market observations
  2. Backtest — test against historical price data (fetched from CoinGecko free API)
  3. Paper trade — run live paper trades for 30+ days
  4. Propose — if paper results are good, propose to Travis via agency system

Strategies are simple rule-based systems Nova can actually reason about:
  - Moving average crossover (fast MA crosses above slow MA → buy)
  - RSI oversold/overbought (RSI < 30 → buy, RSI > 70 → sell)
  - Momentum (price up X% in N days → buy, stop-loss at Y%)
  - Mean reversion (price down X% from recent high → buy)

Nova never executes real trades. All live activity is paper trading.
Going live requires explicit Travis approval via: nova agency approve <id>
"""
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE            = Path.home() / "Nova"
STRAT_DIR       = BASE / "memory/strategies"
INDEX_FILE      = STRAT_DIR / "index.json"
CACHE_FILE      = STRAT_DIR / "backtest_cache.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("reasoning")
    TIMEOUT    = cfg.timeout("standard")
    TEMP       = 0.3
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 180
    TEMP       = 0.3

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
CACHE_TTL_HOURS = 6
PAPER_MIN_DAYS  = 30
PAPER_MIN_RETURN = 5.0
PAPER_MIN_WINRATE = 0.5


# ── Storage helpers ────────────────────────────────────────────────────────────

def _ensure_dirs():
    STRAT_DIR.mkdir(parents=True, exist_ok=True)


def _load_index() -> dict:
    _ensure_dirs()
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except Exception:
            pass
    return {"strategies": {}}


def _save_index(idx: dict):
    _ensure_dirs()
    INDEX_FILE.write_text(json.dumps(idx, indent=2))


def _load_strategy(strategy_id: str) -> dict | None:
    _ensure_dirs()
    f = STRAT_DIR / f"{strategy_id}.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return None


def _save_strategy(strategy: dict):
    _ensure_dirs()
    sid = strategy["id"]
    (STRAT_DIR / f"{sid}.json").write_text(json.dumps(strategy, indent=2))


def _load_cache() -> dict:
    _ensure_dirs()
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(cache: dict):
    _ensure_dirs()
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


# ── CoinGecko fetch ────────────────────────────────────────────────────────────

def _fetch_prices(symbol: str, days: int = 90) -> list[dict]:
    """
    Fetch historical daily prices from CoinGecko free API.
    Returns list of {"ts": ISO, "price": float, "volume": float}.
    Results cached in backtest_cache.json for CACHE_TTL_HOURS hours.
    """
    cache_key = f"{symbol}_{days}"
    cache = _load_cache()

    if cache_key in cache:
        entry = cache[cache_key]
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
        if age_hours < CACHE_TTL_HOURS:
            return entry["data"]

    url = (
        f"{COINGECKO_BASE}/coins/{symbol}/market_chart"
        f"?vs_currency=usd&days={days}&interval=daily"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NOVA/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  [strategy_engine] CoinGecko HTTP {e.code} for {symbol}")
        return []
    except Exception as e:
        print(f"  [strategy_engine] CoinGecko fetch error: {e}")
        return []

    prices_raw  = raw.get("prices", [])
    volumes_raw = raw.get("total_volumes", [])

    vol_map = {v[0]: v[1] for v in volumes_raw}
    result  = []
    for ts_ms, price in prices_raw:
        result.append({
            "ts":     datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
            "price":  float(price),
            "volume": float(vol_map.get(ts_ms, 0.0)),
        })

    if result:
        cache[cache_key] = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data":       result,
        }
        _save_cache(cache)

    return result


def _fetch_current_price(symbol: str) -> float:
    """Fetch current price for a single symbol (uses 1-day chart for freshness)."""
    data = _fetch_prices(symbol, days=1)
    if data:
        return data[-1]["price"]
    return 0.0


# ── Technical indicators ───────────────────────────────────────────────────────

def _calc_rsi(prices: list[float], period: int = 14) -> list[float]:
    """
    Calculate RSI from price list.
    Returns list of same length as prices; first `period` entries are NaN.
    """
    n = len(prices)
    rsi = [float("nan")] * n
    if n < period + 1:
        return rsi

    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def _rsi_from(ag, al):
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    rsi[period] = _rsi_from(avg_gain, avg_loss)

    for i in range(period + 1, n):
        delta = prices[i] - prices[i - 1]
        gain  = max(delta, 0.0)
        loss  = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rsi[i] = _rsi_from(avg_gain, avg_loss)

    return rsi


def _calc_ma(prices: list[float], period: int) -> list[float]:
    """Simple moving average. First (period-1) values are NaN."""
    n   = len(prices)
    ma  = [float("nan")] * n
    for i in range(period - 1, n):
        ma[i] = sum(prices[i - period + 1 : i + 1]) / period
    return ma


# ── Backtesting ────────────────────────────────────────────────────────────────

def _backtest_strategy(strategy: dict, prices: list[dict]) -> dict:
    """
    Simulate strategy on historical prices starting with $1000 virtual capital.
    Returns {"return_pct", "win_rate", "max_drawdown", "trades", "equity_curve"}.
    """
    if len(prices) < 20:
        return {
            "return_pct": 0.0, "win_rate": 0.0,
            "max_drawdown": 0.0, "trades": 0,
            "equity_curve": [], "error": "insufficient data",
        }

    price_vals  = [p["price"] for p in prices]
    n           = len(price_vals)
    stype       = strategy.get("type", "rsi")
    params      = strategy.get("params", {})

    capital      = 1000.0
    in_position  = False
    entry_price  = 0.0
    wins         = 0
    losses       = 0
    equity_curve = [capital]
    peak_equity  = capital
    max_drawdown = 0.0

    # Pre-compute indicators
    if stype == "rsi":
        period    = int(params.get("rsi_period", 14))
        oversold  = float(params.get("oversold", 30))
        overbought = float(params.get("overbought", 70))
        rsi_vals  = _calc_rsi(price_vals, period)

    elif stype == "ma_crossover":
        fast = int(params.get("fast", 7))
        slow = int(params.get("slow", 21))
        fast_ma = _calc_ma(price_vals, fast)
        slow_ma = _calc_ma(price_vals, slow)

    elif stype == "momentum":
        lookback  = int(params.get("lookback", 7))
        threshold = float(params.get("threshold", 5.0))
        stop_loss = float(params.get("stop_loss", 5.0))

    elif stype == "mean_reversion":
        window    = int(params.get("window", 20))
        drop_pct  = float(params.get("drop", 10.0))
        stop_loss = float(params.get("stop_loss", 5.0))

    def _register_sell(buy_p, sell_p):
        nonlocal capital, wins, losses
        pnl_pct = (sell_p - buy_p) / buy_p
        capital  = capital * (1.0 + pnl_pct)
        if pnl_pct > 0:
            wins += 1
        else:
            losses += 1

    for i in range(1, n):
        price = price_vals[i]
        signal = None

        if stype == "rsi":
            cur  = rsi_vals[i]
            prev = rsi_vals[i - 1]
            if math.isnan(cur) or math.isnan(prev):
                pass
            elif not in_position and prev >= oversold and cur < oversold:
                signal = "BUY"
            elif in_position and prev <= overbought and cur > overbought:
                signal = "SELL"

        elif stype == "ma_crossover":
            cf = fast_ma[i];     pf = fast_ma[i - 1]
            cs = slow_ma[i];     ps = slow_ma[i - 1]
            if any(math.isnan(v) for v in [cf, pf, cs, ps]):
                pass
            elif not in_position and pf <= ps and cf > cs:
                signal = "BUY"
            elif in_position and pf >= ps and cf < cs:
                signal = "SELL"

        elif stype == "momentum":
            if i >= lookback:
                past  = price_vals[i - lookback]
                chg   = (price - past) / past * 100
                if not in_position and chg > threshold:
                    signal = "BUY"
                elif in_position:
                    drawdown = (price - entry_price) / entry_price * 100
                    if drawdown < -stop_loss:
                        signal = "SELL"

        elif stype == "mean_reversion":
            if i >= window:
                recent_high = max(price_vals[i - window : i])
                drop = (recent_high - price) / recent_high * 100
                if not in_position and drop > drop_pct:
                    signal = "BUY"
                elif in_position:
                    drawdown = (price - entry_price) / entry_price * 100
                    if drawdown < -stop_loss or price >= recent_high:
                        signal = "SELL"

        if signal == "BUY" and not in_position:
            in_position = True
            entry_price = price

        elif signal == "SELL" and in_position:
            _register_sell(entry_price, price)
            in_position = False
            entry_price = 0.0

        # Close open position at end
        if i == n - 1 and in_position:
            _register_sell(entry_price, price)
            in_position = False

        equity_curve.append(round(capital, 4))
        if capital > peak_equity:
            peak_equity = capital
        dd = (capital - peak_equity) / peak_equity * 100
        if dd < max_drawdown:
            max_drawdown = dd

    total_trades = wins + losses
    win_rate     = (wins / total_trades) if total_trades > 0 else 0.0
    return_pct   = (capital - 1000.0) / 1000.0 * 100

    return {
        "return_pct":    round(return_pct, 4),
        "win_rate":      round(win_rate, 4),
        "max_drawdown":  round(max_drawdown, 4),
        "trades":        total_trades,
        "equity_curve":  equity_curve[-30:],  # keep last 30 points
    }


# ── LLM strategy generation ────────────────────────────────────────────────────

def generate_strategy(symbol: str = "bitcoin") -> dict:
    """
    Use LLM to propose a new strategy for the given symbol.
    Returns strategy dict ready for adding and backtesting.
    """
    prompt = (
        f"You are Nova's strategy engine. Propose a simple rule-based trading "
        f"strategy for {symbol}. Choose one type from: rsi, ma_crossover, "
        f"momentum, mean_reversion.\n\n"
        f"For rsi use params: rsi_period (int), oversold (float), overbought (float).\n"
        f"For ma_crossover use params: fast (int), slow (int).\n"
        f"For momentum use params: lookback (int days), threshold (float %), stop_loss (float %).\n"
        f"For mean_reversion use params: window (int days), drop (float %), stop_loss (float %).\n\n"
        f"Respond with JSON only, no markdown, no explanation:\n"
        f'{{ "type": "...", "name": "...", "params": {{}}, "rationale": "..." }}'
    )

    payload = json.dumps({
        "model":  MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": TEMP},
    }).encode()

    raw_response = ""
    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw_response = json.loads(resp.read().decode()).get("response", "")
    except Exception as e:
        print(f"  [strategy_engine] LLM error: {e} — using RSI fallback")

    # Parse LLM response
    proposed = {}
    if raw_response:
        # Strip markdown fences if present
        text = raw_response.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break
        # Find JSON object
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                proposed = json.loads(text[start:end])
            except Exception:
                pass

    # Fallback if parse failed
    if not proposed or "type" not in proposed:
        proposed = {
            "type":      "rsi",
            "name":      f"{symbol.upper()} RSI Mean Reversion",
            "params":    {"rsi_period": 14, "oversold": 30, "overbought": 70},
            "rationale": (
                f"RSI mean reversion on {symbol} exploits short-term oversold "
                f"conditions that historically precede price recovery."
            ),
        }

    # Validate and normalise params
    stype  = proposed.get("type", "rsi")
    params = proposed.get("params", {})
    _DEFAULTS_PARAMS = {
        "rsi":            {"rsi_period": 14, "oversold": 30, "overbought": 70},
        "ma_crossover":   {"fast": 7,  "slow": 21},
        "momentum":       {"lookback": 7, "threshold": 5.0, "stop_loss": 5.0},
        "mean_reversion": {"window": 20, "drop": 10.0, "stop_loss": 5.0},
    }
    if stype not in _DEFAULTS_PARAMS:
        stype  = "rsi"
        params = {}
    defaults = _DEFAULTS_PARAMS[stype]
    for k, v in defaults.items():
        if k not in params:
            params[k] = v

    now = datetime.now(timezone.utc)
    return {
        "id":              "",   # assigned by add_strategy
        "name":            proposed.get("name", f"{symbol.upper()} {stype}"),
        "type":            stype,
        "symbol":          symbol.lower(),
        "params":          params,
        "created":         now.isoformat(),
        "status":          "generated",
        "backtest":        {},
        "paper_trades":    [],
        "paper_start":     None,
        "paper_return_pct": 0.0,
        "nova_rationale":  proposed.get("rationale", ""),
        "proposal_id":     None,
    }


# ── Index management ───────────────────────────────────────────────────────────

def add_strategy(strategy: dict) -> str:
    """Add strategy to index, return strategy_id."""
    idx = _load_index()
    now = datetime.now(timezone.utc)
    date_tag = now.strftime("%Y%m%d")

    # Generate sequential ID for the day
    existing = [k for k in idx["strategies"] if k.startswith(f"strat_{date_tag}")]
    seq = len(existing) + 1
    sid = f"strat_{date_tag}_{seq:03d}"

    strategy["id"] = sid
    idx["strategies"][sid] = {
        "name":    strategy["name"],
        "type":    strategy["type"],
        "symbol":  strategy["symbol"],
        "status":  strategy["status"],
        "created": strategy["created"],
    }
    _save_index(idx)
    _save_strategy(strategy)
    return sid


# ── Backtest ───────────────────────────────────────────────────────────────────

def backtest(strategy_id: str) -> dict:
    """Fetch prices and run backtest for strategy. Updates strategy's backtest field."""
    strat = _load_strategy(strategy_id)
    if strat is None:
        return {"error": f"Strategy {strategy_id} not found"}

    print(f"  [strategy_engine] Fetching prices for {strat['symbol']} (90 days)...")
    prices = _fetch_prices(strat["symbol"], days=90)
    if not prices:
        return {"error": "Could not fetch price data"}

    print(f"  [strategy_engine] Running backtest on {len(prices)} data points...")
    results = _backtest_strategy(strat, prices)

    strat["backtest"] = {
        "return_pct":   results["return_pct"],
        "win_rate":     results["win_rate"],
        "max_drawdown": results["max_drawdown"],
        "trades":       results["trades"],
        "equity_curve": results.get("equity_curve", []),
        "run_at":       datetime.now(timezone.utc).isoformat(),
        "data_points":  len(prices),
    }
    if results.get("error"):
        strat["backtest"]["error"] = results["error"]

    strat["status"] = "backtested"

    _save_strategy(strat)

    # Update index status
    idx = _load_index()
    if strategy_id in idx["strategies"]:
        idx["strategies"][strategy_id]["status"] = "backtested"
        _save_index(idx)

    return strat["backtest"]


# ── Paper trading ──────────────────────────────────────────────────────────────

def start_paper_trading(strategy_id: str) -> bool:
    """Mark strategy as paper_trading, set paper_start date."""
    strat = _load_strategy(strategy_id)
    if strat is None:
        print(f"  [strategy_engine] Strategy {strategy_id} not found")
        return False

    strat["status"]      = "paper_trading"
    strat["paper_start"] = datetime.now(timezone.utc).isoformat()
    strat["paper_trades"] = strat.get("paper_trades", [])

    _save_strategy(strat)

    idx = _load_index()
    if strategy_id in idx["strategies"]:
        idx["strategies"][strategy_id]["status"] = "paper_trading"
        _save_index(idx)

    return True


def _calc_paper_return(trades: list[dict]) -> float:
    """Calculate cumulative return % from paper trade log."""
    capital = 1000.0
    in_pos  = False
    entry   = 0.0
    for t in trades:
        action = t.get("action", "HOLD")
        price  = t.get("price", 0.0)
        if action == "BUY" and not in_pos and price > 0:
            in_pos = True
            entry  = price
        elif action == "SELL" and in_pos and price > 0 and entry > 0:
            pnl     = (price - entry) / entry
            capital = capital * (1.0 + pnl)
            in_pos  = False
            entry   = 0.0
    return round((capital - 1000.0) / 1000.0 * 100, 4)


def _paper_win_rate(trades: list[dict]) -> float:
    """Win rate from paper trade log (closed trades only)."""
    wins = 0
    total = 0
    for t in trades:
        pnl = t.get("pnl_pct")
        if pnl is not None:
            total += 1
            if pnl > 0:
                wins += 1
    return round(wins / total, 4) if total > 0 else 0.0


def update_paper_trades(strategy_id: str = None) -> list[str]:
    """
    Check current prices for all (or one) paper-trading strategies and execute signals.
    Records trade entries. Returns list of action strings taken.
    """
    idx     = _load_index()
    actions = []

    candidates = []
    if strategy_id:
        if strategy_id in idx["strategies"] and idx["strategies"][strategy_id]["status"] == "paper_trading":
            candidates = [strategy_id]
        else:
            return [f"Strategy {strategy_id} is not paper trading"]
    else:
        candidates = [
            sid for sid, meta in idx["strategies"].items()
            if meta.get("status") == "paper_trading"
        ]

    for sid in candidates:
        strat = _load_strategy(sid)
        if strat is None:
            continue

        symbol = strat["symbol"]
        price  = _fetch_current_price(symbol)
        if price <= 0:
            actions.append(f"{symbol.upper()}: could not fetch price")
            continue

        paper_trades = strat.get("paper_trades", [])
        stype  = strat.get("type", "rsi")
        params = strat.get("params", {})
        ts_now = datetime.now(timezone.utc).isoformat()

        # Determine if currently in position
        in_pos     = False
        entry_price = 0.0
        for t in paper_trades:
            if t["action"] == "BUY":
                in_pos = True
                entry_price = t["price"]
            elif t["action"] == "SELL":
                in_pos = False
                entry_price = 0.0

        # Fetch recent prices to compute indicators
        recent = _fetch_prices(symbol, days=30)
        if not recent:
            actions.append(f"{symbol.upper()}: no recent price data")
            continue

        recent_prices = [r["price"] for r in recent]
        # Append current price as latest candle
        recent_prices.append(price)

        signal = "HOLD"

        if stype == "rsi":
            period     = int(params.get("rsi_period", 14))
            oversold   = float(params.get("oversold", 30))
            overbought = float(params.get("overbought", 70))
            rsi_vals   = _calc_rsi(recent_prices, period)
            if len(rsi_vals) >= 2:
                cur  = rsi_vals[-1]
                prev = rsi_vals[-2]
                if not (math.isnan(cur) or math.isnan(prev)):
                    if not in_pos and prev >= oversold and cur < oversold:
                        signal = "BUY"
                    elif in_pos and prev <= overbought and cur > overbought:
                        signal = "SELL"

        elif stype == "ma_crossover":
            fast = int(params.get("fast", 7))
            slow = int(params.get("slow", 21))
            fm   = _calc_ma(recent_prices, fast)
            sm   = _calc_ma(recent_prices, slow)
            if len(fm) >= 2 and len(sm) >= 2:
                cf, pf = fm[-1], fm[-2]
                cs, ps = sm[-1], sm[-2]
                if not any(math.isnan(v) for v in [cf, pf, cs, ps]):
                    if not in_pos and pf <= ps and cf > cs:
                        signal = "BUY"
                    elif in_pos and pf >= ps and cf < cs:
                        signal = "SELL"

        elif stype == "momentum":
            lookback  = int(params.get("lookback", 7))
            threshold = float(params.get("threshold", 5.0))
            stop_loss = float(params.get("stop_loss", 5.0))
            if len(recent_prices) > lookback:
                past = recent_prices[-(lookback + 1)]
                chg  = (price - past) / past * 100
                if not in_pos and chg > threshold:
                    signal = "BUY"
                elif in_pos and entry_price > 0:
                    dd = (price - entry_price) / entry_price * 100
                    if dd < -stop_loss:
                        signal = "SELL"

        elif stype == "mean_reversion":
            window    = int(params.get("window", 20))
            drop_pct  = float(params.get("drop", 10.0))
            stop_loss = float(params.get("stop_loss", 5.0))
            if len(recent_prices) > window:
                high = max(recent_prices[-window:])
                drop = (high - price) / high * 100
                if not in_pos and drop > drop_pct:
                    signal = "BUY"
                elif in_pos and entry_price > 0:
                    dd = (price - entry_price) / entry_price * 100
                    if dd < -stop_loss or price >= high:
                        signal = "SELL"

        # Build trade entry
        pnl_pct = None
        if signal == "SELL" and in_pos and entry_price > 0:
            pnl_pct = round((price - entry_price) / entry_price * 100, 4)

        trade_entry = {
            "ts":      ts_now,
            "action":  signal,
            "price":   round(price, 6),
            "signal":  stype,
            "pnl_pct": pnl_pct,
        }
        paper_trades.append(trade_entry)
        strat["paper_trades"]    = paper_trades
        strat["paper_return_pct"] = _calc_paper_return(paper_trades)

        _save_strategy(strat)

        action_str = f"{symbol.upper()}: {signal} at ${price:,.2f}"
        if pnl_pct is not None:
            action_str += f" (P&L: {pnl_pct:+.2f}%)"
        actions.append(action_str)

    return actions


# ── Proposal evaluation ────────────────────────────────────────────────────────

def evaluate_for_proposal(strategy_id: str) -> dict:
    """
    Check if strategy is ready to propose going live.
    Criteria: paper_trading >= 30 days AND paper_return_pct > 5% AND win_rate > 0.5.
    """
    strat = _load_strategy(strategy_id)
    if strat is None:
        return {"ready": False, "reason": f"Strategy {strategy_id} not found", "proposal_id": None}

    if strat.get("status") != "paper_trading":
        return {
            "ready": False,
            "reason": f"Status is '{strat.get('status')}', must be paper_trading",
            "proposal_id": None,
        }

    paper_start = strat.get("paper_start")
    if not paper_start:
        return {"ready": False, "reason": "No paper_start date recorded", "proposal_id": None}

    start_dt  = datetime.fromisoformat(paper_start)
    days_live = (datetime.now(timezone.utc) - start_dt).days
    ret_pct   = strat.get("paper_return_pct", 0.0)
    trades    = strat.get("paper_trades", [])
    win_rate  = _paper_win_rate(trades)

    reasons_fail = []
    if days_live < PAPER_MIN_DAYS:
        reasons_fail.append(f"only {days_live}/{PAPER_MIN_DAYS} days paper trading")
    if ret_pct <= PAPER_MIN_RETURN:
        reasons_fail.append(f"return {ret_pct:.1f}% <= {PAPER_MIN_RETURN}% threshold")
    if win_rate <= PAPER_MIN_WINRATE:
        reasons_fail.append(f"win rate {win_rate:.2f} <= {PAPER_MIN_WINRATE} threshold")

    if reasons_fail:
        return {
            "ready":       False,
            "reason":      "; ".join(reasons_fail),
            "proposal_id": strat.get("proposal_id"),
        }

    # Already proposed
    if strat.get("proposal_id"):
        return {
            "ready":       True,
            "reason":      "Already proposed",
            "proposal_id": strat["proposal_id"],
        }

    # Create agency proposal
    proposal_id = None
    try:
        from tools.operator.agency import propose_action
        bt = strat.get("backtest", {})
        description = (
            f"Go live with strategy '{strat['name']}' on {strat['symbol'].upper()}. "
            f"Paper traded {days_live} days: return {ret_pct:+.1f}%, "
            f"win rate {win_rate:.0%}, {len(trades)} signals. "
            f"Backtest: {bt.get('return_pct', 'N/A')}% return, "
            f"{bt.get('max_drawdown', 'N/A')}% max drawdown."
        )
        proposal_id = propose_action(
            action_type="go_live_strategy",
            description=description,
            target=strat["symbol"],
            payload={
                "strategy_id":      strategy_id,
                "strategy_name":    strat["name"],
                "strategy_type":    strat["type"],
                "params":           strat["params"],
                "paper_return_pct": ret_pct,
                "paper_win_rate":   win_rate,
                "paper_days":       days_live,
                "backtest":         bt,
            },
            reason=strat.get("nova_rationale", ""),
        )
    except Exception as e:
        print(f"  [strategy_engine] Agency propose failed: {e}")
        proposal_id = f"manual_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    strat["proposal_id"] = proposal_id
    strat["status"]      = "proposed"
    _save_strategy(strat)

    idx = _load_index()
    if strategy_id in idx["strategies"]:
        idx["strategies"][strategy_id]["status"] = "proposed"
        _save_index(idx)

    return {
        "ready":       True,
        "reason":      f"Criteria met — {days_live} days, {ret_pct:+.1f}% return, {win_rate:.0%} win rate",
        "proposal_id": proposal_id,
    }


# ── Prompt context ─────────────────────────────────────────────────────────────

def to_prompt_context() -> str:
    """Compact strategy summary for LLM prompt injection."""
    idx = _load_index()
    strategies = idx.get("strategies", {})

    if not strategies:
        return "Strategies: none developed yet."

    paper_count    = 0
    proposed_count = 0
    best_name      = None
    best_return    = None
    best_days      = None

    for sid, meta in strategies.items():
        status = meta.get("status", "")
        if status == "paper_trading":
            paper_count += 1
            strat = _load_strategy(sid)
            if strat:
                ret  = strat.get("paper_return_pct", 0.0)
                ps   = strat.get("paper_start")
                days = 0
                if ps:
                    days = (datetime.now(timezone.utc) - datetime.fromisoformat(ps)).days
                if best_return is None or ret > best_return:
                    best_return = ret
                    best_name   = strat.get("name", sid)
                    best_days   = days
        elif status == "proposed":
            proposed_count += 1

    parts = [f"Strategies: {paper_count} paper trading."]
    if best_name is not None:
        parts.append(f"Best: '{best_name}' {best_return:+.1f}% ({best_days} days).")
    if proposed_count > 0:
        parts.append(f"{proposed_count} awaiting Travis approval.")

    return " ".join(parts)


# ── CLI status display ─────────────────────────────────────────────────────────

def status() -> None:
    """Print all strategies with status, backtest results, paper trade summary."""
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"; M = "\033[35m"

    idx = _load_index()
    strategies = idx.get("strategies", {})

    print(f"\n{B}N.O.V.A Strategy Engine{NC}")
    if not strategies:
        print(f"  {DIM}No strategies on record.{NC}\n")
        return

    status_color = {
        "generated":    DIM,
        "backtested":   C,
        "paper_trading": Y,
        "proposed":     M,
        "live":         G,
        "rejected":     R,
    }

    for sid, meta in sorted(strategies.items()):
        strat  = _load_strategy(sid)
        scol   = status_color.get(meta.get("status", ""), DIM)
        name   = meta.get("name", sid)
        symbol = meta.get("symbol", "?").upper()
        stype  = meta.get("type", "?")
        stat   = meta.get("status", "?")

        print(f"\n  {B}{sid}{NC}  {scol}{stat.upper()}{NC}")
        print(f"    Name:    {name}")
        print(f"    Asset:   {symbol}  Type: {stype}")

        if strat:
            bt = strat.get("backtest", {})
            if bt and "return_pct" in bt:
                ret_col = G if bt["return_pct"] > 0 else R
                print(f"    Backtest:{ret_col} {bt['return_pct']:+.1f}%{NC}  "
                      f"Win: {bt.get('win_rate', 0):.0%}  "
                      f"MaxDD: {bt.get('max_drawdown', 0):.1f}%  "
                      f"Trades: {bt.get('trades', 0)}")
            if bt.get("error"):
                print(f"    {R}Backtest error: {bt['error']}{NC}")

            ps = strat.get("paper_start")
            if ps:
                days = (datetime.now(timezone.utc) - datetime.fromisoformat(ps)).days
                ret  = strat.get("paper_return_pct", 0.0)
                ntrades = len(strat.get("paper_trades", []))
                wrate = _paper_win_rate(strat.get("paper_trades", []))
                ret_col = G if ret > 0 else R
                print(f"    Paper:   {days} days  "
                      f"{ret_col}{ret:+.1f}%{NC}  "
                      f"Win: {wrate:.0%}  "
                      f"Signals: {ntrades}")

            if strat.get("proposal_id"):
                print(f"    Proposal: {M}{strat['proposal_id']}{NC}")

            rationale = strat.get("nova_rationale", "")
            if rationale:
                print(f"    Rationale: {DIM}{rationale[:100]}{'...' if len(rationale) > 100 else ''}{NC}")

    print()


# ── Main / CLI ─────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "status"

    if cmd in ("status", ""):
        status()

    elif cmd == "list":
        idx = _load_index()
        strategies = idx.get("strategies", {})
        if not strategies:
            print("No strategies.")
        else:
            for sid, meta in sorted(strategies.items()):
                print(f"  {sid}  {meta.get('status','?'):15s}  {meta.get('name','?')}")

    elif cmd == "generate":
        symbol = args[1] if len(args) > 1 else "bitcoin"
        print(f"  Generating strategy for {symbol}...")
        strat = generate_strategy(symbol)
        sid   = add_strategy(strat)
        print(f"  Generated: {sid}  '{strat['name']}'")
        print(f"  Type: {strat['type']}  Params: {strat['params']}")
        print(f"  Rationale: {strat['nova_rationale'][:120]}")
        print(f"\n  Run: nova markets strategy backtest {sid}")

    elif cmd == "backtest":
        if len(args) < 2:
            print("Usage: strategy_engine.py backtest <strategy_id>")
            sys.exit(1)
        sid = args[1]
        print(f"  Backtesting {sid}...")
        results = backtest(sid)
        if "error" in results:
            print(f"  Error: {results['error']}")
        else:
            G = "\033[32m"; R = "\033[31m"; NC = "\033[0m"
            col = G if results["return_pct"] > 0 else R
            print(f"  Return:      {col}{results['return_pct']:+.2f}%{NC}")
            print(f"  Win rate:    {results['win_rate']:.0%}")
            print(f"  Max drawdown:{results['max_drawdown']:.1f}%")
            print(f"  Trades:      {results['trades']}")
            print(f"\n  To start paper trading: nova markets strategy paper {sid}")

    elif cmd == "paper":
        if len(args) < 2:
            print("Usage: strategy_engine.py paper <strategy_id>")
            sys.exit(1)
        sid = args[1]
        ok  = start_paper_trading(sid)
        if ok:
            print(f"  Paper trading started for {sid}.")
            print(f"  Run 'nova markets strategy update' daily to log signals.")
        else:
            print(f"  Failed to start paper trading for {sid}.")

    elif cmd == "update":
        sid     = args[1] if len(args) > 1 else None
        label   = sid or "all paper-trading strategies"
        print(f"  Updating paper trades for {label}...")
        actions = update_paper_trades(sid)
        if actions:
            for a in actions:
                print(f"  {a}")
        else:
            print("  No active paper-trading strategies.")

    elif cmd == "evaluate":
        if len(args) < 2:
            print("Usage: strategy_engine.py evaluate <strategy_id>")
            sys.exit(1)
        sid    = args[1]
        result = evaluate_for_proposal(sid)
        G = "\033[32m"; R = "\033[31m"; NC = "\033[0m"
        col = G if result["ready"] else R
        print(f"  Ready: {col}{result['ready']}{NC}")
        print(f"  Reason: {result['reason']}")
        if result.get("proposal_id"):
            print(f"  Proposal ID: {result['proposal_id']}")

    elif cmd == "context":
        print(to_prompt_context())

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: status, list, generate [SYMBOL], backtest ID,")
        print("          paper ID, update [ID], evaluate ID, context")
        sys.exit(1)


if __name__ == "__main__":
    main()
