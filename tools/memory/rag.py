#!/usr/bin/env python3
"""
N.O.V.A Semantic Memory (RAG)

Semantic search over all of Nova's memory files. Uses Ollama embeddings
(/api/embeddings) with graceful fallback to TF-IDF when Ollama is
unavailable. Index is stored as a flat JSONL file, capped at 2000 docs.

Storage:
  memory/rag/index.jsonl      — one JSON doc per line
  memory/rag/index_meta.json  — metadata / stats
"""
import json
import math
import os
import sys
import hashlib
import glob as _glob
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

BASE        = Path.home() / "Nova"
RAG_DIR     = BASE / "memory/rag"
INDEX_FILE  = RAG_DIR / "index.jsonl"
META_FILE   = RAG_DIR / "index_meta.json"
MAX_DOCS    = 2000
CHUNK_SIZE  = 300   # chars per chunk

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("general")
    TIMEOUT    = 10
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "gemma2:2b")
    TIMEOUT    = 10

# Derive the embeddings URL from the generate URL
EMBED_URL = OLLAMA_URL.replace("/api/generate", "/api/embeddings")

_DEFAULT_SOURCES = [
    "memory/journal/*.md",
    "memory/research/*.md",
    "memory/episodes/episodes.jsonl",
    "memory/dreams/*.md",
    "memory/studio/*.md",
    "memory/conversations/discord.jsonl",
]

_STOPWORDS = {
    "the","and","for","are","but","not","you","all","can","her","was","one",
    "our","out","had","has","have","him","his","how","its","let","may","nor",
    "now","off","old","own","put","say","she","too","use","way","who","why",
    "with","that","this","they","from","than","then","when","what","will",
    "been","come","into","like","look","more","such","take","than","them",
    "well","were","your",
}


# ── Embedding helpers ──────────────────────────────────────────────────────────

def _embed_ollama(text: str) -> list | None:
    """Call Ollama /api/embeddings. Returns float list or None on failure."""
    payload = json.dumps({"model": MODEL, "prompt": text[:500]}).encode()
    req = Request(
        EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            vec = data.get("embedding")
            if vec and isinstance(vec, list):
                return [float(v) for v in vec]
    except Exception:
        pass
    return None


def _tokenize(text: str) -> list:
    """Split text into lowercase alpha tokens."""
    import re
    return [w for w in re.findall(r"[a-z]+", text.lower())
            if len(w) > 2 and w not in _STOPWORDS]


def _embed_tfidf(text: str, corpus: list) -> list:
    """
    Fallback TF-IDF vector for text given a corpus of strings.
    Vocabulary capped at 500 terms. Pure stdlib.
    """
    # Build vocab from corpus (up to 500 terms by document frequency)
    df: Counter = Counter()
    tokenized_corpus = []
    for doc in corpus:
        tokens = set(_tokenize(doc))
        tokenized_corpus.append(tokens)
        df.update(tokens)

    vocab = [term for term, _ in df.most_common(500)]
    vocab_index = {term: i for i, term in enumerate(vocab)}
    if not vocab:
        return []

    n_docs = max(len(corpus), 1)
    text_tokens = _tokenize(text)
    tf = Counter(text_tokens)
    total_terms = max(len(text_tokens), 1)

    vec = [0.0] * len(vocab)
    for term, count in tf.items():
        if term in vocab_index:
            idx = vocab_index[term]
            tf_val = count / total_terms
            idf_val = math.log((n_docs + 1) / (df.get(term, 0) + 1)) + 1.0
            vec[idx] = tf_val * idf_val

    # L2 normalise
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list, b: list) -> float:
    """Cosine similarity between two vectors. Returns 0.0 if either is empty."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot  = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1e-9
    norm_b = math.sqrt(sum(y * y for y in b)) or 1e-9
    return dot / (norm_a * norm_b)


# ── Chunking ───────────────────────────────────────────────────────────────────

def _chunk(text: str, size: int = CHUNK_SIZE) -> list:
    """Split text into overlapping chunks of ~size chars."""
    chunks = []
    text = text.strip()
    if not text:
        return chunks
    step = max(size - 50, 100)   # 50-char overlap
    for i in range(0, len(text), step):
        chunk = text[i:i + size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _read_file(path: Path) -> str:
    """Read a file, handling .jsonl by extracting text fields."""
    try:
        raw = path.read_text(errors="replace")
    except Exception:
        return ""

    if path.suffix == ".jsonl":
        lines = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Prefer content/text/message/body fields
                for key in ("content", "text", "message", "body", "user", "nova"):
                    val = obj.get(key)
                    if val and isinstance(val, str):
                        lines.append(val)
            except Exception:
                lines.append(line)
        return " ".join(lines)
    return raw


def _doc_id(source: str, chunk_idx: int, content: str) -> str:
    h = hashlib.md5(f"{source}:{chunk_idx}:{content[:80]}".encode()).hexdigest()[:12]
    return h


# ── Index I/O ──────────────────────────────────────────────────────────────────

def _load_index() -> list:
    """Load all docs from index.jsonl."""
    if not INDEX_FILE.exists():
        return []
    docs = []
    for line in INDEX_FILE.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            docs.append(json.loads(line))
        except Exception:
            pass
    return docs


def _save_index(docs: list) -> None:
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    # Cap at MAX_DOCS — evict oldest by 'ts'
    if len(docs) > MAX_DOCS:
        docs.sort(key=lambda d: d.get("ts", ""), reverse=True)
        docs = docs[:MAX_DOCS]
    lines = [json.dumps(d, separators=(",", ":")) for d in docs]
    INDEX_FILE.write_text("\n".join(lines) + "\n")


def _save_meta(indexed_files: list, total_docs: int) -> None:
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "indexed_files": indexed_files,
        "last_built": datetime.now(timezone.utc).isoformat(),
        "total_docs": total_docs,
    }
    META_FILE.write_text(json.dumps(meta, indent=2))


def _load_meta() -> dict:
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text())
        except Exception:
            pass
    return {"indexed_files": [], "last_built": None, "total_docs": 0}


# ── Public API ─────────────────────────────────────────────────────────────────

def build_index(sources: list = None, verbose: bool = True) -> int:
    """
    Index all memory files. sources = list of glob patterns or None for defaults.
    Chunks files into ~300-char segments. Embeds via Ollama (or TF-IDF fallback).
    Saves to index.jsonl. Returns count of docs indexed.
    """
    patterns = sources if sources is not None else _DEFAULT_SOURCES
    ts_now   = datetime.now(timezone.utc).isoformat()

    # Resolve all matching paths
    all_paths = []
    for pat in patterns:
        full_pat = str(BASE / pat)
        matches  = _glob.glob(full_pat, recursive=True)
        all_paths.extend(sorted(matches))

    # Deduplicate
    all_paths = list(dict.fromkeys(all_paths))

    if verbose:
        print(f"[rag] indexing {len(all_paths)} files …")

    # Collect all text chunks first (needed for TF-IDF corpus)
    chunks_by_source: list = []   # (path_str, chunk_text)
    for fpath in all_paths:
        p = Path(fpath)
        if not p.exists():
            continue
        text = _read_file(p)
        for chunk in _chunk(text):
            chunks_by_source.append((str(p.relative_to(BASE)), chunk))

    if not chunks_by_source:
        if verbose:
            print("[rag] no content found — index empty")
        _save_index([])
        _save_meta(all_paths, 0)
        return 0

    # Try Ollama on a test embed to decide strategy
    use_ollama = _embed_ollama("test") is not None
    corpus_texts = [c for _, c in chunks_by_source]

    if verbose:
        strategy = "ollama" if use_ollama else "tfidf"
        print(f"[rag] embedding strategy: {strategy} | chunks: {len(chunks_by_source)}")

    docs = []
    for idx, (src, chunk_text) in enumerate(chunks_by_source):
        if use_ollama:
            vec = _embed_ollama(chunk_text)
            if vec is None:
                vec = _embed_tfidf(chunk_text, corpus_texts)
        else:
            vec = _embed_tfidf(chunk_text, corpus_texts)

        doc = {
            "id":      _doc_id(src, idx, chunk_text),
            "source":  src,
            "content": chunk_text,
            "vector":  vec,
            "ts":      ts_now,
        }
        docs.append(doc)

        if verbose and (idx + 1) % 50 == 0:
            print(f"[rag]   {idx + 1}/{len(chunks_by_source)} …")

    _save_index(docs)
    _save_meta(all_paths, len(docs))

    if verbose:
        print(f"[rag] indexed {len(docs)} docs from {len(all_paths)} files")

    return len(docs)


def search(query: str, top_k: int = 5, sources: list = None) -> list:
    """
    Semantic search over the index.
    Returns top_k results sorted by descending similarity, each:
      {"content": str, "source": str, "score": float, "ts": str}
    Falls back to TF-IDF when Ollama is unavailable.
    """
    docs = _load_index()
    if not docs:
        return []

    # Filter by sources if requested
    if sources:
        docs = [d for d in docs if any(s in d.get("source", "") for s in sources)]

    corpus_texts = [d.get("content", "") for d in docs]

    # Embed the query
    query_vec = _embed_ollama(query)
    if query_vec is None:
        query_vec = _embed_tfidf(query, corpus_texts)

    # Score each doc
    scored = []
    for doc in docs:
        vec = doc.get("vector") or []
        # If dimension mismatch (ollama vs tfidf index), fall back to tfidf
        if query_vec and vec and len(query_vec) != len(vec):
            # re-embed this doc on-the-fly with tfidf
            vec = _embed_tfidf(doc.get("content", ""), corpus_texts)
            qv2 = _embed_tfidf(query, corpus_texts)
            score = _cosine(qv2, vec)
        else:
            score = _cosine(query_vec, vec)
        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, doc in scored[:top_k]:
        results.append({
            "content": doc.get("content", ""),
            "source":  doc.get("source", ""),
            "score":   round(score, 4),
            "ts":      doc.get("ts", ""),
        })
    return results


def to_prompt_context(query: str, top_k: int = 3) -> str:
    """
    Search memory for query, return compact context string for LLM injection.
    Format: "Memory: [journal] She wondered about X; [research] SSRF via import..."
    Max 250 chars total.
    """
    results = search(query, top_k=top_k)
    if not results:
        return ""

    parts = []
    for r in results:
        src   = r["source"]
        # Infer a short label from the path
        label = src.split("/")[1] if "/" in src else src
        label = label.replace("_", " ").rstrip(".md").rstrip(".jsonl")
        snippet = r["content"][:60].replace("\n", " ").strip()
        parts.append(f"[{label}] {snippet}")

    raw = "Memory: " + "; ".join(parts)
    return raw[:250]


def status() -> None:
    """Print index stats: total docs, sources, last built."""
    meta = _load_meta()
    docs = _load_index()

    G = "\033[32m"; C = "\033[36m"; B = "\033[1m"; NC = "\033[0m"; DIM = "\033[2m"

    print(f"\n{B}N.O.V.A RAG Index{NC}")
    print(f"  Total docs  : {G}{meta.get('total_docs', len(docs))}{NC}")
    last_built = meta.get('last_built') or 'never'
    print(f"  Last built  : {DIM}{last_built[:19]}{NC}")
    files = meta.get("indexed_files", [])
    print(f"  Files indexed: {len(files)}")
    if docs:
        sources: Counter = Counter()
        for d in docs:
            src = d.get("source", "?")
            top = src.split("/")[1] if "/" in src else src
            sources[top] += 1
        print(f"\n  {B}Sources:{NC}")
        for src, cnt in sources.most_common(10):
            print(f"    {C}{src:<30}{NC} {cnt} chunks")
    print()


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "status"

    if cmd == "status":
        status()
    elif cmd == "build":
        count = build_index(verbose=True)
        print(f"[rag] done — {count} docs in index")
    elif cmd == "search" and len(args) >= 2:
        query   = " ".join(args[1:])
        results = search(query, top_k=5)
        if not results:
            print("No results. Run: nova rag build")
        else:
            print(f"\nTop results for: \"{query}\"\n")
            for i, r in enumerate(results, 1):
                print(f"  {i}. [{r['source']}]  score={r['score']:.3f}")
                print(f"     {r['content'][:120]}")
                print()
    elif cmd == "context" and len(args) >= 2:
        query = " ".join(args[1:])
        print(to_prompt_context(query))
    else:
        print("Usage: nova rag [status|build|search <query>|context <query>]")


if __name__ == "__main__":
    main()
