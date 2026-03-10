#!/usr/bin/env python3
"""
N.O.V.A Report Generator
Queue item → HackerOne-ready bug report draft
Usage: nova_report.py                    draft from top queue item
       nova_report.py --list             show reportable queue items
       nova_report.py --id <queue_id>    draft specific item
"""
import json, requests, os, sys
from pathlib import Path
from datetime import datetime

BASE       = Path.home() / "Nova"
REPORTS    = BASE / "reports"
QUEUE_FILE = BASE / "memory/queue_items.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

REPORTS.mkdir(parents=True, exist_ok=True)

# HackerOne severity mapping
SEVERITY_MAP = {
    "critical": {"h1": "critical",  "cvss_range": "9.0-10.0"},
    "high":     {"h1": "high",      "cvss_range": "7.0-8.9"},
    "medium":   {"h1": "medium",    "cvss_range": "4.0-6.9"},
    "low":      {"h1": "low",       "cvss_range": "0.1-3.9"},
    "info":     {"h1": "informational", "cvss_range": "0.0"},
}

def load_queue() -> list:
    """Load findings from memory store."""
    findings = []
    
    # Try queue_items first
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text())
        except:
            pass
    
    # Fall back to memory store
    memory_file = BASE / "memory/store/index.jsonl"
    if memory_file.exists():
        for line in memory_file.read_text().strip().split("\n"):
            try:
                entry = json.loads(line)
                if entry.get("hypothesis") or entry.get("text"):
                    findings.append(entry)
            except:
                pass
    
    # Also check recon reports
    for recon in REPORTS.glob("*_recon.json"):
        try:
            data = json.loads(recon.read_text())
            if isinstance(data, list):
                findings.extend(data)
            elif isinstance(data, dict):
                findings.append(data)
        except:
            pass
    
    return findings

def draft_report(finding: dict) -> dict:
    """Use LLM to draft a full HackerOne report."""
    
    # Extract finding details
    title       = finding.get("title", finding.get("text","")[:80])
    hypothesis  = finding.get("hypothesis", finding.get("text",""))
    target      = finding.get("target", finding.get("host","unknown"))
    severity    = finding.get("severity", finding.get("score","medium"))
    evidence    = finding.get("evidence", finding.get("raw",""))
    endpoint    = finding.get("endpoint", finding.get("url",""))

    # Normalize severity
    if isinstance(severity, (int, float)):
        if severity >= 9:   severity = "critical"
        elif severity >= 7: severity = "high"
        elif severity >= 4: severity = "medium"
        else:               severity = "low"
    severity = str(severity).lower()
    if severity not in SEVERITY_MAP:
        severity = "medium"

    prompt = f"""You are N.O.V.A writing a professional HackerOne bug bounty report.
Write a complete, professional report based on this finding.

Finding details:
- Target: {target}
- Endpoint/URL: {endpoint}
- Issue: {hypothesis[:300]}
- Evidence: {evidence[:200]}
- Severity: {severity}

Write the report in this EXACT format:

## Title
[Clear, specific vulnerability title — e.g. "Reflected XSS in search parameter allows cookie theft"]

## Severity
{severity.upper()}

## Summary
[2-3 sentences describing the vulnerability clearly for a triage analyst]

## Steps to Reproduce
1. [Step one]
2. [Step two]
3. [Step three]
4. [Observe the result]

## Impact
[What can an attacker do with this? Be specific about business impact]

## Recommended Fix
[Specific remediation steps]

## Supporting Evidence
[What was observed — response codes, payloads, behavior]

Write a professional, credible report. Be specific and technical."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 800}
        }, timeout=300)
        content = resp.json()["response"].strip()
    except Exception as e:
        content = f"Report generation failed: {e}"

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d-%H%M"),
        "target": target,
        "severity": severity,
        "h1_severity": SEVERITY_MAP[severity]["h1"],
        "finding": finding,
        "report_content": content,
        "status": "draft"
    }
    return report

def save_report(report: dict) -> Path:
    ts       = report["generated_at"]
    target   = str(report["target"] or "unknown").replace("/","_").replace(":","")[:30]
    severity = report["severity"]
    outfile  = REPORTS / f"report_{ts}_{severity}_{target}.md"
    
    md = f"""# N.O.V.A Bug Report Draft
**Generated:** {ts}
**Target:** {report['target']}
**Severity:** {report['severity'].upper()} ({report['h1_severity']})
**Status:** DRAFT — Requires Travis review before submission

---

{report['report_content']}

---
*Report generated by N.O.V.A — review and verify all steps before submitting*
"""
    outfile.write_text(md)
    return outfile

def list_reportable(findings: list):
    print(f"\n[N.O.V.A] Reportable findings ({len(findings)} total):\n")
    for i, f in enumerate(findings[:10]):
        title = f.get("title", f.get("text",""))[:60]
        target = f.get("target", f.get("host","?"))
        sev = f.get("severity", f.get("score","?"))
        print(f"  [{i}] {title}")
        print(f"       Target: {target} | Severity: {sev}\n")

def main():
    findings = load_queue()
    
    # Filter out junk — require real target and hypothesis
    findings = [f for f in findings 
                if f.get("target") not in [None, "None", "example.com"]
                and (f.get("hypothesis") or f.get("text","").strip())]
    
    if not findings:
        print("[N.O.V.A] No reportable findings yet. Need real scan results.")
        print("[N.O.V.A] Run: nova scan <target>")
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        list_reportable(findings)
        return

    if len(sys.argv) > 2 and sys.argv[1] == "--id":
        idx = int(sys.argv[2])
        if idx >= len(findings):
            print(f"[N.O.V.A] No finding at index {idx}")
            sys.exit(1)
        finding = findings[idx]
    else:
        # Use highest severity finding
        def sev_score(f):
            s = str(f.get("severity", f.get("score","0"))).lower()
            return {"critical":4,"high":3,"medium":2,"low":1}.get(s, 0)
        finding = max(findings, key=sev_score)

    print(f"\n[N.O.V.A] Drafting report for: {finding.get('text','')[:60]}")
    print(f"[N.O.V.A] Target: {finding.get('target', finding.get('host','?'))}")
    print("[N.O.V.A] Generating report...\n")

    report  = draft_report(finding)
    outfile = save_report(report)

    print(f"{'═'*60}")
    print(report["report_content"][:800])
    print(f"{'═'*60}")
    print(f"\n[N.O.V.A] Full report saved → {outfile.name}")
    print(f"[N.O.V.A] Review carefully before submitting to HackerOne.")

if __name__ == "__main__":
    main()
