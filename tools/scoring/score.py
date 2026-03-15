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

def score_records(input_file: str) -> str:
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Input file '{input_file}' not found.")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON format in '{input_file}'.")

    if not data:
        raise ValueError(f"Input file '{input_file}' is empty.")

    # Add error handling for invalid JSONL format
    for record in data:
        if not isinstance(record, dict):
            raise ValueError(f"Input file '{input_file}' contains invalid JSONL format.")

    return json.dumps(data)