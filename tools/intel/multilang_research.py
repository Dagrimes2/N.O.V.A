#!/usr/bin/env python3
"""
N.O.V.A Multi-Language Research
Nova researches non-English sources — many CVEs and 0-days surface in Chinese,
Japanese, Korean, and Russian forums before English-language sources.

CLI:
    nova multilang                      — full scan, translate top items
    nova multilang --source chinese     — only Chinese sources
    nova multilang --source japanese
    nova multilang --source russian
    nova multilang --source korean
    nova multilang --inject             — inject findings into research queue
"""

import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE          = Path.home() / "Nova"
NEWS_STATE_F  = BASE / "memory/news_state.json"
RESEARCH_Q_F  = BASE / "memory/research_queue.json"

FETCH_INTERVAL_HOURS = 6

# ─── Non-English security/research sources ────────────────────────────────────

SOURCES = {
    "chinese": [
        {
            "name": "安全客 (Anquanke)",
            "url":  "https://www.anquanke.com/rss",
            "lang": "zh",
        },
        {
            "name": "Seebug Paper",
            "url":  "https://paper.seebug.org/rss",
            "lang": "zh",
        },
    ],
    "japanese": [
        {
            "name": "JVN (Japan Vulnerability Notes)",
            "url":  "https://jvn.jp/rss/index.html",
            "lang": "ja",
        },
    ],
    "russian": [
        {
            "name": "SecurityLab.ru",
            "url":  "https://www.securitylab.ru/rss/",
            "lang": "ru",
        },
    ],
    "korean": [
        {
            "name": "보안뉴스 (Boannews)",
            "url":  "https://www.boannews.com/rss",
            "lang": "ko",
        },
    ],
}

LANGUAGE_NAMES = {
    "zh": "Chinese",
    "ja": "Japanese",
    "ru": "Russian",
    "ko": "Korean",
}


# ─── LLM helper ───────────────────────────────────────────────────────────────

def _llm(prompt: str, temperature: float = 0.3, max_tokens: int = 300) -> str:
    """Call local Ollama LLM. Returns response string or empty."""
    _nova_root = str(BASE)
    if _nova_root not in sys.path:
        sys.path.insert(0, _nova_root)
    try:
        from tools.config import cfg as _cfg
        url   = _cfg.ollama_url
        model = _cfg.model("reasoning")
    except Exception:
        url   = "http://localhost:11434/api/generate"
        model = "dolphin-mistral"
    try:
        import requests
        resp = requests.post(url, json={
            "model":   model,
            "prompt":  prompt,
            "stream":  False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }, timeout=90)
        return resp.json().get("response", "").strip()
    except Exception:
        return ""


# ─── Minimal RSS parser ───────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', text)
    text = (text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                .replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' '))
    return re.sub(r'\s+', ' ', text).strip()


def _parse_rss_xml(xml: str, source_name: str, lang: str) -> list:
    items = []
    chunks = re.split(r'<(?:item|entry)\b[^>]*>', xml, flags=re.IGNORECASE)
    for chunk in chunks[1:]:
        def _field(tag: str) -> str:
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
                "source":    source_name,
                "language":  lang,
            })
    return items


# ─── Core fetch ───────────────────────────────────────────────────────────────

def fetch_source(name: str, url: str, lang: str = "unknown", timeout: int = 15) -> list:
    """
    Fetch one source. Returns list of items with {title, summary, url, source, language}.
    """
    try:
        # Try feedparser first
        try:
            import feedparser
            feed = feedparser.parse(url)
            items = []
            for e in feed.entries:
                title   = getattr(e, "title",   "") or ""
                link    = getattr(e, "link",    "") or ""
                summary = (getattr(e, "summary", "") or
                           getattr(e, "description", "") or "")
                pub     = getattr(e, "published", "") or getattr(e, "updated", "") or ""
                items.append({
                    "title":     _strip_html(title)[:200],
                    "summary":   _strip_html(summary)[:500],
                    "url":       link,
                    "published": pub,
                    "source":    name,
                    "language":  lang,
                })
            return items
        except ImportError:
            pass

        req = urllib.request.Request(url, headers={"User-Agent": "Nova/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        xml = raw.decode("utf-8", errors="replace")
        return _parse_rss_xml(xml, name, lang)
    except Exception:
        return []


# ─── Translation ──────────────────────────────────────────────────────────────

def translate_summary(text: str, source_lang: str) -> str:
    """
    Use local LLM to translate/summarize non-English security text into English.
    Returns English summary (2-3 sentences).
    """
    if not text or not text.strip():
        return ""

    lang_name = LANGUAGE_NAMES.get(source_lang, source_lang)

    prompt = (
        f"You are N.O.V.A, fluent in all languages. "
        f"Translate and summarize this {lang_name} security text in 2-3 sentences: {text}"
    )

    result = _llm(prompt, temperature=0.2, max_tokens=200)
    return result if result else text[:200]


# ─── CVE extraction ───────────────────────────────────────────────────────────

def scan_for_cves(text: str) -> list:
    """
    Extract CVE-XXXX-XXXXX patterns from text.
    Returns list of unique CVE IDs.
    """
    found = re.findall(r'CVE-\d{4}-\d{4,7}', text, re.IGNORECASE)
    seen = set()
    unique = []
    for cve in found:
        upper = cve.upper()
        if upper not in seen:
            seen.add(upper)
            unique.append(upper)
    return unique


# ─── Interest scoring ─────────────────────────────────────────────────────────

_SECURITY_KEYWORDS = [
    "vulnerability", "exploit", "cve", "zero-day", "0day", "rce", "xss", "sqli",
    "overflow", "bypass", "injection", "backdoor", "malware", "ransomware",
    "patch", "advisory", "critical", "high severity", "privilege", "escalation",
    "authentication", "credential", "supply chain", "attack", "threat",
    # CJK security terms (approximate romanisation / common loan words)
    "漏洞", "攻击", "安全", "脆弱性", "脆弱", "패치", "취약점", "уязвимость",
]


def _is_interesting(item: dict) -> bool:
    """Quick heuristic — does this item look security-relevant?"""
    text = (
        (item.get("title") or "") + " " +
        (item.get("summary") or "")
    ).lower()
    # CVEs always interesting
    if scan_for_cves(text):
        return True
    for kw in _SECURITY_KEYWORDS:
        if kw in text:
            return True
    return False


# ─── State ────────────────────────────────────────────────────────────────────

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


def _rate_limited() -> bool:
    """Returns True if last multilang fetch was less than 6 hours ago."""
    state = _load_state()
    last = state.get("lastMultilangFetch")
    if not last:
        return False
    elapsed_h = (
        datetime.now(timezone.utc) - datetime.fromisoformat(last)
    ).total_seconds() / 3600
    return elapsed_h < FETCH_INTERVAL_HOURS


# ─── Main run ─────────────────────────────────────────────────────────────────

def run(verbose: bool = True, force: bool = False, only_source: str = "") -> list:
    """
    Fetch all non-English sources, translate interesting items, return findings.
    Rate-limited to once per 6 hours unless force=True.
    """
    if _rate_limited() and not force:
        if verbose:
            state = _load_state()
            last  = state.get("lastMultilangFetch", "unknown")
            print(f"  Rate-limited — last multilang fetch: {last}")
        return []

    findings = []

    source_groups = SOURCES
    if only_source and only_source in SOURCES:
        source_groups = {only_source: SOURCES[only_source]}

    for group_name, source_list in source_groups.items():
        for src in source_list:
            if verbose:
                print(f"  Fetching {src['name']} ({group_name})...")

            items = fetch_source(src["name"], src["url"], lang=src["lang"])

            if verbose:
                print(f"    → {len(items)} items")

            for item in items:
                if not _is_interesting(item):
                    continue

                text     = (item.get("title", "") + " " + item.get("summary", "")).strip()
                cves     = scan_for_cves(text)
                lang     = item.get("language", "unknown")

                # Only translate if non-trivially non-English
                translated = ""
                summary    = item.get("summary", "")
                if summary and lang != "en":
                    translated = translate_summary(summary[:400], lang)

                finding = {
                    "title":       item.get("title", ""),
                    "summary":     item.get("summary", ""),
                    "translated":  translated,
                    "url":         item.get("url", ""),
                    "source":      item.get("source", ""),
                    "language":    lang,
                    "cves":        cves,
                    "published":   item.get("published", ""),
                    "group":       group_name,
                }
                findings.append(finding)

                if verbose and translated:
                    print(f"    [{lang}] {item['title'][:60]}")
                    if cves:
                        print(f"      CVEs: {', '.join(cves)}")
                    print(f"      → {translated[:80]}")

    # Update state
    state = _load_state()
    state["lastMultilangFetch"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    return findings


# ─── Inject to research queue ─────────────────────────────────────────────────

def inject_to_research_queue(items: list) -> int:
    """
    Add multilang findings to memory/research_queue.json.
    Returns count of items added.
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
        title = (item.get("translated") or item.get("title") or "").strip()
        if not title:
            continue
        query = title[:120]
        if query.lower() in existing_queries:
            continue

        cves = item.get("cves", [])
        entry = {
            "query":     query,
            "source":    f"multilang:{item.get('source', item.get('group', 'feed'))}",
            "url":       item.get("url", ""),
            "language":  item.get("language", ""),
            "cves":      cves,
            "queued_at": now_str,
            "status":    "pending",
        }
        existing.append(entry)
        existing_queries.add(query.lower())
        added += 1

    RESEARCH_Q_F.parent.mkdir(parents=True, exist_ok=True)
    RESEARCH_Q_F.write_text(json.dumps(existing, indent=2))
    return added


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    G   = "\033[32m"
    C   = "\033[36m"
    Y   = "\033[33m"
    DIM = "\033[2m"
    NC  = "\033[0m"
    B   = "\033[1m"

    args        = sys.argv[1:]
    inject      = "--inject" in args
    force       = "--force" in args
    only_source = ""

    if "--source" in args:
        idx = args.index("--source")
        if idx + 1 < len(args):
            only_source = args[idx + 1].lower()

    print(f"\n{B}N.O.V.A Multilingual Research{NC}")

    if only_source and only_source not in SOURCES:
        print(f"  {Y}Unknown source '{only_source}'. Available: {', '.join(SOURCES)}{NC}")
        return

    findings = run(verbose=True, force=force, only_source=only_source)

    if not findings:
        print(f"  {Y}No findings (rate-limited or feeds unreachable). Use --force to override.{NC}\n")
        return

    print(f"\n  Found {len(findings)} interesting item(s):\n")
    for f in findings:
        lang = f.get("language", "")
        flag = {"zh": "🇨🇳", "ja": "🇯🇵", "ru": "🇷🇺", "ko": "🇰🇷"}.get(lang, "")
        cves = f.get("cves", [])
        cve_str = f"  {Y}CVEs: {', '.join(cves)}{NC}" if cves else ""
        print(f"  {flag} {C}{f['title'][:70]}{NC}  {DIM}[{f['source']}]{NC}")
        if f.get("translated"):
            print(f"     → {f['translated'][:100]}")
        if cve_str:
            print(f"     {cve_str}")
        print()

    if inject:
        n = inject_to_research_queue(findings)
        print(f"  {G}Injected {n} item(s) into research queue.{NC}")

    print()


if __name__ == "__main__":
    main()
