#!/usr/bin/env python3
"""
N.O.V.A — LLM-Powered Reflection
Decides: act / observe / hold / suppress based on the full finding.
"""
import sys, json, requests, os
from pathlib import Path

_nova_root = str(Path.home() / "Nova")
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("reasoning")
    TIMEOUT    = cfg.timeout("standard")
    TEMP       = cfg.temperature("triage")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 300
    TEMP       = 0.1

def reflect(record: dict) -> dict:
    hyps = record.get("hypotheses", [])
    host = record.get("host", "?")
    path = record.get("path", "/")
    status = record.get("status")
    confidence = record.get("confidence", 0.5)
    signals = record.get("signals", [])
    top_hyp = hyps[0].get("title", "none") if hyps else "none"

    prompt = f"""You are a security researcher triaging a finding.

Target: {host}{path}
Status: {status}
Signals: {', '.join(signals) if signals else 'none'}
Confidence: {confidence:.2f}
Top hypothesis: {top_hyp}

Choose ONE decision and return it as JSON:
{{
  "decision": "act",
  "reason": "why you chose this in one sentence",
  "state": "confident",
  "action": "specific next step to take"
}}

Decision rules:
- "act" if signals are meaningful AND confidence > 0.6
- "observe" if signals exist but confidence is low
- "hold" if no real signals
- "suppress" only if clearly noise

Return ONLY the JSON object. No explanation."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": TEMP, "num_predict": 200}
        }, timeout=TIMEOUT)
        raw = resp.json()["response"]

        # Extract JSON block from response
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            parsed = json.loads(raw[start:end])
            return {
                "decision": parsed.get("decision", "hold"),
                "reason":   parsed.get("reason", ""),
                "state":    parsed.get("state", "uncertain"),
                "action":   parsed.get("action", "")
            }
    except Exception as e:
        pass
    return {"decision": "suppress", "reason": "reflection failed", "state": "uncertain", "action": "suppress"}