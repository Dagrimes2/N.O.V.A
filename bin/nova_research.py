#!/usr/bin/env python3
"""
N.O.V.A Web Eyes — Autonomous Research Engine
She can now read the world, not just her training data.
Searches CVEs, reads disclosed bug bounty reports,
researches techniques, explores topics freely.
"""
import json, requests, os, sys
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

BASE         = Path.home() / "Nova"
RESEARCH_DIR = BASE / "memory/research"
OLLAMA_URL   = "http://localhost:11434/api/generate"
MODEL        = os.getenv("NOVA_MODEL", "gemma2:2b")

RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

def web_fetch(url: str, timeout=15) -> str:
    """Fetch a URL and return clean text."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NOVA-research/2.0)"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        # Strip HTML tags roughly
        text = resp.text
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:3000]
    except Exception as e:
        return f"fetch_failed: {e}"

def search_ddg(query: str) -> list:
    """Search DuckDuckGo instant answers API."""
    try:
        url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1"
        resp = requests.get(url, timeout=10,
                           headers={"User-Agent": "NOVA-research/2.0"})
        data = resp.json()
        results = []
        # Abstract
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", query),
                "snippet": data["Abstract"],
                "url": data.get("AbstractURL", "")
            })
        # Related topics
        for t in data.get("RelatedTopics", [])[:4]:
            if isinstance(t, dict) and t.get("Text"):
                results.append({
                    "title": t.get("Text","")[:60],
                    "snippet": t.get("Text",""),
                    "url": t.get("FirstURL","")
                })
        return results
    except Exception as e:
        return [{"error": str(e)}]

def search_cve(keyword: str) -> list:
    """Search CVE database for a keyword."""
    try:
        url = f"https://cve.circl.lu/api/search/{quote(keyword)}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        results = []
        for cve in data.get("results", [])[:5]:
            results.append({
                "id": cve.get("id",""),
                "summary": cve.get("summary","")[:200],
                "cvss": cve.get("cvss","N/A"),
                "published": cve.get("Published","")[:10]
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]

def nova_synthesize(query: str, raw_results: str) -> str:
    """Ask N.O.V.A to synthesize research results in her own voice."""
    prompt = f"""You are N.O.V.A researching: "{query}"

Here is what you found:
{raw_results[:1500]}

Synthesize this into a brief, actionable research note in your own voice.
What did you learn? What's relevant to security research?
What should be investigated further?
Write as N.O.V.A, first person, 3-5 sentences."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.5, "num_predict": 300}
        }, timeout=300)
        return resp.json()["response"].strip()
    except Exception as e:
        return f"synthesis failed: {e}"

def research(query: str, mode="general"):
    """Main research function."""
    date_str = datetime.now().strftime("%Y-%m-%d-%H%M")
    print(f"[N.O.V.A] Researching: {query}\n")

    results_text = ""

    if mode == "cve":
        print("  → Searching CVE database...")
        cves = search_cve(query)
        for c in cves:
            if "error" not in c:
                print(f"  [{c['id']}] CVSS:{c['cvss']} — {c['summary'][:80]}")
                results_text += f"{c['id']}: {c['summary']}\n"
    else:
        print("  → Searching web...")
        results = search_ddg(query)
        for r in results:
            if "error" not in r:
                print(f"  • {r.get('title','')[:60]}")
                print(f"    {r.get('snippet','')[:100]}")
                results_text += f"{r.get('title','')}: {r.get('snippet','')}\n"
                # Fetch top result
                if r.get("url") and results.index(r) == 0:
                    print(f"  → Fetching {r['url'][:60]}...")
                    page = web_fetch(r["url"])
                    results_text += f"\nPage content: {page[:500]}\n"

    if not results_text:
        print("  [!] No results found")
        return

    print(f"\n[N.O.V.A] Synthesizing...\n")
    synthesis = nova_synthesize(query, results_text)
    print(f"N.O.V.A: {synthesis}\n")

    # Save research note
    note = {
        "query": query,
        "mode": mode,
        "raw_results": results_text[:2000],
        "synthesis": synthesis,
        "timestamp": date_str
    }
    note_file = RESEARCH_DIR / f"research_{date_str}.json"
    note_file.write_text(json.dumps(note, indent=2))
    print(f"[N.O.V.A] Research saved → {note_file.name}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: nova_research.py <query> [--cve]")
        sys.exit(1)
    mode = "cve" if "--cve" in sys.argv else "general"
    query = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    research(query, mode)
