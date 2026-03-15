#!/usr/bin/env python3
"""
N.O.V.A CVE Monitor

Polls NVD (National Vulnerability Database) for new CVEs matching
Nova's active bug bounty programs and research keywords.
Queues relevant CVEs for research automatically.

Free API: nvd.nist.gov/developers/vulnerabilities (no key needed for basic)
Rate limit: 5 req/30s unauthenticated, 50 req/30s with API key.

Usage:
    nova security cve poll              — check for new CVEs now
    nova security cve list              — show recent CVE findings
    nova security cve search <keyword>  — search NVD directly
"""
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE        = Path.home() / "Nova"
CVE_DIR     = BASE / "memory/security/cves"
SEEN_FILE   = BASE / "memory/security/seen_cves.json"
CVE_DIR.mkdir(parents=True, exist_ok=True)

NVD_URL  = "https://services.nvd.nist.gov/rest/json/cves/2.0"
HEADERS  = {"User-Agent": "NOVA-Security-Research/1.0"}

# Keywords that trigger research queue
RESEARCH_KEYWORDS = [
    "gitlab", "github", "oauth", "ssrf", "rce", "injection", "bypass",
    "privilege escalation", "authentication", "authorization", "deserialization",
    "xxe", "path traversal", "open redirect", "csrf", "xss", "sql injection",
]


def _load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        return set()


def _save_seen(seen: set) -> None:
    SEEN_FILE.write_text(json.dumps(list(seen)))


def _get_active_keywords() -> list[str]:
    """Pull keywords from active bug bounty program + static list."""
    keywords = list(RESEARCH_KEYWORDS)
    program_file = BASE / "state/active_program.json"
    if program_file.exists():
        try:
            prog = json.loads(program_file.read_text())
            name = prog.get("name", "").lower()
            if name:
                keywords.insert(0, name.split()[0])  # first word of program name
        except Exception:
            pass
    return keywords[:10]


def search_nvd(keyword: str = None, days_back: int = 7,
               max_results: int = 20) -> list[dict]:
    """
    Search NVD for recent CVEs.
    Returns list of normalized CVE dicts.
    """
    params = {"resultsPerPage": max_results}

    if keyword:
        params["keywordSearch"] = keyword
    else:
        # Recent CVEs published in last N days
        now   = datetime.now(timezone.utc)
        start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00.000")
        end   = now.strftime("%Y-%m-%dT23:59:59.999")
        params["pubStartDate"] = start
        params["pubEndDate"]   = end

    try:
        resp = requests.get(NVD_URL, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 429:
            time.sleep(6)
            resp = requests.get(NVD_URL, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []

        vulns = resp.json().get("vulnerabilities", [])
        result = []
        for v in vulns:
            cve = v.get("cve", {})
            cve_id = cve.get("id", "")
            desc_list = cve.get("descriptions", [])
            desc = next((d["value"] for d in desc_list if d["lang"] == "en"), "")
            metrics = cve.get("metrics", {})

            # CVSS score — try v3.1, then v3.0, then v2
            score = 0.0
            severity = "UNKNOWN"
            for key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                if key in metrics and metrics[key]:
                    m = metrics[key][0]
                    score    = m.get("cvssData", {}).get("baseScore", 0.0)
                    severity = m.get("cvssData", {}).get("baseSeverity", "UNKNOWN")
                    break

            result.append({
                "id":          cve_id,
                "description": desc[:300],
                "score":       score,
                "severity":    severity,
                "published":   cve.get("published", "")[:10],
                "url":         f"https://nvd.nist.gov/vuln/detail/{cve_id}",
            })
        return result
    except Exception as e:
        return [{"error": str(e)}]


def poll(verbose: bool = True) -> list[dict]:
    """
    Poll for new CVEs matching active program keywords.
    Queue relevant ones for research. Return newly found CVEs.
    """
    seen     = _load_seen()
    keywords = _get_active_keywords()
    new_cves = []

    for kw in keywords[:5]:  # limit API calls
        cves = search_nvd(keyword=kw, days_back=7, max_results=10)
        time.sleep(1)  # respect rate limit

        for cve in cves:
            if "error" in cve:
                continue
            cid = cve.get("id", "")
            if not cid or cid in seen:
                continue

            seen.add(cid)
            new_cves.append(cve)

            # Save individual CVE
            out = CVE_DIR / f"{cid}.json"
            out.write_text(json.dumps(cve, indent=2))

            # Queue for research if high severity
            if cve.get("score", 0) >= 7.0:
                _queue_research(cve)

            if verbose:
                col = "\033[31m" if cve["score"] >= 9 else (
                    "\033[33m" if cve["score"] >= 7 else "\033[36m")
                nc  = "\033[0m"
                print(f"  {col}[{cve['severity']:8s} {cve['score']:.1f}]{nc} "
                      f"{cid}: {cve['description'][:80]}")

    _save_seen(seen)
    if verbose and new_cves:
        print(f"\n  {len(new_cves)} new CVEs found — {sum(1 for c in new_cves if c.get('score',0)>=7)} high/critical queued for research")
    return new_cves


def _queue_research(cve: dict) -> None:
    """Add CVE to Nova's research queue."""
    try:
        queue_file = BASE / "memory/research_queue.json"
        queue = []
        if queue_file.exists():
            try:
                queue = json.loads(queue_file.read_text())
            except Exception:
                pass
        query = f"{cve['id']}: {cve['description'][:100]}"
        if not any(cve["id"] in str(q) for q in queue):
            queue.append({
                "query":    query,
                "priority": "high" if cve.get("score", 0) >= 9 else "normal",
                "source":   "cve_monitor",
                "added":    datetime.now(timezone.utc).isoformat(),
            })
            queue_file.write_text(json.dumps(queue, indent=2))
    except Exception:
        pass


def list_recent(n: int = 20) -> list[dict]:
    files = sorted(CVE_DIR.glob("CVE-*.json"), reverse=True)[:n]
    result = []
    for f in files:
        try:
            result.append(json.loads(f.read_text()))
        except Exception:
            pass
    return sorted(result, key=lambda x: x.get("score", 0), reverse=True)


def main():
    import sys
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    cmd = sys.argv[1] if len(sys.argv) > 1 else "poll"

    if cmd == "poll":
        print(f"\n{B}CVE Monitor — polling NVD...{NC}")
        kws = _get_active_keywords()
        print(f"{DIM}Keywords: {', '.join(kws[:5])}{NC}\n")
        new = poll()
        if not new:
            print(f"{DIM}No new CVEs matching current program keywords.{NC}")

    elif cmd == "list":
        cves = list_recent(20)
        if not cves:
            print(f"{DIM}No CVEs tracked yet. Run: nova security cve poll{NC}")
            return
        print(f"\n{B}Recent CVEs ({len(cves)}){NC}")
        for c in cves:
            sc = c.get("score", 0)
            col = R if sc >= 9 else (Y if sc >= 7 else C)
            print(f"  {col}{c['id']:18s}{NC} [{sc:.1f}] {c['description'][:70]}")

    elif cmd == "search" and len(sys.argv) > 2:
        kw = " ".join(sys.argv[2:])
        print(f"\n{B}Searching NVD for:{NC} {kw}")
        cves = search_nvd(keyword=kw, max_results=10)
        for c in cves:
            if "error" in c:
                print(f"  {R}{c['error']}{NC}")
                break
            sc = c.get("score", 0)
            col = R if sc >= 9 else (Y if sc >= 7 else C)
            print(f"  {col}{c['id']:18s}{NC} [{sc:.1f}] {c['description'][:80]}")
            print(f"  {DIM}{c['url']}{NC}")
    else:
        print("Usage: nova security cve [poll|list|search KEYWORD]")


if __name__ == "__main__":
    main()
