#!/usr/bin/env python3
"""
N.O.V.A Phantom Wallet Integration

Read-only connection to your Phantom wallet via Solana JSON-RPC.
NEVER requires a private key — only your public wallet address.

Reads:
  - SOL balance
  - SPL token balances (USDC, BONK, JUP, WIF, etc.)
  - NFT holdings (Metaplex standard)
  - Recent transaction history
  - Total portfolio value in USD

Prices from Jupiter Price API (Solana-native, real-time aggregated).

Config: config/phantom.yaml
    address: <YOUR_PHANTOM_PUBLIC_KEY>
    rpc_url: https://api.mainnet-beta.solana.com   # or Helius/Alchemy

Usage:
    nova phantom status                  wallet overview
    nova phantom balance                 SOL + all token balances
    nova phantom tokens                  SPL token holdings
    nova phantom nfts                    NFT collection summary
    nova phantom history [--n 10]        recent transactions
    nova phantom compare                 real holdings vs paper portfolio
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = Path.home() / "Nova"
_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# ─── Known SPL token mints ───────────────────────────────────────────────────
# Maps mint address → (symbol, decimals)
KNOWN_MINTS: dict[str, tuple[str, int]] = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": ("USDC",  6),
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": ("USDT",  6),
    "So11111111111111111111111111111111111111112":   ("SOL",   9),
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": ("BONK",  5),
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN":  ("JUP",   6),
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": ("WIF",   6),
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": ("ETH",   8),
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So":  ("mSOL",  9),
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": ("stSOL", 9),
    "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE":  ("ORCA",  6),
    "4k3Dyjzvzp8eMZWqlwv2GJeyAaosKikZYF8gb3MdiR8h":  ("RAY",   6),
}


# ─── Config ───────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    config_file = BASE / "config/phantom.yaml"
    defaults = {
        "address": "",
        "rpc_url": "https://api.mainnet-beta.solana.com",
    }
    if not config_file.exists():
        return defaults
    try:
        cfg = dict(defaults)
        for line in config_file.read_text().splitlines():
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                k, _, v = line.partition(":")
                cfg[k.strip()] = v.strip()
        return cfg
    except Exception:
        return defaults


def get_wallet_address() -> str:
    cfg = _load_config()
    addr = cfg.get("address", "")
    if not addr:
        raise ValueError(
            "Phantom wallet address not configured.\n"
            "Run: nova phantom setup\n"
            "Or create config/phantom.yaml with: address: <YOUR_PUBLIC_KEY>"
        )
    return addr


def get_rpc_url() -> str:
    return _load_config().get("rpc_url", "https://api.mainnet-beta.solana.com")


# ─── Solana RPC ───────────────────────────────────────────────────────────────

def _rpc(method: str, params: list, rpc_url: str = None) -> dict:
    url = rpc_url or get_rpc_url()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15,
                             headers={"Content-Type": "application/json"})
        data = resp.json()
        if "error" in data:
            return {"error": data["error"].get("message", "RPC error")}
        return data.get("result", {})
    except Exception as e:
        return {"error": str(e)}


def get_sol_balance(address: str = None) -> dict:
    """Return SOL balance in lamports and SOL."""
    addr   = address or get_wallet_address()
    result = _rpc("getBalance", [addr])
    if isinstance(result, dict) and "error" in result:
        return {"error": result["error"]}
    lamports = result.get("value", 0) if isinstance(result, dict) else result
    return {
        "lamports": lamports,
        "sol":      round(lamports / 1e9, 6),
    }


def get_token_accounts(address: str = None) -> list[dict]:
    """Return all SPL token accounts for the wallet."""
    addr   = address or get_wallet_address()
    result = _rpc("getTokenAccountsByOwner", [
        addr,
        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
        {"encoding": "jsonParsed"},
    ])
    if isinstance(result, dict) and "error" in result:
        return []

    accounts = []
    for acct in (result.get("value") or []):
        info = (acct.get("account", {})
                    .get("data", {})
                    .get("parsed", {})
                    .get("info", {}))
        mint    = info.get("mint", "")
        amount  = info.get("tokenAmount", {})
        ui_amt  = amount.get("uiAmount", 0) or 0
        dec     = amount.get("decimals", 0)

        if ui_amt <= 0:
            continue

        sym, _ = KNOWN_MINTS.get(mint, ("UNKNOWN", dec))
        accounts.append({
            "mint":    mint,
            "symbol":  sym,
            "amount":  ui_amt,
            "decimals": dec,
        })

    return sorted(accounts, key=lambda x: x["amount"], reverse=True)


def get_nft_accounts(address: str = None) -> list[dict]:
    """Return NFT token accounts (amount=1, decimals=0)."""
    addr   = address or get_wallet_address()
    result = _rpc("getTokenAccountsByOwner", [
        addr,
        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
        {"encoding": "jsonParsed"},
    ])
    if isinstance(result, dict) and "error" in result:
        return []

    nfts = []
    for acct in (result.get("value") or []):
        info   = (acct.get("account", {})
                      .get("data", {})
                      .get("parsed", {})
                      .get("info", {}))
        amount = info.get("tokenAmount", {})
        ui_amt = amount.get("uiAmount", 0) or 0
        dec    = amount.get("decimals", 0)
        mint   = info.get("mint", "")

        if ui_amt == 1 and dec == 0:
            nfts.append({"mint": mint, "symbol": "NFT"})

    return nfts


def get_recent_transactions(address: str = None, n: int = 10) -> list[dict]:
    """Return recent transaction signatures and basic info."""
    addr   = address or get_wallet_address()
    result = _rpc("getSignaturesForAddress", [addr, {"limit": n}])
    if not isinstance(result, list):
        return []

    txns = []
    for sig_info in result:
        ts = sig_info.get("blockTime")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""
        txns.append({
            "signature": sig_info.get("signature", ""),
            "slot":      sig_info.get("slot", 0),
            "ts":        dt,
            "err":       sig_info.get("err"),
            "memo":      sig_info.get("memo", ""),
        })
    return txns


# ─── Jupiter Price API ────────────────────────────────────────────────────────

_JUPITER_PRICE_URL = "https://price.jup.ag/v6/price"
_price_cache: dict[str, dict] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 60.0  # 1 minute


def get_jupiter_prices(symbols: list[str]) -> dict[str, float]:
    """
    Fetch real-time prices from Jupiter Price API.
    Returns {symbol: usd_price}.
    Jupiter aggregates across all Solana DEXes — most accurate for SOL ecosystem.
    """
    global _price_cache, _cache_ts
    now = time.monotonic()

    # Use cache if fresh
    if now - _cache_ts < _CACHE_TTL and _price_cache:
        return {sym: _price_cache.get(sym, 0.0) for sym in symbols}

    # Build mint → symbol reverse map
    sym_to_mint = {}
    for mint, (sym, _) in KNOWN_MINTS.items():
        sym_to_mint[sym.upper()] = mint

    # Collect mints for requested symbols
    mints    = [sym_to_mint.get(s.upper(), s) for s in symbols]
    ids_str  = ",".join(mints)

    try:
        resp = requests.get(
            _JUPITER_PRICE_URL,
            params={"ids": ids_str, "vsToken": "USDC"},
            timeout=10
        )
        data = resp.json().get("data", {})
        prices: dict[str, float] = {}
        for sym, mint in zip(symbols, mints):
            entry = data.get(mint) or data.get(sym.upper()) or {}
            prices[sym.upper()] = float(entry.get("price", 0.0))
        _price_cache = prices
        _cache_ts    = now
        return prices
    except Exception:
        return {sym: 0.0 for sym in symbols}


def get_sol_price_usd() -> float:
    """Return current SOL price in USD from Jupiter."""
    prices = get_jupiter_prices(["SOL"])
    return prices.get("SOL", 0.0)


# ─── Portfolio value ──────────────────────────────────────────────────────────

def portfolio_value(address: str = None) -> dict:
    """
    Total wallet value in USD — SOL + all SPL tokens.
    Uses Jupiter prices for Solana-native tokens.
    """
    addr = address or get_wallet_address()

    sol_info = get_sol_balance(addr)
    sol_amt  = sol_info.get("sol", 0.0)
    tokens   = get_token_accounts(addr)

    # Collect all symbols that need pricing
    syms = ["SOL"] + [t["symbol"] for t in tokens if t["symbol"] != "UNKNOWN"]
    prices = get_jupiter_prices(list(set(syms)))

    sol_price = prices.get("SOL", 0.0)
    sol_usd   = sol_amt * sol_price

    token_values = []
    for tok in tokens:
        sym   = tok["symbol"]
        price = prices.get(sym, 0.0)
        usd   = tok["amount"] * price
        token_values.append({**tok, "price_usd": price, "usd_value": round(usd, 4)})

    total_usd = sol_usd + sum(t["usd_value"] for t in token_values)

    return {
        "address":     addr,
        "sol":         sol_amt,
        "sol_price":   sol_price,
        "sol_usd":     round(sol_usd, 2),
        "tokens":      token_values,
        "nft_count":   len(get_nft_accounts(addr)),
        "total_usd":   round(total_usd, 2),
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }


def compare_with_paper(address: str = None) -> dict:
    """
    Compare real Phantom holdings vs Nova's paper trading portfolio.
    Highlights divergence between actual and simulated positions.
    """
    real = portfolio_value(address)

    try:
        from tools.markets.paper_trading import portfolio_value as paper_pv
        paper = paper_pv()
    except Exception:
        paper = {"positions": [], "total_val": 0}

    real_symbols  = {"SOL": real["sol"]}
    for t in real["tokens"]:
        real_symbols[t["symbol"]] = t["amount"]

    paper_symbols = {}
    for p in paper.get("positions", []):
        paper_symbols[p["symbol"]] = p["qty"]

    all_syms = set(list(real_symbols.keys()) + list(paper_symbols.keys()))
    diff = []
    for sym in sorted(all_syms):
        r_qty = real_symbols.get(sym, 0.0)
        p_qty = paper_symbols.get(sym, 0.0)
        diff.append({
            "symbol":  sym,
            "real_qty":  r_qty,
            "paper_qty": p_qty,
            "delta":     r_qty - p_qty,
        })

    return {
        "real_usd":   real["total_usd"],
        "paper_usd":  paper.get("total_val", 0),
        "real_sol":   real["sol"],
        "comparison": diff,
    }


# ─── Setup wizard ─────────────────────────────────────────────────────────────

def setup_wizard() -> None:
    G = "\033[32m"; C = "\033[36m"; W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"
    print(f"\n{B}N.O.V.A Phantom Wallet Setup{NC}")
    print(f"{DIM}Your {W}public key only{NC}{DIM} — Nova never needs your seed phrase or private key.{NC}")
    print(f"\nTo find your public key:")
    print(f"  1. Open Phantom wallet")
    print(f"  2. Click your wallet name at the top")
    print(f"  3. Copy the address shown (starts with a letter, ~44 characters)")
    print()

    address = input(f"{C}Paste your Phantom public key: {NC}").strip()
    if not address or len(address) < 32:
        print(f"\033[31mInvalid address.{NC}")
        return

    rpc = input(
        f"{C}RPC URL [{DIM}press Enter for free mainnet{NC}{C}]: {NC}"
    ).strip() or "https://api.mainnet-beta.solana.com"

    config_file = BASE / "config/phantom.yaml"
    config_file.write_text(f"# Phantom wallet config — public key only\naddress: {address}\nrpc_url: {rpc}\n")
    print(f"\n{G}Config saved to config/phantom.yaml{NC}")
    print(f"{DIM}Testing connection...{NC}")

    try:
        bal = get_sol_balance(address)
        if "error" in bal:
            print(f"\033[31mConnection error: {bal['error']}{NC}")
        else:
            print(f"{G}Connected! SOL balance: {bal['sol']:.4f} SOL{NC}")
    except Exception as e:
        print(f"\033[31mError: {e}{NC}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    M = "\033[35m"; W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "status"

    if cmd == "setup":
        setup_wizard()
        return

    # All other commands need address
    try:
        addr = get_wallet_address()
    except ValueError as e:
        print(f"{R}{e}{NC}")
        return

    if cmd == "status":
        print(f"\n{DIM}Fetching wallet data...{NC}", end="\r")
        pv = portfolio_value(addr)
        print(f"\n{B}N.O.V.A Phantom Wallet{NC}")
        print(f"  {DIM}Address:{NC} {C}{addr[:8]}...{addr[-8:]}{NC}")
        print(f"  {B}Total value:{NC} {G}${pv['total_usd']:,.2f}{NC}")
        print(f"  SOL: {W}{pv['sol']:.4f}{NC} @ ${pv['sol_price']:,.2f}  = {G}${pv['sol_usd']:,.2f}{NC}")
        print(f"  SPL tokens: {len(pv['tokens'])}  NFTs: {pv['nft_count']}")
        if pv["tokens"]:
            print(f"\n  {B}Top holdings:{NC}")
            for t in pv["tokens"][:5]:
                col = G if t["usd_value"] > 100 else (Y if t["usd_value"] > 10 else DIM)
                print(f"    {col}{t['symbol']:8s}{NC}  {t['amount']:>14,.4f}  "
                      f"@ ${t['price_usd']:,.6g}  = {G}${t['usd_value']:,.2f}{NC}")

    elif cmd == "balance":
        sol  = get_sol_balance(addr)
        price = get_sol_price_usd()
        print(f"\n{B}SOL Balance{NC}")
        print(f"  {W}{sol.get('sol', 0):.6f} SOL{NC}  @ ${price:,.2f}  = "
              f"{G}${sol.get('sol',0)*price:,.2f}{NC}")

    elif cmd == "tokens":
        tokens = get_token_accounts(addr)
        if not tokens:
            print(f"{DIM}No SPL token holdings found.{NC}")
            return
        symbols = [t["symbol"] for t in tokens if t["symbol"] != "UNKNOWN"]
        prices  = get_jupiter_prices(list(set(symbols + ["SOL"])))
        print(f"\n{B}SPL Token Holdings{NC}")
        print(f"{'Symbol':10s} {'Amount':>16s} {'Price':>12s} {'USD Value':>12s}")
        print(f"{DIM}{'─'*54}{NC}")
        for t in tokens:
            price = prices.get(t["symbol"], 0.0)
            usd   = t["amount"] * price
            col   = G if usd > 100 else (Y if usd > 10 else DIM)
            print(f"  {col}{t['symbol']:8s}{NC}  {t['amount']:>14,.4f}  "
                  f"${price:>10,.6g}  {G}${usd:>10,.2f}{NC}")

    elif cmd == "nfts":
        nfts = get_nft_accounts(addr)
        print(f"\n{B}NFT Holdings{NC}  ({len(nfts)} tokens)")
        for n in nfts[:20]:
            print(f"  {DIM}{n['mint'][:24]}...{NC}")
        if len(nfts) > 20:
            print(f"  {DIM}... and {len(nfts)-20} more{NC}")

    elif cmd == "history":
        n    = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
        txns = get_recent_transactions(addr, n)
        if not txns:
            print(f"{DIM}No recent transactions found.{NC}")
            return
        print(f"\n{B}Recent Transactions{NC}  ({len(txns)} shown)")
        for t in txns:
            err_col = R if t["err"] else G
            status  = "✗" if t["err"] else "✓"
            memo    = f"  {DIM}{t['memo'][:30]}{NC}" if t["memo"] else ""
            print(f"  {err_col}{status}{NC}  {DIM}{t['ts'][:16]}{NC}  "
                  f"{C}{t['signature'][:16]}...{NC}{memo}")

    elif cmd == "compare":
        print(f"\n{DIM}Comparing real holdings vs paper portfolio...{NC}")
        result = compare_with_paper(addr)
        print(f"\n{B}Real vs Paper Portfolio{NC}")
        print(f"  Real wallet : {G}${result['real_usd']:,.2f}{NC}")
        print(f"  Paper portfolio: {Y}${result['paper_usd']:,.2f}{NC}")
        if result["comparison"]:
            print(f"\n  {'Symbol':8s} {'Real':>12s} {'Paper':>12s} {'Delta':>12s}")
            print(f"  {DIM}{'─'*48}{NC}")
            for d in result["comparison"]:
                dcol = G if d["delta"] >= 0 else R
                print(f"  {d['symbol']:8s}  "
                      f"{d['real_qty']:>10.4f}  {d['paper_qty']:>10.4f}  "
                      f"{dcol}{d['delta']:>+10.4f}{NC}")

    else:
        print("Usage: nova phantom [setup|status|balance|tokens|nfts|history|compare]")


if __name__ == "__main__":
    main()
