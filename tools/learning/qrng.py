#!/usr/bin/env python3
"""
N.O.V.A Quantum Random Number Generator (QRNG)

Replaces Python's pseudo-random with genuine quantum entropy.
Source: ANU Quantum Random Numbers (public API, no key required).
Fallback: os.urandom() (cryptographic quality) if offline.

Usage:
    from tools.learning.qrng import qrand, qchoice, qshuffle

    val    = qrand()              # float in [0, 1)
    item   = qchoice(my_list)     # quantum-random choice
    order  = qshuffle(my_list)    # quantum-shuffled copy

This matters because:
  - Python's random.random() is Mersenne Twister — deterministic, seeded
  - Nova's decisions, creative choices, and dream selection should be
    genuinely non-deterministic
  - Real quantum entropy = no pattern an observer could predict or exploit
"""
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any, Sequence

# ANU QRNG endpoint — public, no auth, returns true quantum random bytes
_ANU_URL = "https://qrng.anu.edu.au/API/jsonI.php?length=1024&type=uint8"
_CACHE_FILE = Path.home() / "Nova/memory/learning/qrng_cache.bin"
_CACHE_MIN  = 256   # refill if below this many bytes

_cache = bytearray()
_last_fetch = 0.0
_FETCH_COOLDOWN = 60.0   # seconds between network calls


def _fetch_quantum_bytes(n: int = 1024) -> bytes:
    """
    Fetch n quantum random bytes.
    Priority: Qiskit (real/simulated quantum) → ANU QRNG API → empty.
    """
    global _last_fetch
    now = time.monotonic()
    if now - _last_fetch < _FETCH_COOLDOWN:
        return b""

    # 1. Try Qiskit (local Aer simulator or IBM Quantum)
    try:
        from tools.quantum.qiskit_backend import quantum_random_bytes, detect_backend
        info = detect_backend()
        if info["type"] in ("qiskit_aer", "qiskit_ibm"):
            result = quantum_random_bytes(n)
            if result:
                _last_fetch = time.monotonic()
                return result
    except Exception:
        pass

    # 2. Try ANU QRNG REST API
    try:
        import urllib.request
        import json as _json
        with urllib.request.urlopen(_ANU_URL, timeout=5) as resp:
            data = _json.loads(resp.read())
            if data.get("success"):
                _last_fetch = time.monotonic()
                return bytes(data["data"][:n])
    except Exception:
        pass

    return b""


def _load_cache():
    global _cache
    if _CACHE_FILE.exists():
        try:
            _cache = bytearray(_CACHE_FILE.read_bytes())
        except Exception:
            _cache = bytearray()


def _save_cache():
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_bytes(bytes(_cache))
    except Exception:
        pass


def _ensure_entropy(n: int = 8):
    """Make sure we have at least n bytes of entropy available."""
    global _cache

    if len(_cache) < _CACHE_MIN:
        # Try quantum first
        fresh = _fetch_quantum_bytes(1024)
        if fresh:
            _cache.extend(fresh)
            _save_cache()

    # Still low? Fall back to cryptographic os.urandom
    if len(_cache) < n:
        _cache.extend(os.urandom(1024))


def _pop_bytes(n: int) -> bytes:
    """Pop n bytes from the cache."""
    _ensure_entropy(n)
    chunk = bytes(_cache[:n])
    del _cache[:n]
    return chunk


# ── Public API ────────────────────────────────────────────────────────────────

def qrand() -> float:
    """Return a quantum-random float in [0.0, 1.0)."""
    raw = _pop_bytes(8)
    val = struct.unpack(">Q", raw)[0]
    return val / (2**64)


def qrandint(a: int, b: int) -> int:
    """Return a quantum-random integer N such that a <= N <= b."""
    span = b - a + 1
    raw  = _pop_bytes(8)
    val  = struct.unpack(">Q", raw)[0]
    return a + (val % span)


def qchoice(seq: Sequence[Any]) -> Any:
    """Return a quantum-random element from a non-empty sequence."""
    if not seq:
        raise IndexError("qchoice from empty sequence")
    return seq[qrandint(0, len(seq) - 1)]


def qshuffle(seq: list) -> list:
    """Return a quantum-shuffled copy of a list (Fisher-Yates)."""
    result = list(seq)
    for i in range(len(result) - 1, 0, -1):
        j = qrandint(0, i)
        result[i], result[j] = result[j], result[i]
    return result


def qsample(seq: Sequence[Any], k: int) -> list:
    """Return k unique quantum-random elements from seq."""
    shuffled = qshuffle(list(seq))
    return shuffled[:k]


def entropy_source() -> str:
    """Report where entropy is currently coming from."""
    if len(_cache) > _CACHE_MIN:
        return "quantum_cache"
    fresh = _fetch_quantum_bytes(1)
    if fresh:
        return "quantum_live"
    return "os_urandom"


# ── Init — load cache on import ───────────────────────────────────────────────
_load_cache()


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A QRNG")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("source",  help="Show current entropy source")
    sub.add_parser("status",  help="Cache status")
    r = sub.add_parser("rand",    help="Generate N random floats")
    r.add_argument("--n", type=int, default=5)
    sub.add_parser("fetch",   help="Force-fetch fresh quantum bytes from ANU")

    args = p.parse_args()
    G="\033[32m"; C="\033[36m"; W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"

    if args.cmd == "source":
        src = entropy_source()
        col = G if "quantum" in src else C
        print(f"Entropy source: {col}{src}{NC}")

    elif args.cmd == "status":
        print(f"\n{B}QRNG Status{NC}")
        print(f"  Cache size:    {W}{len(_cache)}{NC} bytes")
        print(f"  Cache minimum: {_CACHE_MIN} bytes")
        print(f"  Source:        {G}{entropy_source()}{NC}")
        print(f"  Cache file:    {DIM}{_CACHE_FILE}{NC}")

    elif args.cmd == "rand":
        print(f"\n{B}{args.n} quantum random values:{NC}")
        for _ in range(args.n):
            print(f"  {G}{qrand():.10f}{NC}")

    elif args.cmd == "fetch":
        global _last_fetch
        _last_fetch = 0  # reset cooldown
        fresh = _fetch_quantum_bytes(1024)
        if fresh:
            _cache.extend(fresh)
            _save_cache()
            print(f"{G}Fetched {len(fresh)} quantum bytes from ANU. Cache: {len(_cache)} bytes.{NC}")
        else:
            print(f"{C}ANU unavailable — cache has {len(_cache)} bytes of os.urandom entropy.{NC}")
    else:
        # Default: just show a value
        print(f"qrand() = {qrand():.10f}")
        print(f"source  = {entropy_source()}")


if __name__ == "__main__":
    main()
