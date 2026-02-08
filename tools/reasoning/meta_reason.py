#!/usr/bin/env python3
import sys, json

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))

def meta(record):
    # Inputs (best-effort)
    conf = float(record.get("confidence", 0.0) or 0.0)
    priority = (record.get("priority") or "LOW").upper()
    status = record.get("status")
    signals = record.get("signals") or []
    playbooks = record.get("playbooks") or []
    suggestion = (record.get("triage") or {}).get("suggestion") or "unknown"

    # --- Evidence quality checks ---
    evidence = {
        "has_status": status is not None and status != "N/A",
        "has_signals": len(signals) > 0,
        "has_playbooks": len(playbooks) > 0,
        "has_length": record.get("length") is not None,
        "has_method": bool(record.get("method")),
    }

    missing = [k for k, v in evidence.items() if not v]

    # --- Risk of overreach / hallucination ---
    # Start with "low risk" when we have: status + signals + >=0.7 confidence
    risk = 0.5
    if evidence["has_status"] and evidence["has_signals"] and conf >= 0.7:
        risk -= 0.25
    if len(missing) >= 2:
        risk += 0.25
    if conf < 0.4:
        risk += 0.20
    if priority == "HIGH" and conf < 0.6:
        risk += 0.10

    risk = clamp(risk)

    # --- Meta critique (why are we doing this?) ---
    critique = []
    if suggestion == "validate_first" and not evidence["has_status"]:
        critique.append("validate_first suggested, but status is missing; need a real response code.")
    if suggestion == "manual_review" and conf < 0.5:
        critique.append("manual_review suggested with low confidence; consider surface mapping first.")
    if not evidence["has_playbooks"] and evidence["has_signals"]:
        critique.append("signals present but no playbooks generated; playbook stage may be skipped/misconfigured.")
    if len(signals) == 0 and conf >= 0.6:
        critique.append("confidence is high without signals; confirm scoring logic.")

    # --- Next best action (operator-facing) ---
    # Important: these are safe, non-exploitative “what to verify next” steps.
    if risk >= 0.75:
        next_action = "map_surface"
        questions = [
            "What is the exact HTTP status + headers returned?",
            "Is this endpoint authenticated? What changes pre/post login?",
            "Is the response stable across 3 requests?"
        ]
    elif conf >= 0.8 and evidence["has_signals"] and evidence["has_status"]:
        next_action = "validate_reproducibility"
        questions = [
            "Can we reproduce the signal 3 times with identical inputs?",
            "Do we have before/after evidence (unauth vs auth) if relevant?",
            "Is impact demonstrable beyond 'interesting behavior'?"
        ]
    elif suggestion in ("manual_review", "validate_first"):
        next_action = "collect_context"
        questions = [
            "What parameters/IDs are user-controlled and reflected in response?",
            "Do different IDs yield different objects or permissions?",
            "Any rate-limit, caching, or WAF behavior affecting results?"
        ]
    else:
        next_action = "triage_queue"
        questions = [
            "Is this worth time vs current top targets?",
            "Any program rules that forbid this testing style?",
        ]

    record["meta_reasoning"] = {
        "evidence": evidence,
        "missing": missing,
        "risk_of_overreach": risk,
        "critique": critique,
        "next_best_action": next_action,
        "questions_to_answer": questions
    }
    return record

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        print(json.dumps(meta(r)))

if __name__ == "__main__":
    main()
