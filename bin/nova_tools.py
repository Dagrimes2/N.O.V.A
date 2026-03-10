#!/usr/bin/env python3
"""
N.O.V.A Tool Engine — called from chat in real time.
Nova can research, whois, CVE lookup, ping, and scan
directly during conversation without leaving the terminal.
"""
import re, requests, subprocess, json
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = "gemma2:2b"

def tool_whois(domain: str) -> str:
    try:
        result = subprocess.run(
            ["whois", domain], capture_output=True, text=True, timeout=10
        )
        lines = [l for l in result.stdout.split("\n")
                 if any(k in l.lower() for k in
                 ["registrar","registered","expires","name server","org","country"])]
        return "\n".join(lines[:8]) or "No whois data found."
    except Exception as e:
        return f"whois failed: {e}"

def tool_cve(keyword: str) -> str:
    try:
        url = (f"https://services.nvd.nist.gov/rest/json/cves/2.0"
               f"?keywordSearch={requests.utils.quote(keyword)}&resultsPerPage=3")
        resp = requests.get(url, timeout=15,
                           headers={"User-Agent": "NOVA-tools/2.0"})
        vulns = resp.json().get("vulnerabilities", [])
        if not vulns:
            return f"No CVEs found for: {keyword}"
        lines = []
        for v in vulns:
            cve   = v["cve"]
            cid   = cve.get("id","")
            desc  = cve.get("descriptions",[{}])[0].get("value","")[:150]
            score = "N/A"
            for key in ["cvssMetricV31","cvssMetricV30","cvssMetricV2"]:
                m = cve.get("metrics",{}).get(key)
                if m:
                    score = m[0].get("cvssData",{}).get("baseScore","N/A")
                    break
            lines.append(f"{cid} [CVSS:{score}] — {desc}")
        return "\n".join(lines)
    except Exception as e:
        return f"CVE lookup failed: {e}"

def tool_ping(host: str) -> str:
    try:
        result = subprocess.run(
            ["/usr/bin/ping", "-c", "2", "-W", "2", host],
            capture_output=True, text=True, timeout=8
        )
        if result.returncode == 0:
            match = re.search(r"time=(\S+)", result.stdout)
            return f"{host} is UP — latency {match.group(1) if match else '?'}ms"
        return f"{host} is DOWN or unreachable"
    except Exception as e:
        return f"ping failed: {e}"

def tool_dns(domain: str) -> str:
    try:
        result = subprocess.run(
            ["dig", "+short", domain],
            capture_output=True, text=True, timeout=8
        )
        out = result.stdout.strip()
        return f"{domain} resolves to: {out}" if out else f"No DNS record for {domain}"
    except Exception as e:
        return f"dns failed: {e}"

def tool_research(query: str) -> str:
    try:
        url = (f"https://en.wikipedia.org/api/rest_v1/page/summary/"
               f"{requests.utils.quote(query.replace(' ','_'))}")
        resp = requests.get(url, timeout=10,
                           headers={"User-Agent": "NOVA-tools/2.0"})
        if resp.ok:
            data = resp.json()
            extract = data.get("extract","")
            if extract:
                return extract[:400]
        # Fallback to CVE if security query
        if any(w in query.lower() for w in ["cve","vuln","exploit","bypass"]):
            return tool_cve(query)
        return "No results found."
    except Exception as e:
        return f"research failed: {e}"

def detect_tool_call(message: str) -> tuple:
    """
    Detect if N.O.V.A wants to use a tool.
    Returns (tool_name, argument) or (None, None)
    """
    patterns = [
        (r'\[WHOIS:([^\]]+)\]',    'whois'),
        (r'\[CVE:([^\]]+)\]',      'cve'),
        (r'\[PING:([^\]]+)\]',     'ping'),
        (r'\[DNS:([^\]]+)\]',      'dns'),
        (r'\[RESEARCH:([^\]]+)\]', 'research'),
    ]
    for pattern, tool in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return tool, match.group(1).strip()
    return None, None

def run_tool(tool: str, arg: str) -> str:
    tools = {
        'whois':    tool_whois,
        'cve':      tool_cve,
        'ping':     tool_ping,
        'dns':      tool_dns,
        'research': tool_research,
    }
    fn = tools.get(tool)
    return fn(arg) if fn else f"Unknown tool: {tool}"

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        print(run_tool(sys.argv[1], " ".join(sys.argv[2:])))
