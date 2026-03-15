#!/usr/bin/env python3
"""
N.O.V.A LLM Response Cache

Avoids redundant Ollama calls by caching prompt→response pairs.
Cache key: SHA256(model + prompt). TTL per use-case.

Gives Nova 3-5x throughput on repeated or similar reasoning tasks.
Identical hypothesize/reflect calls (same signals, same host) skip Ollama entirely.

Storage: memory/llm_cache/  (one JSON file per entry)

Usage:
    from tools.llm.llm_cache import llm_call
    response = llm_call(model, prompt, temperature=0.1, ttl=3600)
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE       = Path.home() / "Nova"
CACHE_DIR  = BASE / "memory/llm_cache"
STATS_FILE = BASE / "memory/llm_cache/stats.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# Default TTLs (seconds) by use-case
TTL_REASONING  = 1800   # 30 min — reflect/hypothesize (same finding = same answer)
TTL_RESEARCH   = 3600   # 1 hour — synthesis
TTL_CREATIVE   = 0      # never cache — creative output should be unique
TTL_AUTONOMOUS = 300    # 5 min — decision prompts change with time

_hits   = 0
_misses = 0
_calls  = 0


def _cache_key(model: str, prompt: str) -> str:
    raw = f"{model}::{prompt}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _load_stats() -> dict:
    if STATS_FILE.exists():
        try:
            return json.loads(STATS_FILE.read_text())
        except Exception:
            pass
    return {"hits": 0, "misses": 0, "calls": 0, "tokens_saved": 0}


def _save_stats(stats: dict):
    try:
        STATS_FILE.write_text(json.dumps(stats, indent=2))
    except Exception:
        pass


def get_cached(model: str, prompt: str, ttl: int) -> Optional[str]:
    """Return cached response or None if miss/expired."""
    if ttl <= 0:
        return None
    key   = _cache_key(model, prompt)
    path  = _cache_path(key)
    if not path.exists():
        return None
    try:
        data     = json.loads(path.read_text())
        cached_at= datetime.fromisoformat(data["cached_at"])
        age      = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if age > ttl:
            path.unlink(missing_ok=True)
            return None
        return data["response"]
    except Exception:
        return None


def set_cached(model: str, prompt: str, response: str):
    """Write a response to cache."""
    key  = _cache_key(model, prompt)
    path = _cache_path(key)
    try:
        path.write_text(json.dumps({
            "model":     model,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "response":  response,
            "prompt_len": len(prompt),
        }))
    except Exception:
        pass


def llm_call(model: str, prompt: str, temperature: float = 0.1,
             num_predict: int = 300, ttl: int = TTL_REASONING,
             stream: bool = False) -> str:
    """
    Drop-in replacement for direct Ollama calls.
    Checks cache first, calls Ollama on miss, caches result.

    Returns the response string.
    """
    global _hits, _misses, _calls
    _calls += 1

    # Cache check
    cached = get_cached(model, prompt, ttl)
    if cached is not None:
        _hits += 1
        _persist_stats(hit=True, prompt_len=len(prompt))
        return cached

    _misses += 1

    # Ollama call
    try:
        import requests
        ollama_url = "http://localhost:11434/api/generate"
        try:
            from tools.config import cfg
            ollama_url = cfg.ollama_url
        except Exception:
            pass

        resp = requests.post(ollama_url, json={
            "model":   model,
            "prompt":  prompt,
            "stream":  stream,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }, timeout=300)
        response = resp.json().get("response", "")

        if response and ttl > 0:
            set_cached(model, prompt, response)

        _persist_stats(hit=False, prompt_len=len(prompt))
        return response

    except Exception as e:
        return ""


def _persist_stats(hit: bool, prompt_len: int):
    stats = _load_stats()
    stats["calls"]  += 1
    if hit:
        stats["hits"]        += 1
        stats["tokens_saved"] = stats.get("tokens_saved", 0) + prompt_len // 4
    else:
        stats["misses"] += 1
    _save_stats(stats)


def cache_stats() -> dict:
    stats  = _load_stats()
    files  = [f for f in CACHE_DIR.glob("*.json") if f.name != "stats.json"]
    size_kb= round(sum(f.stat().st_size for f in files) / 1024, 1)
    hit_rate = 0.0
    if stats["calls"] > 0:
        hit_rate = round(stats["hits"] / stats["calls"], 3)
    return {
        "entries":      len(files),
        "size_kb":      size_kb,
        "hits":         stats.get("hits", 0),
        "misses":       stats.get("misses", 0),
        "calls":        stats.get("calls", 0),
        "hit_rate":     hit_rate,
        "tokens_saved": stats.get("tokens_saved", 0),
    }


def clear_cache(expired_only: bool = True) -> int:
    """Clear expired (or all) cache entries. Returns count deleted."""
    files   = [f for f in CACHE_DIR.glob("*.json") if f.name != "stats.json"]
    deleted = 0
    for f in files:
        if not expired_only:
            f.unlink(missing_ok=True)
            deleted += 1
        else:
            try:
                data      = json.loads(f.read_text())
                cached_at = datetime.fromisoformat(data["cached_at"])
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age > TTL_RESEARCH:   # use longest TTL as cutoff
                    f.unlink(missing_ok=True)
                    deleted += 1
            except Exception:
                pass
    return deleted


def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A LLM Cache")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("stats",  help="Cache statistics")
    sub.add_parser("clear",  help="Clear expired cache entries")
    sub.add_parser("purge",  help="Clear ALL cache entries")

    args = p.parse_args()
    G="\033[32m"; Y="\033[33m"; C="\033[36m"
    W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"

    if args.cmd == "stats" or not args.cmd:
        s = cache_stats()
        print(f"\n{B}N.O.V.A LLM Cache{NC}")
        print(f"  Entries:      {W}{s['entries']}{NC}  ({s['size_kb']} KB)")
        hr_col = G if s["hit_rate"] > 0.5 else Y
        print(f"  Hit rate:     {hr_col}{s['hit_rate']:.1%}{NC}  "
              f"({s['hits']} hits / {s['calls']} calls)")
        print(f"  Tokens saved: {G}~{s['tokens_saved']:,}{NC}")
    elif args.cmd == "clear":
        n = clear_cache(expired_only=True)
        print(f"{G}Cleared {n} expired entries.{NC}")
    elif args.cmd == "purge":
        n = clear_cache(expired_only=False)
        print(f"{G}Purged {n} entries.{NC}")


if __name__ == "__main__":
    main()
