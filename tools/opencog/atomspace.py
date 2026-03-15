#!/usr/bin/env python3
"""
N.O.V.A AtomSpace — Hypergraph Knowledge Representation

Implements an AtomSpace-compatible interface backed by Nova's SQLite
knowledge graph. Can optionally connect to a real OpenCog AtomSpace
via Docker (opencog/atomspace) if available.

Atom types follow OpenCog conventions:
  ConceptNode, PredicateNode, NumberNode,
  EvaluationLink, InheritanceLink, SimilarityLink,
  ImplicationLink, EquivalenceLink

TruthValues: SimpleTruthValue(strength, confidence)

Usage:
    nova opencog atomspace stats
    nova opencog atomspace query ConceptNode
    nova opencog atomspace assert "BTC" "is" "volatile"
    nova opencog atomspace infer "BTC"
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

BASE = Path.home() / "Nova"
GRAPH_DB = BASE / "memory/graph.db"
ATOM_DB  = BASE / "memory/opencog/atomspace.db"
ATOM_DB.parent.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)


# ─── TruthValue ──────────────────────────────────────────────────────────────

@dataclass
class SimpleTruthValue:
    """OpenCog-style SimpleTruthValue: (strength, confidence)."""
    strength:   float = 0.5   # 0.0 = false, 1.0 = true
    confidence: float = 0.5   # 0.0 = no evidence, 1.0 = certain

    def __repr__(self):
        return f"stv({self.strength:.3f}, {self.confidence:.3f})"

    def merge(self, other: "SimpleTruthValue") -> "SimpleTruthValue":
        """Merge two truth values via confidence-weighted average."""
        total = self.confidence + other.confidence
        if total == 0:
            return SimpleTruthValue(0.5, 0.0)
        s = (self.strength * self.confidence + other.strength * other.confidence) / total
        c = min(1.0, total / 2.0)
        return SimpleTruthValue(s, c)

    def to_dict(self) -> dict:
        return {"strength": self.strength, "confidence": self.confidence}

    @staticmethod
    def from_dict(d: dict) -> "SimpleTruthValue":
        return SimpleTruthValue(d.get("strength", 0.5), d.get("confidence", 0.5))

    @staticmethod
    def from_db(tv_json: str) -> "SimpleTruthValue":
        try:
            return SimpleTruthValue.from_dict(json.loads(tv_json or "{}"))
        except Exception:
            return SimpleTruthValue(0.5, 0.5)

DEFAULT_TV = SimpleTruthValue(0.5, 0.5)


# ─── Atom ─────────────────────────────────────────────────────────────────────

@dataclass
class Atom:
    """An atom in the AtomSpace (node or link)."""
    atom_type:  str
    name:       str                     # empty string for links
    tv:         SimpleTruthValue = field(default_factory=SimpleTruthValue)
    outgoing:   list = field(default_factory=list)  # list of Atom for links
    atom_id:    Optional[int] = None
    created_at: str = ""

    @property
    def is_link(self) -> bool:
        return bool(self.outgoing)

    @property
    def is_node(self) -> bool:
        return not self.outgoing

    def __repr__(self):
        if self.is_link:
            return f"({self.atom_type} {self.outgoing} {self.tv})"
        return f"({self.atom_type} \"{self.name}\" {self.tv})"


# ─── AtomSpace ───────────────────────────────────────────────────────────────

class AtomSpace:
    """
    Nova's AtomSpace — SQLite-backed hypergraph.

    Mirrors the OpenCog AtomSpace API surface so code can run with
    or without the real OpenCog C++ backend.
    """

    def __init__(self, db_path: Path = ATOM_DB):
        self.db_path = db_path
        self._conn   = sqlite3.connect(str(db_path))
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS atoms (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            atom_type   TEXT NOT NULL,
            name        TEXT DEFAULT '',
            tv_strength REAL DEFAULT 0.5,
            tv_conf     REAL DEFAULT 0.5,
            created_at  TEXT,
            updated_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS links (
            link_id     INTEGER NOT NULL,
            position    INTEGER NOT NULL,
            target_id   INTEGER NOT NULL,
            FOREIGN KEY(link_id) REFERENCES atoms(id),
            FOREIGN KEY(target_id) REFERENCES atoms(id)
        );
        CREATE INDEX IF NOT EXISTS idx_atom_type ON atoms(atom_type);
        CREATE INDEX IF NOT EXISTS idx_atom_name ON atoms(name);
        CREATE INDEX IF NOT EXISTS idx_link_id   ON links(link_id);
        """)
        self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_node(self, atom_type: str, name: str,
                 tv: SimpleTruthValue = None) -> Atom:
        """Add or update a node. Returns the atom."""
        tv = tv or DEFAULT_TV
        cur = self._conn.execute(
            "SELECT id, tv_strength, tv_conf FROM atoms WHERE atom_type=? AND name=?",
            (atom_type, name)
        )
        row = cur.fetchone()
        now = self._now()
        if row:
            # Merge truth values
            existing_tv = SimpleTruthValue(row[1], row[2])
            merged = existing_tv.merge(tv)
            self._conn.execute(
                "UPDATE atoms SET tv_strength=?, tv_conf=?, updated_at=? WHERE id=?",
                (merged.strength, merged.confidence, now, row[0])
            )
            self._conn.commit()
            return Atom(atom_type, name, merged, atom_id=row[0])
        else:
            cur = self._conn.execute(
                "INSERT INTO atoms(atom_type, name, tv_strength, tv_conf, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (atom_type, name, tv.strength, tv.confidence, now, now)
            )
            self._conn.commit()
            return Atom(atom_type, name, tv, atom_id=cur.lastrowid)

    def add_link(self, link_type: str, outgoing: list[Atom],
                 tv: SimpleTruthValue = None) -> Atom:
        """Add a link between atoms."""
        tv  = tv or DEFAULT_TV
        now = self._now()
        # Store link atom
        cur = self._conn.execute(
            "INSERT INTO atoms(atom_type, name, tv_strength, tv_conf, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (link_type, "", tv.strength, tv.confidence, now, now)
        )
        link_id = cur.lastrowid
        # Store outgoing set
        for i, atom in enumerate(outgoing):
            if atom.atom_id is None:
                raise ValueError(f"Atom has no id: {atom}")
            self._conn.execute(
                "INSERT INTO links(link_id, position, target_id) VALUES (?,?,?)",
                (link_id, i, atom.atom_id)
            )
        self._conn.commit()
        return Atom(link_type, "", tv, outgoing=outgoing, atom_id=link_id)

    def get_node(self, atom_type: str, name: str) -> Optional[Atom]:
        cur = self._conn.execute(
            "SELECT id, tv_strength, tv_conf FROM atoms WHERE atom_type=? AND name=?",
            (atom_type, name)
        )
        row = cur.fetchone()
        if not row:
            return None
        return Atom(atom_type, name, SimpleTruthValue(row[1], row[2]), atom_id=row[0])

    def get_atoms_by_type(self, atom_type: str) -> list[Atom]:
        cur = self._conn.execute(
            "SELECT id, name, tv_strength, tv_conf FROM atoms WHERE atom_type=? ORDER BY tv_conf DESC",
            (atom_type,)
        )
        return [
            Atom(atom_type, row[1], SimpleTruthValue(row[2], row[3]), atom_id=row[0])
            for row in cur.fetchall()
        ]

    def get_incoming(self, atom: Atom) -> list[Atom]:
        """Return all links that have this atom in their outgoing set."""
        cur = self._conn.execute(
            "SELECT DISTINCT link_id FROM links WHERE target_id=?",
            (atom.atom_id,)
        )
        links = []
        for (lid,) in cur.fetchall():
            link_atom = self._load_link(lid)
            if link_atom:
                links.append(link_atom)
        return links

    def _load_link(self, link_id: int) -> Optional[Atom]:
        cur = self._conn.execute(
            "SELECT atom_type, tv_strength, tv_conf FROM atoms WHERE id=?",
            (link_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        # Load outgoing set
        out_cur = self._conn.execute(
            "SELECT target_id FROM links WHERE link_id=? ORDER BY position",
            (link_id,)
        )
        outgoing = []
        for (tid,) in out_cur.fetchall():
            t_cur = self._conn.execute(
                "SELECT atom_type, name, tv_strength, tv_conf FROM atoms WHERE id=?",
                (tid,)
            )
            t = t_cur.fetchone()
            if t:
                outgoing.append(Atom(t[0], t[1], SimpleTruthValue(t[2], t[3]), atom_id=tid))
        return Atom(row[0], "", SimpleTruthValue(row[1], row[2]),
                    outgoing=outgoing, atom_id=link_id)

    def stats(self) -> dict:
        cur = self._conn.execute("SELECT atom_type, COUNT(*) FROM atoms GROUP BY atom_type")
        type_counts = dict(cur.fetchall())
        total       = sum(type_counts.values())
        link_count  = self._conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        return {
            "total_atoms":  total,
            "link_edges":   link_count,
            "by_type":      type_counts,
        }

    def query(self, atom_type: str = None, name_pattern: str = None,
              min_strength: float = 0.0, min_confidence: float = 0.0) -> list[Atom]:
        sql    = "SELECT id, atom_type, name, tv_strength, tv_conf FROM atoms WHERE 1=1"
        params = []
        if atom_type:
            sql    += " AND atom_type=?"
            params.append(atom_type)
        if name_pattern:
            sql    += " AND name LIKE ?"
            params.append(f"%{name_pattern}%")
        sql += " AND tv_strength>=? AND tv_conf>=?"
        params += [min_strength, min_confidence]
        sql += " ORDER BY tv_strength * tv_conf DESC LIMIT 50"
        cur = self._conn.execute(sql, params)
        return [
            Atom(row[1], row[2], SimpleTruthValue(row[3], row[4]), atom_id=row[0])
            for row in cur.fetchall()
        ]

    def ingest_from_knowledge_graph(self) -> int:
        """Import Nova's SQLite knowledge graph nodes into AtomSpace."""
        if not GRAPH_DB.exists():
            return 0
        g_conn = sqlite3.connect(str(GRAPH_DB))
        count  = 0
        try:
            cur = g_conn.execute("SELECT type, label, properties FROM nodes LIMIT 500")
            for row in cur.fetchall():
                node_type = row[0].replace("_", "").capitalize() + "Node"
                name      = row[1] or ""
                try:
                    props = json.loads(row[2] or "{}")
                    conf  = float(props.get("confidence", 0.6))
                except Exception:
                    conf = 0.6
                self.add_node(node_type, name, SimpleTruthValue(0.8, conf))
                count += 1
        except Exception:
            pass
        finally:
            g_conn.close()
        return count

    def assert_knowledge(self, subject: str, predicate: str, obj: str,
                         strength: float = 0.9, confidence: float = 0.8) -> Atom:
        """
        Assert: (EvaluationLink (PredicateNode predicate)
                               (ListLink (ConceptNode subject)
                                         (ConceptNode obj)))
        """
        s_atom = self.add_node("ConceptNode", subject,
                               SimpleTruthValue(strength, confidence))
        p_atom = self.add_node("PredicateNode", predicate,
                               SimpleTruthValue(1.0, 1.0))
        o_atom = self.add_node("ConceptNode", obj,
                               SimpleTruthValue(strength, confidence))
        # We can't nest ListLink without IDs — store flattened EvaluationLink
        tv = SimpleTruthValue(strength, confidence)
        return self.add_link("EvaluationLink", [p_atom, s_atom, o_atom], tv)

    def close(self):
        self._conn.close()


# ─── Module-level singleton ───────────────────────────────────────────────────

_atomspace: Optional[AtomSpace] = None

def get_atomspace() -> AtomSpace:
    global _atomspace
    if _atomspace is None:
        _atomspace = AtomSpace()
    return _atomspace


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "stats"
    as_  = get_atomspace()

    if cmd == "stats":
        s = as_.stats()
        print(f"\n{B}N.O.V.A AtomSpace{NC}")
        print(f"  Total atoms : {C}{s['total_atoms']}{NC}")
        print(f"  Link edges  : {C}{s['link_edges']}{NC}")
        print(f"\n  {B}By type:{NC}")
        for t, n in sorted(s["by_type"].items(), key=lambda x: -x[1]):
            print(f"    {t:30s} {Y}{n}{NC}")

    elif cmd == "query" and len(args) >= 2:
        atoms = as_.query(atom_type=args[1],
                          name_pattern=args[2] if len(args) > 2 else None)
        if not atoms:
            print(f"{DIM}No atoms found.{NC}")
        else:
            print(f"\n{B}Atoms ({len(atoms)}){NC}")
            for a in atoms:
                print(f"  {C}{a.atom_type:20s}{NC}  {W}{a.name:30s}{NC}  {DIM}{a.tv}{NC}")

    elif cmd == "assert" and len(args) >= 4:
        result = as_.assert_knowledge(args[1], args[2], args[3])
        print(f"{G}Asserted: ({args[2]} {args[1]} {args[3]})  link_id={result.atom_id}{NC}")

    elif cmd == "ingest":
        n = as_.ingest_from_knowledge_graph()
        print(f"{G}Ingested {n} nodes from knowledge graph.{NC}")

    elif cmd == "infer" and len(args) >= 2:
        from tools.opencog.pln import PLNEngine
        pln = PLNEngine(as_)
        results = pln.infer(args[1])
        print(f"\n{B}PLN Inference — '{args[1]}'{NC}")
        for r in results:
            print(f"  {C}{r['conclusion']:40s}{NC}  {DIM}{r['tv']}{NC}")

    else:
        print("Usage: nova opencog atomspace [stats|query TYPE|assert S P O|ingest|infer CONCEPT]")

    as_.close()


if __name__ == "__main__":
    main()
