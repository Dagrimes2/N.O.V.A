#!/usr/bin/env python3
"""
N.O.V.A — LLM-Powered Hypothesis Generator
Replaces static template logic with real Ollama reasoning.
Each finding gets genuine security analysis, not canned text.
"""
import sys, json, requests, os

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = os.getenv("NOVA_MODEL", "gemma2:2b")

SYSTEM_PROMPT = """You are N.O.V.A, an expert security researcher AI assistant.
You analyze HTTP recon findings and generate precise, actionable security hypotheses.
You think like a senior penetration tester: methodical, specific, ethical.
You only work on authorized targets. You output valid JSON only."""

def hypothesize(record: dict) -> list:
    host = record.get("host", "?")
    path = record.get("path", "/")
    status = record.get("status")
    signals = record.get("signals", [])
    method = record.get("method", "GET")

    prompt = f"""You are a security researcher. Analyze this HTTP finding.

Target: {host}{path}
Method: {method}
Status: {status}
Signals: {', '.join(signals) if signals else 'none'}

Give ONE security hypothesis as JSON. Use exactly this format:
{{
  "signal": "the main signal",
  "title": "specific vulnerability name",
  "category": "access_control or auth_bypass or idor or sqli or xss",
  "validate": "one specific test step",
  "impact": "one concrete impact if exploited",
  "confidence_modifier": 0.1
}}

Return ONLY the JSON object. No explanation, no markdown, no arrays."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 500}
        }, timeout=300)
        raw = resp.json()["response"].strip()
        # Strip markdown fences if present
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        raw = raw.strip()
        # Parse single object, wrap in list for pipeline compatibility
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return [parsed]   # single object → wrap in list
        return parsed         # already a list, fine
    except Exception as e:
        # Graceful fallback — don't break the pipeline
        return [{"signal": "llm_unavailable", "title": str(e),
                 "category": "unknown", "what_to_validate": [],
                 "impact_examples": [], "confidence_modifier": 0.0}]

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        r["hypotheses"] = hypothesize(r)
        # Apply confidence modifiers from hypotheses
        mods = [h.get("confidence_modifier", 0) for h in r["hypotheses"]]
        if mods:
            r["confidence"] = min(1.0, max(0.0,
                r.get("confidence", 0.5) + (sum(mods) / len(mods))))
        print(json.dumps(r))

if __name__ == "__main__":
    main()
