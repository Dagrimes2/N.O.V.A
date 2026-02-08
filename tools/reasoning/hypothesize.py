#!/usr/bin/env python3
"""
Nova Phase 7.1 — Hypothesis Engine (offline-first)

Consumes enriched records and emits:
- hypotheses: what might be vulnerable, why, and what to validate
- confidence adjustments: derived from evidence density + memory + reproducibility flags
- no network actions: only generates structured reasoning

Input: JSONL records via stdin
Output: JSONL records with added:
  record["hypotheses"] = [ ... ]
  record["triage"] = { ... }
"""

import json
import sys
import math
from typing import Dict, Any, List


# Heuristic mappings from signals to hypothesis templates (non-exploitative)
HYPOTHESIS_TEMPLATES = {
    "auth-path": {
        "title": "Access control inconsistency on protected route",
        "category": "access_control",
        "what_to_validate": [
            "Confirm whether auth is enforced consistently across methods (GET/POST/HEAD)",
            "Check whether the app exposes distinct responses for authenticated vs unauthenticated users",
            "Verify if intermediate components (proxy/CDN) treat headers/methods differently",
        ],
        "impact_examples": [
            "Unauthorized access to admin functions",
            "Information disclosure (admin metadata, feature flags)",
        ],
    },
    "error-403": {
        "title": "Authorization boundary present; potential inconsistent enforcement",
        "category": "access_control",
        "what_to_validate": [
            "Confirm 403 is consistent across equivalent paths (trailing slash, dot segments)",
            "Check for different behavior when session/cookies are present vs absent",
        ],
        "impact_examples": [
            "Privilege boundary bypass if inconsistent enforcement exists",
        ],
    },
    "numeric-id": {
        "title": "Object-level authorization risk (ID-based access)",
        "category": "idor",
        "what_to_validate": [
            "Verify resource ownership checks exist for different ids",
            "Confirm responses do not leak other users’ data (even partial)",
            "Check behavior with authenticated user A requesting user B’s object",
        ],
        "impact_examples": [
            "Account data exposure",
            "Unauthorized modification of user objects",
        ],
    },
    "interesting-param:id": {
        "title": "Parameter-driven object lookup; potential IDOR surface",
        "category": "idor",
        "what_to_validate": [
            "Map which params change server-side object selection",
            "Confirm access checks and error uniformity",
        ],
        "impact_examples": [
            "Cross-user data exposure",
        ],
    },
    "error-500": {
        "title": "Server error indicates unstable input handling",
        "category": "logic_or_input_handling",
        "what_to_validate": [
            "Identify which inputs trigger 500 reliably (same request → same error)",
            "Check if stack traces or debug markers appear",
            "Confirm whether error correlates with auth/session state",
        ],
        "impact_examples": [
            "Information disclosure via verbose errors",
            "Business logic weaknesses if error occurs on sensitive flows",
        ],
    },
    "method-post": {
        "title": "State-changing endpoint; validate intent + anti-abuse protections",
        "category": "authentication_logic",
        "what_to_validate": [
            "Check whether the endpoint requires CSRF protections where applicable",
            "Confirm failure modes are consistent and not information-leaking",
        ],
        "impact_examples": [
            "Account abuse if protections are missing and flow is exploitable",
        ],
    },
}


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def evidence_strength(signals: List[str], base_conf: float) -> float:
    """
    Slightly increases confidence when multiple independent signals exist.
    Uses diminishing returns.
    """
    n = len(set(signals))
    boost = 1.0 - math.exp(-0.35 * n)  # 0..~1
    # Blend: keep base_conf dominant, boost acts as small multiplier
    return clamp01(base_conf * (0.85 + 0.15 * boost))


def build_hypotheses(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    signals = record.get("signals", []) or []
    out = []

    # Build per-signal hypotheses
    for sig in signals:
        tpl = HYPOTHESIS_TEMPLATES.get(sig)
        if not tpl:
            continue
        out.append({
            "signal": sig,
            "title": tpl["title"],
            "category": tpl["category"],
            "what_to_validate": tpl["what_to_validate"],
            "impact_examples": tpl["impact_examples"],
        })

    # If no signals, create a minimal "surface mapping" hypothesis
    if not out:
        out.append({
            "signal": "none",
            "title": "Unclassified surface — requires manual classification",
            "category": "surface_mapping",
            "what_to_validate": [
                "Confirm endpoint existence and status",
                "Identify whether auth/session changes response",
                "Identify whether response content hints at functionality",
            ],
            "impact_examples": [
                "N/A until classified",
            ],
        })

    return out


def triage_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    host = record.get("host")
    path = record.get("path")
    priority = record.get("priority", "LOW")
    status = record.get("status", "N/A")
    base_conf = float(record.get("confidence", 0.2))
    signals = record.get("signals", []) or []

    adjusted = evidence_strength(signals, base_conf)

    # Simple readiness suggestion (still governed by your other tools)
    # This is NOT submission approval; it's a reasoning hint.
    suggestion = "manual_review"
    if adjusted >= 0.75 and priority in ("HIGH", "MEDIUM"):
        suggestion = "validate_first"
    elif adjusted < 0.35:
        suggestion = "map_surface"

    return {
        "target": f"{host}{path}",
        "status": status,
        "priority": priority,
        "confidence_base": round(base_conf, 2),
        "confidence_adjusted": round(adjusted, 2),
        "signals": signals if signals else ["none"],
        "suggestion": suggestion,
    }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)

        record["hypotheses"] = build_hypotheses(record)
        record["triage"] = triage_summary(record)

        print(json.dumps(record))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
