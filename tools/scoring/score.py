#!/usr/bin/env python3
"""
Score normalized recon records to prioritize bug bounty targets.
Input:  JSONL from normalize.py
Output: JSONL with added fields:
  - score (int)
  - signals (list[str])
  - confidence (float) — Bayesian-adjusted from learned signal weights
After scoring, each record is passed through nova_wire full_pipeline
for enrichment, memory adjustment, and pattern boosting.
"""
from __future__ import annotations
import json
import sys
from typing import Any, Dict, Iterable

# ----------------- CONFIG -----------------
AUTH_KEYWORDS = {
    "admin", "internal", "debug", "manage", "staff",
    "private", "config", "console", "root"
}
INTERESTING_PARAMS = {
    "id", "user", "user_id", "account", "account_id",
    "uid", "pid", "token", "key", "session"
}
ERROR_STATUS_SCORES = {
    401: 6,
    403: 8,
    500: 5,
    502: 4,
    503: 4,
}
METHOD_SCORES = {
    "POST": 3,
    "PUT": 4,
    "PATCH": 4,
    "DELETE": 6,
}
# ------------------------------------------

# Wire into nova_wire full_pipeline (enrich → memory_adjust → pattern_boost)
try:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[2]))
    from tools.nova_wire import full_pipeline as _full_pipeline
    WIRE_ENABLED = True
except Exception:
    WIRE_ENABLED = False

# Wire Bayesian signal weights from outcome tracker
try:
    from tools.learning.outcome_tracker import get_signal_confidence as _sig_conf
    _LEARNING_ENABLED = True
except Exception:
    _LEARNING_ENABLED = False

# Wire episodic memory — record notable findings automatically
try:
    from tools.learning.episodic_memory import maybe_record_from_finding as _maybe_episode
    _EPISODE_ENABLED = True
except Exception:
    _EPISODE_ENABLED = False


def iter_jsonl(stream: Iterable[str]) -> Iterable[Dict[str, Any]]:
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "signal_strength" not in obj:
            obj["signal_strength"] = 0
        if isinstance(obj, dict):
            yield obj


def is_numeric(value: Any) -> bool:
    try:
        int(value)
        return True
    except Exception:
        return False


def _bayesian_confidence(signals: list[str], base_score: int) -> float:
    """
    Compute a confidence score that blends:
      - Normalized base score (0–1)
      - Bayesian P(real | signal) learned from past outcomes
    New signals default to 0.5 (neutral — no bias toward false positives).
    """
    if not _LEARNING_ENABLED:
        # No learning yet — use simple normalization
        return min(1.0, base_score / 30.0)

    if not signals:
        return min(1.0, base_score / 30.0)

    # Average learned confidence across all triggered signals
    learned = sum(_sig_conf(s) for s in signals) / len(signals)

    # Blend 60% learned, 40% base score (base score anchors early on)
    base_norm = min(1.0, base_score / 30.0)
    blended   = 0.6 * learned + 0.4 * base_norm

    return round(min(1.0, max(0.0, blended)), 4)


def score_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(rec, dict):
        return {"score": 0, "signals": [], "error": "invalid input type"}

    score   = 0
    signals = []

    path   = (rec.get("path") or "").lower()
    method = (rec.get("method") or "GET").upper()
    params = rec.get("params") or {}
    status = rec.get("status")
    length = rec.get("length")

    # ---- Path keyword signals ----
    for kw in AUTH_KEYWORDS:
        if kw in path:
            score += 10
            signals.append("auth-path")
            break

    # ---- HTTP method ----
    if method in METHOD_SCORES:
        score += METHOD_SCORES[method]
        signals.append(f"method-{method.lower()}")

    # ---- Params analysis ----
    for key, value in params.items():
        key_l = str(key).lower()
        if key_l in INTERESTING_PARAMS:
            score += 4
            signals.append(f"interesting-param:{key_l}")
        if is_numeric(value):
            score += 6
            signals.append("numeric-id")
            break

    # ---- Status codes ----
    if isinstance(status, int) and status in ERROR_STATUS_SCORES:
        score += ERROR_STATUS_SCORES[status]
        signals.append(f"error-{status}")

    # ---- Response length anomalies ----
    if isinstance(length, int):
        if length > 100_000:
            score += 3
            signals.append("large-response")
        elif length == 0:
            score += 2
            signals.append("empty-response")

    rec["score"]      = score
    rec["signals"]    = signals
    rec["confidence"] = _bayesian_confidence(signals, score)

    # Auto-record notable findings as episodes
    if _EPISODE_ENABLED:
        try:
            _maybe_episode(rec)
        except Exception:
            pass

    return rec


def main() -> int:
    for record in iter_jsonl(sys.stdin):
        scored = score_record(record)
        if WIRE_ENABLED:
            scored = _full_pipeline(scored)
        sys.stdout.write(json.dumps(scored, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
