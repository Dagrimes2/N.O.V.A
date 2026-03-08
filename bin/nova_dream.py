#!/usr/bin/env python3
"""
N.O.V.A Dream Engine
Nightly memory consolidation and strategic planning.
Reads from memory/store/index.jsonl — no chromadb needed.
"""
import json, requests, datetime
from pathlib import Path

MEMORY_DIR = Path.home() / "Nova/memory/store"
INDEX_FILE = MEMORY_DIR / "index.jsonl"
DREAM_DIR  = Path.home() / "Nova/memory/dreams"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = "gemma2:2b"

def load_recent_findings() -> list:
    if not INDEX_FILE.exists():
        return []
    findings = []
    try:
        with open(INDEX_FILE) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    findings.append((entry.get("text", ""), entry))
                except:
                    continue
    except:
        return []
    return findings

def dream(findings: list) -> str:
    if not findings:
        return "No findings to analyze yet."

    act_findings     = [f[0] for f in findings if f[1].get("decision") == "act"]
    observe_findings = [f[0] for f in findings if f[1].get("decision") == "observe"]

    summary = f"""
Total stored findings: {len(findings)}
High confidence (act): {len(act_findings)}
Needs review (observe): {len(observe_findings)}

High-confidence findings:
{chr(10).join(act_findings[:10]) or 'none yet'}

Uncertain findings:
{chr(10).join(observe_findings[:5]) or 'none yet'}"""

    prompt = f"""You are N.O.V.A in dream state — a security research AI doing
nightly memory consolidation and strategic planning.

Review these findings from recent sessions:
{summary}

Write a strategic synthesis report covering:
1. PATTERN ANALYSIS: What signals keep appearing?
2. BLIND SPOTS: What are we missing?
3. HIGH PRIORITY TARGETS: What deserves deeper testing?
4. TOMORROW'S FOCUS: 3 specific actionable priorities.

Be specific and actionable. Write as N.O.V.A's internal log."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.6, "num_predict": 800}
        }, timeout=300)
        return resp.json()["response"]
    except Exception as e:
        return f"Dream failed: {e}"

def main():
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    print(f"[N.O.V.A] Dream cycle starting: {date_str}")

    DREAM_DIR.mkdir(parents=True, exist_ok=True)

    findings  = load_recent_findings()
    print(f"[N.O.V.A] Loaded {len(findings)} memories...")
    synthesis = dream(findings)

    dream_file = DREAM_DIR / f"dream_{date_str}.md"
    dream_file.write_text(f"# N.O.V.A Dream Log — {date_str}\n\n{synthesis}")
    print(f"[N.O.V.A] Dream complete → {dream_file}")

if __name__ == "__main__":
    main()
