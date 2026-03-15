#!/usr/bin/env python3
"""
N.O.V.A Auto-Report Engine

When Nova finds a high-score finding (score > 8), she drafts a HackerOne-format
vulnerability report. Not submitted — always reviewed by Travis first.

Output: memory/security/reports/report_YYYY-MM-DD-HHMM.md
Usage:
    nova security report <finding_id>
    nova security report --latest
    nova security report --list
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE       = Path.home() / "Nova"
REPORT_DIR = BASE / "memory/security/reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("reasoning")
    TIMEOUT    = cfg.timeout("heavy")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 300

SEVERITY_MAP = {
    (0,  4):  "Low",
    (4,  7):  "Medium",
    (7,  9):  "High",
    (9,  99): "Critical",
}


def _severity(score: float) -> str:
    for (lo, hi), label in SEVERITY_MAP.items():
        if lo <= score < hi:
            return label
    return "Medium"


def _load_finding(finding_id: str) -> dict | None:
    """Try to find a finding by ID from the memory store."""
    index = BASE / "memory/store/index.jsonl"
    if index.exists():
        with open(index) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if str(entry.get("id", "")) == str(finding_id):
                        return entry
                    if finding_id in str(entry.get("host", "")) + str(entry.get("path", "")):
                        return entry
                except Exception:
                    pass
    return None


def draft_report(finding: dict, verbose: bool = True) -> str:
    """Draft a HackerOne-style vulnerability report for a finding."""
    host     = finding.get("host", "unknown")
    path     = finding.get("path", "/")
    method   = finding.get("method", "GET")
    score    = finding.get("score", 0)
    signals  = finding.get("signals", [])
    status   = finding.get("status", "")
    program  = finding.get("program", "")
    conf     = finding.get("confidence", 0.0)
    severity = _severity(score)

    # Infer vulnerability type from signals
    vuln_type = "Unknown Vulnerability"
    if "auth-path" in signals:
        vuln_type = "Unauthorized Access / Authentication Bypass"
    elif "numeric-id" in signals:
        vuln_type = "Insecure Direct Object Reference (IDOR)"
    elif "error-500" in signals:
        vuln_type = "Server-Side Error / Potential Code Execution"
    elif "error-403" in signals and "auth-path" in signals:
        vuln_type = "Access Control Issue"
    elif "large-response" in signals:
        vuln_type = "Information Disclosure"

    prompt = f"""You are N.O.V.A writing a HackerOne vulnerability report.

Finding details:
- Host: {host}
- Path: {path}
- Method: {method}
- HTTP Status: {status}
- Signals: {', '.join(signals)}
- Score: {score}/30
- Severity: {severity}
- Confidence: {conf:.0%}
- Inferred type: {vuln_type}
- Program: {program or 'unknown'}

Write a complete HackerOne vulnerability report with these sections:
1. Title (concise, describes the vulnerability)
2. Severity: {severity}
3. Summary (2-3 sentences: what is vulnerable, why it matters)
4. Steps to Reproduce (numbered, specific to the endpoint above)
5. Impact (what an attacker could do)
6. Suggested Fix (concrete recommendation)

Be specific to the endpoint. Be honest about confidence level ({conf:.0%}).
If confidence is low, note it in the summary.
Format as Markdown."""

    try:
        import requests as req
        resp = req.post(OLLAMA_URL, json={
            "model": MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.5, "num_predict": 600}
        }, timeout=TIMEOUT)
        report_body = resp.json().get("response", "").strip()
    except Exception as e:
        report_body = f"[Report generation failed: {e}]\n\nRaw finding:\n{json.dumps(finding, indent=2)}"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = (
        f"# N.O.V.A Draft Report — {ts}\n"
        f"**Status:** DRAFT — For Travis review only. NOT submitted.\n"
        f"**Score:** {score}/30  **Confidence:** {conf:.0%}  **Severity:** {severity}\n\n"
        f"---\n\n"
        f"{report_body}\n\n"
        f"---\n"
        f"*Auto-drafted by N.O.V.A. Verify before submitting.*\n"
    )

    # Save report
    ts_fn = datetime.now().strftime("%Y-%m-%d-%H%M")
    out   = REPORT_DIR / f"report_{host.replace('.','_')}_{ts_fn}.md"
    out.write_text(report)

    if verbose:
        print(f"\n[report] Drafted → {out.name}")
        print(f"[report] Severity: {severity}  Score: {score}  Confidence: {conf:.0%}")

    # Notify Travis
    try:
        from tools.notify.telegram import send_event
        send_event(
            f"N.O.V.A Draft Report — {severity}",
            f"{vuln_type} on {host}{path}\nScore: {score}  Confidence: {conf:.0%}\nFile: {out.name}",
            emoji="📋"
        )
    except Exception:
        pass

    return str(out)


def auto_draft_high_scores(min_score: float = 8.0) -> list[str]:
    """Scan memory index for high-score findings and draft reports for unprocessed ones."""
    index   = BASE / "memory/store/index.jsonl"
    drafted = set(f.stem for f in REPORT_DIR.glob("report_*.md"))
    reports = []

    if not index.exists():
        return []

    with open(index) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                score = entry.get("score", 0)
                host  = entry.get("host", "unknown").replace(".", "_")
                if score >= min_score:
                    # Check if not already reported
                    marker = f"report_{host}"
                    if not any(marker in d for d in drafted):
                        path = draft_report(entry, verbose=False)
                        reports.append(path)
                        drafted.add(Path(path).stem)
            except Exception:
                pass

    return reports


def list_reports(n: int = 10) -> list[dict]:
    files = sorted(REPORT_DIR.glob("report_*.md"), reverse=True)[:n]
    result = []
    for f in files:
        result.append({
            "file": f.name,
            "size": f.stat().st_size,
            "ts":   f.stem.split("_")[-2] + "-" + f.stem.split("_")[-1],
        })
    return result


def main():
    import sys
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    cmd  = sys.argv[1] if len(sys.argv) > 1 else "--list"
    rest = sys.argv[2:] if len(sys.argv) > 2 else []

    if cmd == "--list":
        reports = list_reports()
        if not reports:
            print(f"{DIM}No reports yet. Reports auto-draft for findings with score > 8.{NC}")
            return
        print(f"\n{B}Draft Reports ({len(reports)}){NC}")
        for r in reports:
            print(f"  {C}{r['file']}{NC}  {DIM}{r['size']} bytes{NC}")

    elif cmd == "--latest":
        reports = list_reports(1)
        if not reports:
            print(f"{DIM}No reports yet.{NC}")
            return
        f = REPORT_DIR / reports[0]["file"]
        print(f.read_text())

    elif cmd == "--auto":
        min_score = float(rest[0]) if rest else 8.0
        drafted = auto_draft_high_scores(min_score)
        if drafted:
            print(f"{G}Drafted {len(drafted)} reports.{NC}")
            for d in drafted:
                print(f"  → {Path(d).name}")
        else:
            print(f"{DIM}No findings above score {min_score} without existing reports.{NC}")

    elif cmd and not cmd.startswith("--"):
        finding = _load_finding(cmd)
        if finding:
            draft_report(finding)
        else:
            print(f"{R}Finding '{cmd}' not found in memory index.{NC}")

    else:
        print("Usage: nova security report [--list|--latest|--auto|<finding_id>]")


if __name__ == "__main__":
    main()
