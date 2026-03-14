#!/usr/bin/env python3
"""
N.O.V.A Knowledge Graph — SQLite-backed relational memory.

Nodes: finding, pattern, target, signal, research, proposal, dream, program
Edges: found_on, similar_to, led_to, confirmed_by, generated_by, part_of, related_to
"""
import sqlite3, json
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path.home() / "Nova/memory/graph.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    data        TEXT    DEFAULT '{}',
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    UNIQUE(type, label)
);

CREATE TABLE IF NOT EXISTS edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    dst_id      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    relation    TEXT    NOT NULL,
    weight      REAL    DEFAULT 1.0,
    data        TEXT    DEFAULT '{}',
    created_at  TEXT    DEFAULT (datetime('now')),
    UNIQUE(src_id, dst_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_edges_src      ON edges(src_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst      ON edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
CREATE INDEX IF NOT EXISTS idx_nodes_type     ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_label    ON nodes(label);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


# ── Node operations ───────────────────────────────────────────────────────────

def add_node(type_: str, label: str, data: dict = None) -> int:
    """Insert or update a node. Returns node id."""
    data = data or {}
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO nodes (type, label, data, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(type, label) DO UPDATE SET
                   data       = excluded.data,
                   updated_at = excluded.updated_at
               RETURNING id""",
            (type_, label, json.dumps(data), now, now)
        )
        return cur.fetchone()[0]


def get_node(node_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return _row(row)


def find_nodes(type_: str = None, label: str = None, limit: int = 50) -> list[dict]:
    """Find nodes by type and/or label substring."""
    clauses, params = [], []
    if type_:
        clauses.append("type = ?"); params.append(type_)
    if label:
        clauses.append("label LIKE ?"); params.append(f"%{label}%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM nodes {where} ORDER BY updated_at DESC LIMIT ?", params
        ).fetchall()
        return [_row(r) for r in rows]


# ── Edge operations ───────────────────────────────────────────────────────────

def add_edge(src_id: int, dst_id: int, relation: str, weight: float = 1.0, data: dict = None) -> int:
    """Insert or update an edge. Returns edge id."""
    data = data or {}
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO edges (src_id, dst_id, relation, weight, data, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(src_id, dst_id, relation) DO UPDATE SET
                   weight = excluded.weight,
                   data   = excluded.data
               RETURNING id""",
            (src_id, dst_id, relation, weight, json.dumps(data), now)
        )
        return cur.fetchone()[0]


def neighbors(node_id: int, relation: str = None, direction: str = "out") -> list[dict]:
    """Return connected nodes. direction: 'out', 'in', or 'both'."""
    rel_clause = "AND e.relation = ?" if relation else ""
    rel_param  = [relation] if relation else []

    with _connect() as conn:
        results = []

        if direction in ("out", "both"):
            rows = conn.execute(
                f"""SELECT n.*, e.relation, e.weight FROM nodes n
                    JOIN edges e ON e.dst_id = n.id
                    WHERE e.src_id = ? {rel_clause}""",
                [node_id] + rel_param
            ).fetchall()
            results += [_row(r, include_edge=True) for r in rows]

        if direction in ("in", "both"):
            rows = conn.execute(
                f"""SELECT n.*, e.relation, e.weight FROM nodes n
                    JOIN edges e ON e.src_id = n.id
                    WHERE e.dst_id = ? {rel_clause}""",
                [node_id] + rel_param
            ).fetchall()
            results += [_row(r, include_edge=True, inbound=True) for r in rows]

        return results


def related(label: str, type_: str = None, depth: int = 2) -> list[dict]:
    """BFS from a node label, returns all reachable nodes within depth."""
    with _connect() as conn:
        clause = "AND type = ?" if type_ else ""
        params = [f"%{label}%"] + ([type_] if type_ else [])
        start_rows = conn.execute(
            f"SELECT id FROM nodes WHERE label LIKE ? {clause} LIMIT 1", params
        ).fetchall()

    if not start_rows:
        return []

    start_id = start_rows[0]["id"]
    visited, queue, result = {start_id}, [(start_id, 0)], []

    while queue:
        nid, d = queue.pop(0)
        if d >= depth:
            continue
        for nb in neighbors(nid, direction="both"):
            nid2 = nb["id"]
            if nid2 not in visited:
                visited.add(nid2)
                queue.append((nid2, d + 1))
                result.append(nb)

    return result


# ── Stats ─────────────────────────────────────────────────────────────────────

def stats() -> dict:
    with _connect() as conn:
        node_counts = {
            row["type"]: row["cnt"]
            for row in conn.execute(
                "SELECT type, COUNT(*) as cnt FROM nodes GROUP BY type"
            ).fetchall()
        }
        edge_counts = {
            row["relation"]: row["cnt"]
            for row in conn.execute(
                "SELECT relation, COUNT(*) as cnt FROM edges GROUP BY relation"
            ).fetchall()
        }
        total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    return {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "nodes_by_type": node_counts,
        "edges_by_relation": edge_counts,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(row, include_edge: bool = False, inbound: bool = False) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    if "data" in d and isinstance(d["data"], str):
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            pass
    if include_edge:
        d["_direction"] = "in" if inbound else "out"
    return d


# ── Convenience wrappers used by other modules ────────────────────────────────

def node_id_for(type_: str, label: str, data: dict = None) -> int:
    """Get-or-create a node, return its id."""
    return add_node(type_, label, data or {})


def link(src_type: str, src_label: str,
         dst_type: str, dst_label: str,
         relation: str, weight: float = 1.0, data: dict = None) -> None:
    """High-level: ensure both nodes exist then create an edge between them."""
    src = node_id_for(src_type, src_label)
    dst = node_id_for(dst_type, dst_label)
    add_edge(src, dst, relation, weight, data or {})
