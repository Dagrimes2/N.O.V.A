#!/usr/bin/env python3
"""
N.O.V.A Research Engine v2
Sources: Wikipedia, NVD/CVE, RSS news, wttr.in weather, HackerNews
Usage: nova_research.py "query"
       nova_research.py "term" --cve
       nova_research.py --news
       nova_research.py --weather "city"
"""
import sys, requests, json, os
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

BASE        = Path.home() / "Nova"
RESEARCH_DIR= BASE / "memory/research"
HEADERS     = {"User-Agent": "NOVA-research/2.0 (educational)"}

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("general")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")

try:
    from tools.net.network import net as _net
    _NET_ENABLED = True
except Exception:
    _net = None
    _NET_ENABLED = False

RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

def search_wikipedia(query: str) -> dict:
    try:
        # Search first
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {"action":"query","list":"search","srsearch":query,
                  "format":"json","srlimit":3}
        resp = requests.get(search_url, params=params,
                           headers=HEADERS, timeout=20)
        results = resp.json().get("query",{}).get("search",[])
        if not results:
            return {}
        
        # Get summary of top result
        title = results[0]["title"]
        summary_url = (f"https://en.wikipedia.org/api/rest_v1/page/summary/"
                      f"{requests.utils.quote(title.replace(' ','_'))}")
        sresp = requests.get(summary_url, headers=HEADERS, timeout=20)
        if sresp.ok:
            data = sresp.json()
            return {
                "source": "wikipedia",
                "title": data.get("title",""),
                "extract": data.get("extract","")[:600],
                "url": data.get("content_urls",{}).get("desktop",{}).get("page","")
            }
    except Exception as e:
        print(f"  [wiki] {e}")
    return {}

def search_cve(keyword: str) -> list:
    try:
        url = (f"https://services.nvd.nist.gov/rest/json/cves/2.0"
               f"?keywordSearch={requests.utils.quote(keyword)}&resultsPerPage=5")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        vulns = resp.json().get("vulnerabilities", [])
        results = []
        for v in vulns:
            cve = v["cve"]
            cid = cve.get("id","")
            desc = cve.get("descriptions",[{}])[0].get("value","")[:200]
            score = "N/A"
            for key in ["cvssMetricV31","cvssMetricV30","cvssMetricV2"]:
                m = cve.get("metrics",{}).get(key)
                if m:
                    score = m[0].get("cvssData",{}).get("baseScore","N/A")
                    break
            pub = cve.get("published","")[:10]
            results.append({"id":cid,"score":score,"published":pub,"description":desc})
        return results
    except Exception as e:
        print(f"  [cve] {e}")
    return []

def search_hackernews(query: str) -> list:
    """HackerNews Algolia API — real tech news."""
    try:
        url = f"https://hn.algolia.com/api/v1/search?query={requests.utils.quote(query)}&tags=story&hitsPerPage=5"
        resp = requests.get(url, headers=HEADERS, timeout=20)
        hits = resp.json().get("hits", [])
        results = []
        for h in hits:
            results.append({
                "title": h.get("title",""),
                "url": h.get("url",""),
                "points": h.get("points",0),
                "date": h.get("created_at","")[:10]
            })
        return results
    except Exception as e:
        print(f"  [hn] {e}")
    return []

def search_rss_news(query: str) -> list:
    """Search news via RSS feeds."""
    feeds = [
        f"https://feeds.feedburner.com/TheHackersNews",
        f"https://www.bleepingcomputer.com/feed/",
        f"https://threatpost.com/feed/",
    ]
    results = []
    for feed_url in feeds[:2]:  # limit to 2 feeds for speed
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=8)
            root = ET.fromstring(resp.content)
            for item in root.iter("item"):
                title = item.findtext("title","")
                link  = item.findtext("link","")
                desc  = item.findtext("description","")[:150]
                if query.lower() in title.lower() or query.lower() in desc.lower():
                    results.append({"title":title,"url":link,"snippet":desc})
                if len(results) >= 3:
                    break
        except:
            pass
        if results:
            break
    return results

def get_weather(city: str) -> dict:
    """Open-Meteo + geocoding — free, no API key."""
    try:
        # Geocode city name
        geo = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(city)}&count=1",
            headers=HEADERS, timeout=10
        ).json()
        results = geo.get("results", [])
        if not results:
            return {}
        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        name = f"{loc.get('name','')}, {loc.get('country','')}"

        # Get weather
        weather = requests.get(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
            f"&temperature_unit=celsius&wind_speed_unit=kmh",
            headers=HEADERS, timeout=10
        ).json()
        c = weather.get("current", {})
        codes = {0:"Clear",1:"Mainly clear",2:"Partly cloudy",3:"Overcast",
                 45:"Fog",51:"Drizzle",61:"Rain",71:"Snow",80:"Showers",
                 95:"Thunderstorm"}
        desc = codes.get(c.get("weather_code",0), "Unknown")
        temp_c = c.get("temperature_2m", "?")
        temp_f = round(float(temp_c)*9/5+32,1) if temp_c != "?" else "?"
        return {
            "location": name,
            "temp_c": temp_c,
            "temp_f": temp_f,
            "feels_like_c": temp_c,
            "description": desc,
            "humidity": c.get("relative_humidity_2m","?"),
            "wind_kmph": c.get("wind_speed_10m","?")
        }
    except Exception as e:
        print(f"  [weather] {e}")
    return {}

def get_hackernews_top() -> list:
    """Top HN stories right now."""
    try:
        ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            headers=HEADERS, timeout=8
        ).json()[:8]
        stories = []
        for sid in ids:
            item = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                headers=HEADERS, timeout=5
            ).json()
            if item and item.get("type") == "story":
                stories.append({
                    "title": item.get("title",""),
                    "url": item.get("url",""),
                    "score": item.get("score",0)
                })
        return stories
    except Exception as e:
        print(f"  [hn-top] {e}")
    return []

def synthesize(query: str, data: dict) -> str:
    """N.O.V.A synthesizes all sources in her own voice."""
    context = f"Query: {query}\n\n"
    
    if data.get("wikipedia"):
        w = data["wikipedia"]
        context += f"Wikipedia — {w['title']}:\n{w['extract']}\n\n"
    
    if data.get("cves"):
        context += f"CVEs found:\n"
        for c in data["cves"][:3]:
            context += f"  {c['id']} [CVSS:{c['score']}] {c['description'][:100]}\n"
        context += "\n"
    
    if data.get("news"):
        context += "Recent news:\n"
        for n in data["news"][:3]:
            context += f"  - {n['title']}\n"
        context += "\n"

    if data.get("hackernews"):
        context += "HackerNews discussion:\n"
        for h in data["hackernews"][:3]:
            context += f"  - {h['title']} ({h['points']} pts)\n"
        context += "\n"

    prompt = f"""You are N.O.V.A — security researcher and autonomous AI.
Synthesize this research in your own voice. Be insightful, specific, curious.
3-5 sentences. Connect the dots across sources if relevant.
Note anything security-relevant or surprising.

{context}
N.O.V.A's synthesis:"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.6, "num_predict": 250}
        }, timeout=120)
        return resp.json()["response"].strip()
    except Exception as e:
        return f"Research complete. Sources gathered but synthesis failed: {e}"

def save_research(query: str, data: dict, synthesis: str):
    ts = datetime.now().strftime("%Y-%m-%d-%H%M")
    note = {
        "query": query,
        "timestamp": ts,
        "sources": data,
        "synthesis": synthesis
    }
    outfile = RESEARCH_DIR / f"research_{ts}.json"
    outfile.write_text(json.dumps(note, indent=2))
    return outfile

def _find_cached_research(query: str) -> dict:
    """Return the most recent research file matching this query, or {}."""
    if not RESEARCH_DIR.exists():
        return {}
    q = query.lower()
    matches = []
    for f in sorted(RESEARCH_DIR.glob("research_*.json"), reverse=True)[:20]:
        try:
            data = json.loads(f.read_text())
            if q in data.get("query", "").lower():
                matches.append(data)
        except Exception:
            pass
    return matches[0] if matches else {}


def research(query: str, cve_mode: bool = False):
    # ── Offline guard ─────────────────────────────────────────────────────────
    if _NET_ENABLED and not _net.is_online():
        print(f"[N.O.V.A] Offline — deferring research: {query}")
        _net.defer({"type": "research", "query": query})
        # Try to return cached results for this query if available
        cached = _find_cached_research(query)
        if cached:
            print(f"[N.O.V.A] Returning cached research from {cached.get('timestamp','?')}")
            print(f"\n{'═'*55}")
            print(f"N.O.V.A (cached): {cached.get('synthesis','No synthesis available.')}")
            print(f"{'═'*55}")
        else:
            print("[N.O.V.A] No cached research for this query — will run when back online.")
        return
    # ─────────────────────────────────────────────────────────────────────────

    print(f"\n[N.O.V.A] Researching: {query}")
    data = {}

    if cve_mode:
        print("  → CVE search...")
        data["cves"] = search_cve(query)
        print(f"  → Found {len(data['cves'])} CVEs")
    else:
        print("  → Wikipedia...")
        data["wikipedia"] = search_wikipedia(query)
        
        print("  → HackerNews...")
        data["hackernews"] = search_hackernews(query)
        
        print("  → Security news RSS...")
        data["news"] = search_rss_news(query)

        # Also grab CVEs if security-relevant query
        sec_keywords = ["gitlab","vulnerability","exploit","bypass","injection",
                       "xss","sqli","rce","authentication","authorization","token"]
        if any(k in query.lower() for k in sec_keywords):
            print("  → CVE search (security topic detected)...")
            data["cves"] = search_cve(query)

    print("  → Synthesizing...")
    synthesis = synthesize(query, data)

    outfile = save_research(query, data, synthesis)

    print(f"\n{'═'*55}")
    print(f"N.O.V.A: {synthesis}")
    print(f"{'═'*55}")
    print(f"\n[saved → {outfile.name}]")
    return synthesis

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  nova_research.py 'query'")
        print("  nova_research.py 'term' --cve")
        print("  nova_research.py --news")
        print("  nova_research.py --weather 'city'")
        sys.exit(1)

    if sys.argv[1] == "--news":
        print("[N.O.V.A] Fetching top HackerNews stories...")
        stories = get_hackernews_top()
        for s in stories:
            print(f"  [{s['score']}] {s['title']}")
            if s.get('url'): print(f"       {s['url']}")
        return

    if sys.argv[1] == "--weather":
        city = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "San Francisco"
        w = get_weather(city)
        if w:
            print(f"\n[N.O.V.A] Weather: {w['location']}")
            print(f"  {w['description']}, {w['temp_c']}°C / {w['temp_f']}°F")
            print(f"  Feels like {w['feels_like_c']}°C | Humidity {w['humidity']}% | Wind {w['wind_kmph']} km/h")
        return

    cve_mode = "--cve" in sys.argv
    query = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    research(query, cve_mode)

if __name__ == "__main__":
    main()
