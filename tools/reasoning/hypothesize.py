#!/usr/bin/env python3
"""
N.O.V.A — LLM-Powered Hypothesis Generator
Each finding gets genuine security analysis via Ollama.
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
    TEMP       = cfg.temperature("reasoning")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 180
    TEMP       = 0.1


def hypothesize(record: dict) -> list:
    host    = record.get("host", "?")
    path    = record.get("path", "/")
    status  = record.get("status")
    signals = record.get("signals", [])
    method  = record.get("method", "GET")

    if not signals:
        return []

    # Inject known graph patterns for these signals if available
    pattern_hint = ""
    try:
        from tools.knowledge.graph import find_nodes
        sig_nodes = []
        for sig in signals[:3]:
            nodes = find_nodes(type_="pattern", label=sig, limit=3)
            sig_nodes += [n["label"] for n in nodes]
        if sig_nodes:
            pattern_hint = f"\nKnown patterns for these signals: {', '.join(sig_nodes)}"
    except Exception:
        pass

    prompt = f"""You are N.O.V.A, an expert security researcher AI.
Analyze this HTTP finding and return ONE precise security hypothesis.

Target: {host}{path}
Method: {method}
Status: {status}
Signals: {', '.join(signals)}{pattern_hint}

Return ONLY this JSON object, no explanation, no markdown:
{{
  "signal": "the triggering signal",
  "title": "specific vulnerability name (e.g. IDOR via numeric user ID)",
  "category": "idor|auth_bypass|access_control|sqli|xss|ssrf|rce|info_disclosure",
  "validate": "one concrete test step",
  "impact": "one sentence: what an attacker gains if this is real",
  "confidence_modifier": 0.10
}}"""

    try:
        try:
            from tools.llm.llm_cache import llm_call, TTL_REASONING
            raw = llm_call(MODEL, prompt, temperature=TEMP,
                           num_predict=300, ttl=TTL_REASONING)
        except Exception:
            resp = requests.post(OLLAMA_URL, json={
                "model":   MODEL, "prompt": prompt, "stream": False,
                "options": {"temperature": TEMP, "num_predict": 300}
            }, timeout=TIMEOUT)
            raw = resp.json().get("response", "")
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            hyp = json.loads(raw[start:end])
            return [hyp]
    except Exception:
        pass

    return []


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        hyps = hypothesize(record)
        record["hypotheses"] = hyps
        print(json.dumps(record))


if __name__ == "__main__":
    main()
