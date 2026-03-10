#!/usr/bin/env python3
"""
N.O.V.A Report Generator v2
Reads operator_queue.txt → drafts HackerOne-ready reports
Usage: nova_report.py              draft from top queue item
       nova_report.py --list       show queue items
       nova_report.py --id <n>     draft specific item
"""
import json, requests, os, sys, re
from pathlib import Path
from datetime import datetime

BASE       = Path.home() / "Nova"
REPORTS    = BASE / "reports"
QUEUE_FILE = BASE / "reports/operator_queue.txt"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

REPORTS.mkdir(parents=True, exist_ok=True)

def parse_queue() -> list:
    """Parse operator_queue.txt into structured findings."""
    if not QUEUE_FILE.exists():
        return []
    
    text = QUEUE_FILE.read_text()
    findings = []
    
    # Split on numbered entries like [1], [2], etc.
    blocks = re.split(r'\n?\[(\d+)\]', text)
    
    i = 1
    while i < len(blocks):
        num = blocks[i]
        content = blocks[i+1] if i+1 < len(blocks) else ""
        i += 2
        
        lines = content.strip().split("\n")
        if not lines: continue
        
        target_line = lines[0].strip()
        finding = {
            "index": int(num),
            "target": target_line,
            "decision": "",
            "confidence": 0.0,
            "triage": "",
            "signals": [],
            "why": "",
            "next": ""
        }
        
        for line in lines[1:]:
            line = line.strip()
            if line.startswith("decision:"):
                finding["decision"] = line.split(":",1)[1].strip()
            elif line.startswith("confidence:"):
                try:
                    finding["confidence"] = float(line.split(":",1)[1].strip())
                except:
                    pass
            elif line.startswith("triage:"):
                finding["triage"] = line.split(":",1)[1].strip()
            elif line.startswith("signals:"):
                sigs = line.split(":",1)[1].strip()
                finding["signals"] = [s.strip() for s in sigs.split(",") if s.strip() and s.strip() != "none"]
            elif line.startswith("why:"):
                finding["why"] = line.split(":",1)[1].strip()
            elif line.startswith("next:"):
                finding["next"] = line.split(":",1)[1].strip()
        
        # Only include actionable findings
        if finding["decision"] == "act" and finding["target"]:
            findings.append(finding)
    
    return findings

def load_recon(target: str) -> dict:
    """Load recon data for a specific target."""
    safe = target.replace("https://","").replace("http://","").rstrip("/")
    safe = re.sub(r'[^a-zA-Z0-9._-]', '_', safe)
    recon_file = REPORTS / f"{safe}_recon.json"
    if recon_file.exists():
        try:
            return json.loads(recon_file.read_text())
        except:
            pass
    return {}

def infer_severity(finding: dict, recon: dict) -> str:
    """Infer severity from signals and recon data."""
    signals = finding.get("signals", [])
    sig_str = " ".join(signals).lower()
    triage  = finding.get("triage","").lower()
    
    if any(s in sig_str for s in ["rce","sqli","xxe","deserialization"]):
        return "critical"
    if any(s in sig_str for s in ["auth-path","error-403","error-401","bypass"]):
        return "high"
    if any(s in sig_str for s in ["xss","redirect","ssrf","idor"]):
        return "medium"
    if any(s in sig_str for s in ["error-500","interesting-param"]):
        return "medium"
    if recon.get("waf_detected"):
        return "low"
    return "low"

def draft_report(finding: dict, recon: dict) -> str:
    target   = finding["target"]
    signals  = ", ".join(finding["signals"]) if finding["signals"] else "none detected yet"
    triage   = finding["triage"]
    why      = finding["why"]
    severity = infer_severity(finding, recon)
    
    # Build recon summary
    recon_summary = ""
    if recon:
        headers = recon.get("security_headers", [])
        server  = recon.get("server","unknown")
        waf     = recon.get("waf_detected", False)
        score   = recon.get("risk_score", "?")
        recon_summary = f"""
Recon data:
- Server: {server}
- WAF detected: {waf}
- Risk score: {score}
- Security headers: {len(headers)} present
- Notable headers: {', '.join(h.split(':')[0] for h in headers[:3])}"""

    prompt = f"""You are N.O.V.A writing a professional HackerOne bug report.
Write a complete, submission-ready report. Be specific and technical.
This is a DRAFT — Travis will verify before submitting.

Target: {target}
Severity: {severity}
Signals observed: {signals}
Analysis: {triage}
Why flagged: {why}
{recon_summary}

Write in this EXACT format:

## Title
[Specific vulnerability title — be precise]

## Severity
{severity.upper()}

## Summary
[2-3 sentences describing the issue clearly for a triage analyst]

## Steps to Reproduce
1. Navigate to {target}
2. [Specific step]
3. [Specific step]
4. [Observed result]

## Impact
[What can an attacker achieve? Business impact.]

## Recommended Fix
[Specific remediation]

## Technical Evidence
Server: {recon.get('server','unknown')}
Signals: {signals}
WAF: {recon.get('waf_detected','unknown')}

Write a credible, professional report based on the evidence."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 700}
        }, timeout=300)
        return resp.json()["response"].strip()
    except Exception as e:
        return f"Generation failed: {e}"

def save_report(finding: dict, content: str, severity: str) -> Path:
    ts     = datetime.now().strftime("%Y-%m-%d-%H%M")
    target = re.sub(r'[^a-zA-Z0-9._-]', '_', finding["target"])[:40]
    outfile = REPORTS / f"report_{ts}_{severity}_{target}.md"
    
    md = f"""# N.O.V.A Bug Report Draft
**Generated:** {ts}  
**Target:** {finding['target']}  
**Severity:** {severity.upper()}  
**Confidence:** {finding['confidence']}  
**Status:** DRAFT — Requires Travis review before submission  

---

{content}

---
*Generated by N.O.V.A | Review all steps before submitting to HackerOne*
"""
    outfile.write_text(md)
    return outfile

def main():
    findings = parse_queue()
    
    if not findings:
        print("[N.O.V.A] No actionable findings in queue.")
        print("[N.O.V.A] Run: nova scan <target>")
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        print(f"\n[N.O.V.A] Actionable findings ({len(findings)}):\n")
        for f in findings[:15]:
            sev = infer_severity(f, load_recon(f["target"].split("/")[0]))
            print(f"  [{f['index']}] {f['target']}")
            print(f"       signals: {', '.join(f['signals']) or 'none'} | severity: {sev} | confidence: {f['confidence']}")
            print()
        return

    if len(sys.argv) > 2 and sys.argv[1] == "--id":
        idx = int(sys.argv[2])
        matches = [f for f in findings if f["index"] == idx]
        if not matches:
            print(f"[N.O.V.A] No finding with index {idx}")
            sys.exit(1)
        finding = matches[0]
    else:
        # Pick highest confidence with real signals first
        with_signals = [f for f in findings if f["signals"]]
        finding = with_signals[0] if with_signals else findings[0]

    target = finding["target"].split("/")[0]
    recon  = load_recon(target)
    severity = infer_severity(finding, recon)

    print(f"\n[N.O.V.A] Drafting report:")
    print(f"  Target:     {finding['target']}")
    print(f"  Signals:    {', '.join(finding['signals']) or 'none'}")
    print(f"  Severity:   {severity}")
    print(f"  Confidence: {finding['confidence']}")
    print(f"\n[N.O.V.A] Generating...\n")

    content = draft_report(finding, recon)
    outfile = save_report(finding, content, severity)

    print(f"{'═'*60}")
    print(content[:1000])
    print(f"{'═'*60}")
    print(f"\n[N.O.V.A] Saved → {outfile.name}")
    print(f"[N.O.V.A] Review before submitting.")

if __name__ == "__main__":
    main()
