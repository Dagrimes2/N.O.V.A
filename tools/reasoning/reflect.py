#!/usr/bin/env python3
"""
N.O.V.A — LLM-Powered Reflection
Decides: act / observe / hold / suppress based on the full finding.
"""
import sys, json, requests, os

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = os.getenv("NOVA_MODEL", "gemma2:2b")

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
            "options": {"temperature": 0.1, "num_predict": 200}
        }, timeout=300)
        raw = resp.json()["response"].strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        raw = raw.strip()
        parsed = json.loads(raw)
        # Ensure required keys exist
        parsed.setdefault("decision", "hold")
        parsed.setdefault("reason", "no reason given")
        parsed.setdefault("state", "uncertain")
        parsed.setdefault("action", "manual review")
        return parsed
    except Exception as e:
        return {
            "decision": "hold",
            "reason": str(e),
            "state": "degraded",
            "action": "manual review"
        }

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        r["reflection"] = reflect(r)
        print(json.dumps(r))

if __name__ == "__main__":
    main()
