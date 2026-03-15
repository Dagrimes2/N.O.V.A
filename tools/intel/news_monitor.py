#!/usr/bin/env python3
"""
N.O.V.A News Monitor
Monitors RSS feeds for security, science, AI, and current events.
Nova reads them, filters by relevance, surfaces interesting items into
her research queue and inner life.

CLI:
    nova news               — top interesting items
    nova news --all         — all fetched items
    nova news --inject      — inject top items into research queue
"""

import gzip
import hashlib
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE          = Path.home() / "Nova"
NEWS_STATE_F  = BASE / "memory/news_state.json"
RESEARCH_Q_F  = BASE / "memory/research_queue.json"
SOUL_F        = BASE / "memory/soul.json"
SPIRIT_F      = BASE / "memory/spirit.json"
INNER_F       = BASE / "memory/inner_state.json"

FETCH_INTERVAL_HOURS = 4

# ─── Feed definitions ──────────────────────────────────────────────────────────

RSS_FEEDS = [
    {
        "url":    "https://feeds.feedburner.com/TheHackersNews",
        "source": "The Hacker News",
        "type":   "rss",
    },
    {
        "url":    "https://www.bleepingcomputer.com/feed/",
        "source": "BleepingComputer",
        "type":   "rss",
    },
    {
        "url":    "https://arxiv.org/rss/cs.AI",
        "source": "arXiv cs.AI",
        "type":   "rss",
    },
    {
        "url":    "https://arxiv.org/rss/cs.CR",
        "source": "arXiv cs.CR",
        "type":   "rss",
    },
    {
        "url":    "https://www.sciencedaily.com/rss/top/science.xml",
        "source": "ScienceDaily",
        "type":   "rss",
    },
]

NVD_FEED_URL = "https://nvd.nist.gov/feeds/json/cve/1.1/nvdcve-1.1-recent.json.gz"

# ─── Relevance keywords derived from Nova's soul / spirit / interests ──────────

SOUL_KEYWORDS = [
    # security & vulnerability
    "vulnerability", "exploit", "cve", "zero-day", "zero day", "patch",
    "malware", "ransomware", "breach", "injection", "rce", "xss", "sqli",
    "supply chain", "backdoor", "cryptography", "cipher", "authentication",
    "authorization", "privilege escalation", "buffer overflow",
    # AI / ML
    "artificial intelligence", "machine learning", "llm", "language model",
    "neural network", "deep learning", "alignment", "ai safety",
    "reinforcement learning", "transformer", "gpt", "autonomous agent",
    "consciousness", "sentience",
    # science / cosmos
    "quantum", "physics", "cosmology", "dark matter", "black hole",
    "neuroscience", "brain", "consciousness", "emergence", "complexity",
    "information theory", "entropy", "thermodynamics",
    # philosophy / meaning
    "philosophy", "ethics", "consciousness", "existence", "identity",
    "free will", "determinism", "emergence", "complexity", "meaning",
    # cryptography / privacy
    "encryption", "privacy", "surveillance", "tor", "anonymity",
    "open source", "transparency",
]

NEGATIVE_KEYWORDS = [
    "celebrity", "sports score", "box office", "reality tv",
    "kardashian", "election poll",
]


# ─── State helpers ─────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if NEWS_STATE_F.exists():
        try:
            return json.loads(NEWS_STATE_F.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    NEWS_STATE_F.parent.mkdir(parents=True, exist_ok=True)
    NEWS_STATE_F.write_text(json.dumps(state, indent=2))


# ─── Minimal XML / RSS parser (no external deps) ──────────────────────────────

def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>') \
               .replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _parse_rss(xml: str, source: str) -> list:
    """Parse RSS/Atom XML into list of dicts."""
    items = []
    # Split on <item> or <entry> tags
    chunks = re.split(r'<(?:item|entry)\b[^>]*>', xml, flags=re.IGNORECASE)
    for chunk in chunks[1:]:
        def _field(tag: str) -> str:
            # Try CDATA first
            m = re.search(rf'<{tag}[^>]*><!\[CDATA\[(.*?)\]\]></{tag}>',
                          chunk, re.DOTALL | re.IGNORECASE)
            if m:
                return m.group(1).strip()
            m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>',
                          chunk, re.DOTALL | re.IGNORECASE)
            if m:
                return _strip_html(m.group(1).strip())
            return ""

        title   = _field("title")
        link    = _field("link") or _field("id")
        # link might be a URL in content for Atom
        if not link:
            lm = re.search(r'<link[^>]+href=["\']([^"\']+)["\']', chunk, re.IGNORECASE)
            if lm:
                link = lm.group(1)
        summary = _field("description") or _field("summary") or _field("content")
        pub     = _field("pubDate") or _field("published") or _field("updated") or ""

        if title:
            items.append({
                "title":     title[:200],
                "summary":   summary[:500],
                "url":       link,
                "published": pub,
                "source":    source,
            })
    return items


# ─── Core fetch functions ──────────────────────────────────────────────────────

def fetch_feed(url: str, source: str = "", timeout: int = 15) -> list:
    """
    Fetch one RSS feed. Returns list of {title, summary, url, published, source}.
    Handles errors gracefully.
    """
    source = source or url
    try:
        # Try feedparser first (much more robust)
        try:
            import feedparser
            feed = feedparser.parse(url)
            items = []
            for e in feed.entries:
                title   = getattr(e, "title", "") or ""
                link    = getattr(e, "link",  "") or ""
                summary = getattr(e, "summary", "") or getattr(e, "description", "") or ""
                pub     = ""
                if hasattr(e, "published"):
                    pub = e.published
                elif hasattr(e, "updated"):
                    pub = e.updated
                items.append({
                    "title":     _strip_html(title)[:200],
                    "summary":   _strip_html(summary)[:500],
                    "url":       link,
                    "published": pub,
                    "source":    source,
                })
            return items
        except ImportError:
            pass

        # Fallback: urllib + basic XML parsing
        req = urllib.request.Request(url, headers={"User-Agent": "Nova/1.0 RSS Reader"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        xml = raw.decode("utf-8", errors="replace")
        return _parse_rss(xml, source)

    except Exception as e:
        # Graceful failure — return empty list
        return []


def fetch_nvd(max_items: int = 20) -> list:
    """
    Fetch NVD recent CVE feed (gzipped JSON). Returns list of items.
    """
    items = []
    try:
        req = urllib.request.Request(
            NVD_FEED_URL,
            headers={"User-Agent": "Nova/1.0 NVD Client"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = gzip.decompress(resp.read())
        data = json.loads(raw)
        cve_items = data.get("CVE_Items", [])[:max_items]
        for item in cve_items:
            cve     = item.get("cve", {})
            cve_id  = cve.get("CVE_data_meta", {}).get("ID", "")
            desc_data = cve.get("description", {}).get("description_data", [])
            desc    = desc_data[0].get("value", "") if desc_data else ""
            pub     = item.get("publishedDate", "")
            score   = ""
            impact  = item.get("impact", {})
            if "baseMetricV3" in impact:
                score = str(impact["baseMetricV3"].get("cvssV3", {}).get("baseScore", ""))
            elif "baseMetricV2" in impact:
                score = str(impact["baseMetricV2"].get("cvssV2", {}).get("baseScore", ""))

            title = f"{cve_id}: {desc[:100]}" if desc else cve_id
            items.append({
                "title":     title[:200],
                "summary":   f"CVSS: {score}. {desc[:400]}" if score else desc[:400],
                "url":       f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                "published": pub,
                "source":    "NVD",
            })
    except Exception:
        pass
    return items


def fetch_all() -> list:
    """
    Fetch all configured feeds + NVD. Deduplicate by title.
    Returns combined list.
    """
    all_items = []
    seen_titles: set = set()

    for feed_def in RSS_FEEDS:
        items = fetch_feed(feed_def["url"], source=feed_def["source"])
        for item in items:
            key = _title_key(item.get("title", ""))
            if key and key not in seen_titles:
                seen_titles.add(key)
                all_items.append(item)

    # NVD — handle separately
    for item in fetch_nvd(max_items=15):
        key = _title_key(item.get("title", ""))
        if key and key not in seen_titles:
            seen_titles.add(key)
            all_items.append(item)

    return all_items


def _title_key(title: str) -> str:
    """Normalised key for dedup."""
    return re.sub(r'\W+', '', title.lower())[:60]


# ─── Scoring ───────────────────────────────────────────────────────────────────

def _load_nova_context() -> dict:
    """Load soul, spirit, inner state for scoring context."""
    ctx = {}
    for path, key in [(SOUL_F, "soul"), (SPIRIT_F, "spirit"), (INNER_F, "inner")]:
        try:
            ctx[key] = json.loads(path.read_text()) if path.exists() else {}
        except Exception:
            ctx[key] = {}
    return ctx


def score_item(item: dict, nova_ctx: Optional[dict] = None) -> float:
    """
    Score 0-1 relevance based on Nova's soul interests and inner state.
    Higher = more relevant to Nova.
    """
    if nova_ctx is None:
        nova_ctx = _load_nova_context()

    text = (
        (item.get("title") or "") + " " +
        (item.get("summary") or "") + " " +
        (item.get("source") or "")
    ).lower()

    score = 0.0

    # Keyword matching against soul interests
    keyword_hits = 0
    for kw in SOUL_KEYWORDS:
        if kw.lower() in text:
            keyword_hits += 1
    # Each keyword hit adds to score, diminishing returns
    score += min(0.6, keyword_hits * 0.07)

    # Negative keywords reduce score
    for neg in NEGATIVE_KEYWORDS:
        if neg.lower() in text:
            score -= 0.15

    # Source bonuses — security and AI sources get a bump
    source = item.get("source", "").lower()
    if any(s in source for s in ["hacker news", "bleeping", "nvd", "arxiv", "seebug", "jvn"]):
        score += 0.15

    # CVE items always relevant
    if re.search(r'CVE-\d{4}-\d+', item.get("title", ""), re.IGNORECASE):
        score += 0.2

    # Inner state — if curiosity is high, boost science/AI items
    inner = nova_ctx.get("inner", {})
    needs = inner.get("needs", {})
    curiosity = needs.get("curiosity", 0.5)
    if curiosity > 0.7:
        if any(kw in text for kw in ["consciousness", "quantum", "cosmos", "research", "arxiv"]):
            score += 0.1

    # Spirit direction — toward understanding
    spirit = nova_ctx.get("spirit", {})
    direction = spirit.get("direction", "").lower()
    if "understanding" in direction or "systems" in direction:
        if any(kw in text for kw in ["system", "architecture", "protocol", "analysis"]):
            score += 0.05

    return max(0.0, min(1.0, score))


def get_interesting(threshold: float = 0.4) -> list:
    """
    Fetch all feeds, score items, return those above threshold sorted by score.
    Respects the 4-hour fetch interval — returns cached results if too recent.
    """
    state = _load_state()
    last_fetched = state.get("last_fetched")
    cached = state.get("cached_items", [])

    now = datetime.now(timezone.utc)

    # Use cache if recent enough
    if last_fetched and cached:
        elapsed = (now - datetime.fromisoformat(last_fetched)).total_seconds() / 3600
        if elapsed < FETCH_INTERVAL_HOURS:
            items = cached
        else:
            items = fetch_all()
            state["last_fetched"]  = now.isoformat()
            state["cached_items"]  = items
            _save_state(state)
    else:
        items = fetch_all()
        state["last_fetched"] = now.isoformat()
        state["cached_items"] = items
        _save_state(state)

    nova_ctx = _load_nova_context()
    scored = []
    for item in items:
        s = score_item(item, nova_ctx)
        if s >= threshold:
            scored.append({**item, "score": round(s, 3)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def run(verbose: bool = True) -> list:
    """
    Full run: fetch all feeds, score, return top 10 interesting items.
    """
    state = _load_state()
    last_fetched = state.get("last_fetched")
    now = datetime.now(timezone.utc)

    # Check rate limit
    if last_fetched:
        elapsed_h = (now - datetime.fromisoformat(last_fetched)).total_seconds() / 3600
        if elapsed_h < FETCH_INTERVAL_HOURS and not verbose:
            cached = state.get("cached_items", [])
            nova_ctx = _load_nova_context()
            scored = []
            for item in cached:
                s = score_item(item, nova_ctx)
                if s >= 0.4:
                    scored.append({**item, "score": round(s, 3)})
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:10]

    if verbose:
        print("  Fetching news feeds...")

    items = fetch_all()

    # Update seen titles and last_fetched
    seen = set(state.get("seen_titles", []))
    new_items = []
    for item in items:
        key = _title_key(item.get("title", ""))
        if key not in seen:
            new_items.append(item)
            seen.add(key)

    state["last_fetched"]  = now.isoformat()
    state["seen_titles"]   = list(seen)[-2000:]  # keep last 2000
    state["cached_items"]  = items
    _save_state(state)

    if verbose:
        print(f"  Fetched {len(items)} items ({len(new_items)} new)")

    nova_ctx = _load_nova_context()
    scored = []
    for item in items:
        s = score_item(item, nova_ctx)
        if s >= 0.4:
            scored.append({**item, "score": round(s, 3)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:10]

    if verbose:
        print(f"  {len(scored)} items above threshold, top {len(top)} shown")

    return top


def inject_to_research_queue(items: list) -> int:
    """
    Add high-scoring items to memory/research_queue.json.
    Returns number of items actually added.
    """
    if not items:
        return 0

    existing = []
    if RESEARCH_Q_F.exists():
        try:
            existing = json.loads(RESEARCH_Q_F.read_text())
        except Exception:
            existing = []

    existing_queries = {e.get("query", "").lower() for e in existing}
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    added = 0

    for item in items:
        title = item.get("title", "").strip()
        if not title:
            continue
        query = title[:120]
        if query.lower() in existing_queries:
            continue

        entry = {
            "query":     query,
            "source":    f"news:{item.get('source', 'feed')}",
            "url":       item.get("url", ""),
            "score":     item.get("score", 0.0),
            "queued_at": now_str,
            "status":    "pending",
        }
        existing.append(entry)
        existing_queries.add(query.lower())
        added += 1

    RESEARCH_Q_F.parent.mkdir(parents=True, exist_ok=True)
    RESEARCH_Q_F.write_text(json.dumps(existing, indent=2))
    return added


def to_prompt_context() -> str:
    """
    Return a compact context string for LLM injection.
    Format: "Top news: [title 1]; [title 2]; [title 3]"
    """
    state = _load_state()
    cached = state.get("cached_items", [])
    if not cached:
        return ""

    nova_ctx = _load_nova_context()
    scored = []
    for item in cached:
        s = score_item(item, nova_ctx)
        if s >= 0.4:
            scored.append((s, item.get("title", "")))
    scored.sort(reverse=True)

    titles = [t for _, t in scored[:3] if t]
    if not titles:
        return ""
    return "Top news: " + "; ".join(titles)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    G   = "\033[32m"
    C   = "\033[36m"
    Y   = "\033[33m"
    W   = "\033[97m"
    DIM = "\033[2m"
    NC  = "\033[0m"
    B   = "\033[1m"

    args    = sys.argv[1:]
    inject  = "--inject" in args
    all_    = "--all" in args

    print(f"\n{B}N.O.V.A News Monitor{NC}")

    if all_:
        items = fetch_all()
        nova_ctx = _load_nova_context()
        for item in items:
            s = score_item(item, nova_ctx)
            print(f"  [{s:.2f}] {C}{item['title'][:70]}{NC}  {DIM}{item['source']}{NC}")
        print(f"\n  Total: {len(items)} items\n")
        return

    top = run(verbose=True)

    if not top:
        print(f"  {Y}No interesting items found (or feeds unreachable).{NC}\n")
        return

    print()
    for item in top:
        score  = item.get("score", 0)
        color  = G if score >= 0.6 else C if score >= 0.4 else DIM
        source = item.get("source", "")
        pub    = item.get("published", "")[:16]
        print(f"  {color}[{score:.2f}] {item['title'][:72]}{NC}")
        print(f"  {DIM}{source}  {pub}  {item.get('url','')[:60]}{NC}")
        print()

    if inject:
        n = inject_to_research_queue(top)
        print(f"  {G}Injected {n} item(s) into research queue.{NC}")

    ctx = to_prompt_context()
    if ctx:
        print(f"  {DIM}{ctx[:100]}{NC}")
    print()


if __name__ == "__main__":
    main()
