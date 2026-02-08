#!/usr/bin/env python3
"""
Nova Phase 5.5.1 — Smart Endpoint Mutation

Generates context-aware endpoint variants based on signals and paths.
Designed to expand attack surface intelligently (no blind fuzzing).
"""

import json
import sys
from typing import Dict, List, Iterable

# Context-driven expansions
MUTATION_RULES = {
    "auth-path": ["login", "signin", "auth", "bypass", "debug"],
    "error-403": ["..", ".", "%2e", "backup", "old"],
    "numeric-id": ["0", "1", "9999", "me", "self"],
    "method-post": ["submit", "process", "action"],
    "error-500": ["test", "debug", "health", "status"],
}

COMMON_ADMIN_PATHS = ["admin", "dashboard", "manage", "internal"]


def iter_jsonl(stream: Iterable[str]):
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/"


def mutate_path(base_path: str, token: str) -> str:
    base = normalize_path(base_path)

    if base == "/":
        return f"/{token}"

    if token.startswith((".", "..", "%")):
        return f"{base}/{token}"

    return f"{base}/{token}"


def generate_mutations(record: Dict) -> List[Dict]:
    host = record.get("host")
    path = record.get("path", "/")
    signals = record.get("signals", [])

    mutations = []

    # 1. Signal-driven mutations
    for sig in signals:
        for token in MUTATION_RULES.get(sig, []):
            new_path = mutate_path(path, token)
            mutations.append({
                "host": host,
                "path": new_path,
                "method": record.get("method", "GET"),
                "source": f"mutation:{sig}"
            })

    # 2. Admin path expansion (heuristic)
    for admin in COMMON_ADMIN_PATHS:
        if admin in path.lower():
            for token in ["api", "v1", "internal", "debug"]:
                new_path = mutate_path(path, token)
                mutations.append({
                    "host": host,
                    "path": new_path,
                    "method": record.get("method", "GET"),
                    "source": "mutation:admin"
                })

    return mutations


def main() -> int:
    for record in iter_jsonl(sys.stdin):
        # Emit original record first
        print(json.dumps(record))

        # Emit mutations
        for mutated in generate_mutations(record):
            print(json.dumps(mutated))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
