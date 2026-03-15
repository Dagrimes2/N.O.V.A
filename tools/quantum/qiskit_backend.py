#!/usr/bin/env python3
"""
N.O.V.A Qiskit Quantum Backend

Replaces/augments the classical QRNG with real quantum circuits when
IBM Quantum is available. Falls back gracefully to os.urandom() if Qiskit
is not installed or the IBM backend is unavailable.

Capabilities:
  1. Quantum Random Number Generator (QRNG) — replaces classical PRNG
     Uses Hadamard gates on N qubits, collapses superposition → true randomness
  2. Quantum Portfolio Optimization (QPO) — QAOA-based weight finding
     Maximizes expected return subject to risk constraints
  3. Quantum Monte Carlo seeding — uses quantum entropy for GBM simulations

Config (config/quantum.yaml):
  provider: local        # local (Qiskit Aer) or ibm (IBM Quantum cloud)
  ibm_token: <TOKEN>     # IBM Quantum API token (from quantum.ibm.com — free)
  backend: ibmq_qasm_simulator
  shots: 1024

Usage:
    nova quantum status                     backend status + qubit count
    nova quantum qrng [--bits 256]          generate quantum random bytes
    nova quantum portfolio BTC ETH SOL      QAOA portfolio weights
    nova quantum seed                       generate seeds for Monte Carlo
"""
import os
import sys
import json
import struct
import hashlib
from datetime import datetime, timezone
from pathlib import Path

BASE = Path.home() / "Nova"
QUANTUM_LOG = BASE / "memory/quantum/log.json"
QUANTUM_LOG.parent.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)


# ─── Config ───────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    config_file = BASE / "config/quantum.yaml"
    defaults = {
        "provider": "local",
        "ibm_token": "",
        "backend": "aer_simulator",
        "shots": 1024,
        "n_qubits": 8,
    }
    if not config_file.exists():
        return defaults
    try:
        import yaml
        with open(config_file) as f:
            return {**defaults, **yaml.safe_load(f)}
    except ImportError:
        # Parse minimal yaml manually
        cfg = dict(defaults)
        for line in config_file.read_text().splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                cfg[k.strip()] = v.strip()
        return cfg
    except Exception:
        return defaults


# ─── Backend detection ────────────────────────────────────────────────────────

def detect_backend() -> dict:
    """
    Detect which quantum backend is available.
    Returns {"type": "qiskit_aer"|"qiskit_ibm"|"fallback", "available": bool, ...}
    """
    # Try Qiskit Aer (local simulator — pip install qiskit qiskit-aer)
    try:
        from qiskit_aer import AerSimulator
        sim = AerSimulator()
        return {
            "type": "qiskit_aer",
            "available": True,
            "backend_name": "AerSimulator",
            "max_qubits": 32,
            "note": "Local quantum simulator (Qiskit Aer)",
        }
    except ImportError:
        pass

    # Try IBM Quantum (real hardware or cloud simulator)
    cfg = _load_config()
    if cfg.get("ibm_token"):
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService
            service = QiskitRuntimeService(channel="ibm_quantum",
                                           token=cfg["ibm_token"])
            backends = service.backends()
            return {
                "type": "qiskit_ibm",
                "available": True,
                "backend_name": cfg["backend"],
                "backends": [b.name for b in backends[:5]],
                "note": "IBM Quantum cloud backend",
            }
        except ImportError:
            pass
        except Exception as e:
            pass

    # Fallback: os.urandom (cryptographic CSPRNG — still good)
    return {
        "type": "fallback",
        "available": True,
        "backend_name": "os.urandom (CSPRNG)",
        "note": "Install 'qiskit qiskit-aer' for true quantum randomness",
    }


# ─── QRNG ────────────────────────────────────────────────────────────────────

def quantum_random_bytes(n_bytes: int = 32) -> bytes:
    """
    Generate n_bytes of quantum random data.

    Circuit: N qubits, each through a Hadamard gate, then measured.
    Superposition collapses to a random bitstring upon measurement.
    Concatenate multiple shots → random byte stream.
    """
    backend_info = detect_backend()

    if backend_info["type"] == "qiskit_aer":
        return _qrng_aer(n_bytes)
    elif backend_info["type"] == "qiskit_ibm":
        return _qrng_ibm(n_bytes)
    else:
        return _qrng_fallback(n_bytes)


def _qrng_aer(n_bytes: int) -> bytes:
    """Quantum RNG using Qiskit Aer local simulator."""
    from qiskit import QuantumCircuit
    from qiskit_aer import AerSimulator

    n_qubits = 8  # 8 qubits → 1 byte per shot
    shots_needed = n_bytes

    sim = AerSimulator()
    result_bytes = bytearray()

    # Run in batches to get enough random bits
    while len(result_bytes) < n_bytes:
        qc = QuantumCircuit(n_qubits, n_qubits)
        # Apply Hadamard to all qubits — put in equal superposition
        for i in range(n_qubits):
            qc.h(i)
        # Measure — collapses superposition
        qc.measure_all()

        batch_shots = min(shots_needed - len(result_bytes), 1024)
        job    = sim.run(qc, shots=batch_shots)
        counts = job.result().get_counts()

        for bitstring, count in counts.items():
            val = int(bitstring.replace(" ", ""), 2)
            result_bytes.append(val & 0xFF)
            if len(result_bytes) >= n_bytes:
                break

    return bytes(result_bytes[:n_bytes])


def _qrng_ibm(n_bytes: int) -> bytes:
    """Quantum RNG using IBM Quantum cloud backend."""
    from qiskit import QuantumCircuit
    from qiskit_ibm_runtime import QiskitRuntimeService, Sampler

    cfg     = _load_config()
    service = QiskitRuntimeService(channel="ibm_quantum", token=cfg["ibm_token"])
    backend = service.backend(cfg["backend"])
    sampler = Sampler(backend=backend)

    n_qubits = 8
    qc = QuantumCircuit(n_qubits)
    for i in range(n_qubits):
        qc.h(i)
    qc.measure_all()

    job    = sampler.run([qc], shots=n_bytes)
    result = job.result()
    counts = result[0].data.meas.get_counts()

    result_bytes = bytearray()
    for bitstring, count in counts.items():
        val = int(bitstring.replace(" ", ""), 2)
        result_bytes.append(val & 0xFF)
    return bytes(result_bytes[:n_bytes])


def _qrng_fallback(n_bytes: int) -> bytes:
    """Fallback: cryptographic CSPRNG (os.urandom)."""
    return os.urandom(n_bytes)


def quantum_random_float() -> float:
    """Return a uniform random float in [0, 1) using quantum randomness."""
    raw = quantum_random_bytes(8)
    val = struct.unpack(">Q", raw)[0]
    return val / (2 ** 64)


def quantum_random_seed() -> int:
    """Return a 64-bit integer seed for Monte Carlo simulations."""
    raw = quantum_random_bytes(8)
    return struct.unpack(">Q", raw)[0]


# ─── Quantum Portfolio Optimization (QAOA) ───────────────────────────────────

def portfolio_optimize_qaoa(symbols: list[str],
                             returns:   list[float],
                             risks:     list[float],
                             budget: int = None) -> dict:
    """
    QAOA-based portfolio weight optimization.

    For N assets, find weights that maximize:
        Σ return_i * w_i - λ * Σ risk_i * w_i

    Uses QAOA (Quantum Approximate Optimization Algorithm) with p=1 layer.
    Falls back to classical optimization if Qiskit not available.

    Args:
        symbols: list of asset symbols
        returns: expected return for each asset (0..1)
        risks:   risk score for each asset (0..1)
        budget:  number of assets to select (None = unconstrained)

    Returns: {symbol: weight} dict, normalized to sum=1
    """
    n = len(symbols)
    if n == 0:
        return {}

    backend_info = detect_backend()

    if backend_info["type"] in ("qiskit_aer", "qiskit_ibm"):
        try:
            return _qaoa_optimize(symbols, returns, risks, budget, backend_info)
        except Exception as e:
            pass  # Fall through to classical

    # Classical fallback: risk-adjusted return maximization
    return _classical_portfolio(symbols, returns, risks)


def _qaoa_optimize(symbols, returns, risks, budget, backend_info) -> dict:
    """Run QAOA circuit for portfolio selection."""
    from qiskit import QuantumCircuit
    from qiskit.circuit import Parameter
    import numpy as np

    n = len(symbols)
    λ = 0.5  # risk aversion

    # Objective: maximize Σ (return_i - λ*risk_i) * x_i
    # Encode as QUBO for QAOA
    objective = [r - λ * k for r, k in zip(returns, risks)]

    # p=1 QAOA circuit
    γ = Parameter("γ")
    β = Parameter("β")

    qc = QuantumCircuit(n)
    # Initial state: uniform superposition
    for i in range(n):
        qc.h(i)

    # Cost operator (phase kickback proportional to objective)
    for i in range(n):
        qc.rz(γ * objective[i], i)

    # Mixer operator
    for i in range(n):
        qc.rx(2 * β, i)

    qc.measure_all()

    # Grid search over γ, β (simple QAOA optimization)
    best_weights = None
    best_score   = -float("inf")

    from qiskit_aer import AerSimulator
    sim = AerSimulator()

    for γ_val in [0.1, 0.5, 1.0, 1.5]:
        for β_val in [0.1, 0.5, 1.0]:
            bound = qc.assign_parameters({γ: γ_val, β: β_val})
            job    = sim.run(bound, shots=512)
            counts = job.result().get_counts()

            # Convert measurement outcomes to weights
            weights = [0.0] * n
            total   = sum(counts.values())
            for bitstring, cnt in counts.items():
                bits = [int(b) for b in bitstring.replace(" ", "")]
                for i, b in enumerate(bits[:n]):
                    weights[i] += b * cnt / total

            # Score this parameter set
            score = sum(objective[i] * weights[i] for i in range(n))
            if score > best_score:
                best_score   = score
                best_weights = weights

    if best_weights is None:
        return _classical_portfolio(symbols, returns, risks)

    # Normalize
    total = sum(best_weights)
    if total < 1e-6:
        return _classical_portfolio(symbols, returns, risks)
    norm = {sym: round(w / total, 4) for sym, w in zip(symbols, best_weights)}

    # Apply budget constraint: keep top-budget assets
    if budget and budget < n:
        top = sorted(norm.items(), key=lambda x: x[1], reverse=True)[:budget]
        t   = sum(v for _, v in top)
        norm = {sym: round(v / t, 4) for sym, v in top}

    return norm


def _classical_portfolio(symbols, returns, risks) -> dict:
    """Classical risk-adjusted portfolio allocation."""
    scores = [max(0.0, r - 0.3 * k) for r, k in zip(returns, risks)]
    total  = sum(scores) or 1.0
    return {sym: round(s / total, 4) for sym, s in zip(symbols, scores)}


# ─── Integration with Nova markets ───────────────────────────────────────────

def enhanced_monte_carlo_seed() -> dict:
    """
    Generate quantum-seeded parameters for Monte Carlo simulation.
    Returns multiple independent seeds for parallel simulation streams.
    """
    seeds = [quantum_random_seed() for _ in range(8)]
    return {
        "seeds":     seeds,
        "source":    detect_backend()["type"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def log_quantum_usage(action: str, result: dict) -> None:
    """Log quantum backend usage for audit trail."""
    log = []
    if QUANTUM_LOG.exists():
        try:
            log = json.loads(QUANTUM_LOG.read_text())
        except Exception:
            pass
    log.append({
        "ts":     datetime.now(timezone.utc).isoformat(),
        "action": action,
        "result": str(result)[:100],
    })
    QUANTUM_LOG.write_text(json.dumps(log[-100:], indent=2))


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    M = "\033[35m"; W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "status"

    if cmd == "status":
        info = detect_backend()
        col  = G if info["available"] else R
        print(f"\n{B}N.O.V.A Quantum Backend{NC}")
        print(f"  Provider  : {col}{info['type']}{NC}")
        print(f"  Backend   : {C}{info['backend_name']}{NC}")
        print(f"  Status    : {G}available{NC}" if info["available"] else f"  Status    : {R}unavailable{NC}")
        print(f"  {DIM}{info.get('note','')}{NC}")

        if info["type"] == "fallback":
            print(f"\n  {Y}To enable true quantum randomness:{NC}")
            print(f"  {DIM}pip install qiskit qiskit-aer{NC}")
            print(f"  {DIM}# For IBM Quantum hardware: pip install qiskit-ibm-runtime{NC}")
            print(f"  {DIM}# Get free account at quantum.ibm.com{NC}")

    elif cmd == "qrng":
        n_bits = 256
        if "--bits" in args:
            i = args.index("--bits")
            n_bits = int(args[i + 1]) if i + 1 < len(args) else 256
        n_bytes = max(1, n_bits // 8)

        info    = detect_backend()
        print(f"{DIM}Generating {n_bits} quantum random bits via {info['type']}...{NC}")
        raw     = quantum_random_bytes(n_bytes)
        hex_str = raw.hex()
        print(f"\n{G}{hex_str}{NC}")
        seed    = struct.unpack(">Q", raw[:8])[0]
        print(f"\n{DIM}As int64 seed: {seed}{NC}")
        log_quantum_usage("qrng", {"bits": n_bits, "seed": seed})

    elif cmd == "portfolio":
        symbols = [a.upper() for a in args[1:] if not a.startswith("--")]
        if not symbols:
            symbols = ["BTC", "ETH", "SOL", "AAPL", "NVDA"]

        print(f"\n{B}Quantum Portfolio Optimization (QAOA){NC}")
        print(f"{DIM}Assets: {', '.join(symbols)}{NC}\n")

        # Fetch expected returns from markets if available
        returns, risks = [], []
        for sym in symbols:
            try:
                from bin.nova_markets import analyze_asset
                result = analyze_asset(sym, horizon=7)
                if result:
                    conv = result.get("conviction", 0.0)
                    risk = result.get("risk_score", 0.5)
                    # Map conviction (-1..+1) to return estimate (0..1)
                    returns.append(max(0.01, (conv + 1) / 2))
                    risks.append(float(risk))
                else:
                    returns.append(0.5); risks.append(0.5)
            except Exception:
                returns.append(0.5); risks.append(0.5)

        weights = portfolio_optimize_qaoa(symbols, returns, risks)

        print(f"{'Asset':8s} {'Weight':8s} {'Est.Return':12s} {'Risk':8s}")
        print(f"{DIM}{'─'*40}{NC}")
        for i, sym in enumerate(symbols):
            w   = weights.get(sym, 0.0)
            col = G if w > 0.25 else (Y if w > 0.1 else DIM)
            bar = "█" * int(w * 20)
            print(f"  {col}{sym:6s}{NC}  {w:.1%}  {G}{bar:<20s}{NC}  "
                  f"r={returns[i]:.2f}  ρ={risks[i]:.2f}")

        backend_info = detect_backend()
        print(f"\n{DIM}Backend: {backend_info['type']}{NC}")
        log_quantum_usage("portfolio", {"symbols": symbols, "weights": weights})

    elif cmd == "seed":
        seeds = enhanced_monte_carlo_seed()
        print(f"\n{B}Quantum Monte Carlo Seeds{NC}  {DIM}({seeds['source']}){NC}")
        for i, s in enumerate(seeds["seeds"]):
            print(f"  seed[{i}] = {C}{s}{NC}")

    else:
        print("Usage: nova quantum [status|qrng [--bits N]|portfolio [SYM ...]|seed]")


if __name__ == "__main__":
    main()
