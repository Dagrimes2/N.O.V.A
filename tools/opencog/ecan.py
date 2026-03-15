#!/usr/bin/env python3
"""
N.O.V.A ECAN — Economic Attention Allocation Network

Nova's implementation of OpenCog's ECAN: atoms compete for attention
(STI = Short-Term Importance, LTI = Long-Term Importance).

Nova uses attention to decide what to think about during dream cycles
and autonomous reasoning. High-STI atoms surface in dreams and morning
intentions. High-LTI atoms become part of long-term identity.

Usage:
    nova opencog ecan status
    nova opencog ecan boost BTC
    nova opencog ecan top [--n 10]
    nova opencog ecan decay
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE     = Path.home() / "Nova"
ECAN_DB  = BASE / "memory/opencog/ecan.db"
ECAN_DB.parent.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)


# ─── Constants ────────────────────────────────────────────────────────────────

MAX_STI       = 100.0
MIN_STI       = -20.0
STI_DECAY     = 0.05    # per cycle decay rate (5%)
LTI_DECAY     = 0.005   # LTI decays 10x slower than STI
WAGE_SHARE    = 5.0     # STI units paid to connected atoms
RENT          = 0.5     # STI rent per cycle


# ─── ECAN DB ─────────────────────────────────────────────────────────────────

class ECANStore:
    def __init__(self, db_path: Path = ECAN_DB):
        self.conn = sqlite3.connect(str(db_path))
        self._init()

    def _init(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS attention (
            name        TEXT PRIMARY KEY,
            sti         REAL DEFAULT 0.0,
            lti         REAL DEFAULT 0.0,
            vlti        INTEGER DEFAULT 0,
            access_count INTEGER DEFAULT 0,
            last_access TEXT,
            created_at  TEXT
        );
        """)
        self.conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get(self, name: str) -> dict:
        cur = self.conn.execute(
            "SELECT sti, lti, vlti, access_count, last_access FROM attention WHERE name=?",
            (name,)
        )
        row = cur.fetchone()
        if row:
            return {"name": name, "sti": row[0], "lti": row[1], "vlti": bool(row[2]),
                    "access_count": row[3], "last_access": row[4]}
        return {"name": name, "sti": 0.0, "lti": 0.0, "vlti": False, "access_count": 0}

    def set_sti(self, name: str, delta: float) -> float:
        cur = self.conn.execute("SELECT sti, lti, access_count FROM attention WHERE name=?",
                                (name,))
        row = cur.fetchone()
        now = self._now()
        if row:
            sti = max(MIN_STI, min(MAX_STI, row[0] + delta))
            lti = min(100.0, row[1] + delta * 0.01)  # LTI absorbs 1% of STI changes
            self.conn.execute(
                "UPDATE attention SET sti=?, lti=?, access_count=access_count+1, last_access=? WHERE name=?",
                (sti, lti, now, name)
            )
        else:
            sti = max(MIN_STI, min(MAX_STI, delta))
            self.conn.execute(
                "INSERT INTO attention(name, sti, lti, access_count, last_access, created_at) "
                "VALUES (?,?,?,1,?,?)",
                (name, sti, 0.0, now, now)
            )
        self.conn.commit()
        return sti

    def top_sti(self, n: int = 10) -> list[dict]:
        cur = self.conn.execute(
            "SELECT name, sti, lti, vlti, access_count FROM attention "
            "ORDER BY sti DESC LIMIT ?", (n,)
        )
        return [{"name": r[0], "sti": r[1], "lti": r[2], "vlti": bool(r[3]),
                 "access_count": r[4]} for r in cur.fetchall()]

    def top_lti(self, n: int = 10) -> list[dict]:
        cur = self.conn.execute(
            "SELECT name, sti, lti, vlti, access_count FROM attention "
            "ORDER BY lti DESC LIMIT ?", (n,)
        )
        return [{"name": r[0], "sti": r[1], "lti": r[2], "vlti": bool(r[3]),
                 "access_count": r[4]} for r in cur.fetchall()]

    def decay_all(self) -> int:
        """Apply STI/LTI decay and collect rent. Returns count updated."""
        now = self._now()
        # STI decay
        self.conn.execute(
            "UPDATE attention SET sti = MAX(?, sti * ? - ?) WHERE vlti = 0",
            (MIN_STI, 1.0 - STI_DECAY, RENT)
        )
        # LTI decay (much slower)
        self.conn.execute(
            "UPDATE attention SET lti = MAX(0, lti * ?)",
            (1.0 - LTI_DECAY,)
        )
        self.conn.commit()
        cur = self.conn.execute("SELECT COUNT(*) FROM attention")
        return cur.fetchone()[0]

    def stats(self) -> dict:
        cur = self.conn.execute(
            "SELECT COUNT(*), AVG(sti), MAX(sti), MIN(sti), SUM(lti) FROM attention"
        )
        row = cur.fetchone()
        return {
            "atoms": row[0] or 0,
            "avg_sti": round(row[1] or 0, 2),
            "max_sti": round(row[2] or 0, 2),
            "min_sti": round(row[3] or 0, 2),
            "total_lti": round(row[4] or 0, 2),
        }

    def close(self):
        self.conn.close()


# ─── ECAN Engine ─────────────────────────────────────────────────────────────

class ECANEngine:
    """
    Economic Attention Allocation — Nova's attention economy.

    Governs which concepts Nova actively "thinks about" during
    autonomous cycles, dream synthesis, and PLN reasoning.
    """

    def __init__(self):
        self.store = ECANStore()

    def stimulate(self, name: str, amount: float = 10.0) -> float:
        """Boost an atom's STI (it just got attention/importance)."""
        return self.store.set_sti(name, amount)

    def penalize(self, name: str, amount: float = 5.0) -> float:
        """Penalize an atom's STI (it led to a dead end)."""
        return self.store.set_sti(name, -amount)

    def decay(self) -> int:
        """Run one decay cycle."""
        return self.store.decay_all()

    def attentional_focus(self, n: int = 10) -> list[dict]:
        """Return atoms currently in the 'attentional focus' (top STI)."""
        return self.store.top_sti(n)

    def long_term_important(self, n: int = 10) -> list[dict]:
        """Return atoms with highest long-term importance."""
        return self.store.top_lti(n)

    def seed_from_history(self) -> int:
        """
        Seed attention values from Nova's autonomous history.
        Actions/targets she has taken recently get boosted STI.
        """
        history_file = BASE / "memory/autonomous_history.json"
        if not history_file.exists():
            return 0
        try:
            history = json.loads(history_file.read_text())
        except Exception:
            return 0

        # Recent items get more attention
        n = len(history)
        count = 0
        for i, h in enumerate(history[-50:]):
            recency_boost = 5.0 * ((i + 1) / 50)  # more recent = more boost
            for key in ("action", "target"):
                val = h.get(key, "")
                if val and len(val) > 2:
                    self.stimulate(val, recency_boost)
                    count += 1
        return count

    def seed_from_research(self) -> int:
        """Seed attention from recent research results."""
        research_dir = BASE / "memory/research"
        if not research_dir.exists():
            return 0
        count = 0
        files = sorted(research_dir.glob("*.json"), reverse=True)[:20]
        for f in files:
            try:
                data = json.loads(f.read_text())
                query = data.get("query", "")
                for word in query.split()[:5]:
                    if len(word) > 3:
                        self.stimulate(word, 3.0)
                        count += 1
            except Exception:
                pass
        return count

    def dream_themes(self, n: int = 5) -> list[str]:
        """Return top-n concepts for tonight's dream (high STI atoms)."""
        focus = self.attentional_focus(n)
        return [a["name"] for a in focus]

    def stats(self) -> dict:
        return self.store.stats()

    def close(self):
        self.store.close()


# Module-level singleton
_ecan: ECANEngine = None

def get_ecan() -> ECANEngine:
    global _ecan
    if _ecan is None:
        _ecan = ECANEngine()
    return _ecan


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "status"
    ecan = get_ecan()

    if cmd == "status":
        s = ecan.stats()
        focus = ecan.attentional_focus(5)
        print(f"\n{B}N.O.V.A ECAN — Attention Economy{NC}")
        print(f"  Atoms in economy : {C}{s['atoms']}{NC}")
        print(f"  Average STI      : {Y}{s['avg_sti']}{NC}")
        print(f"  Max STI          : {G}{s['max_sti']}{NC}")
        print(f"  Total LTI        : {C}{s['total_lti']}{NC}")
        if focus:
            print(f"\n  {B}Attentional Focus:{NC}")
            for a in focus:
                bar = "█" * min(20, max(0, int(a["sti"])))
                print(f"    {W}{a['name']:25s}{NC}  {G}{bar}{NC}  STI={a['sti']:.1f}  LTI={a['lti']:.2f}")

    elif cmd == "boost" and len(args) >= 2:
        amount = float(args[2]) if len(args) > 2 else 10.0
        new_sti = ecan.stimulate(" ".join(args[1:-1]) if len(args) > 2 else args[1], amount)
        print(f"{G}Boosted '{args[1]}' — STI now {new_sti:.1f}{NC}")

    elif cmd == "top":
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
        atoms = ecan.attentional_focus(n)
        print(f"\n{B}Top {n} Atoms by STI{NC}")
        for a in atoms:
            col = G if a["sti"] > 20 else (Y if a["sti"] > 5 else DIM)
            print(f"  {col}{a['name']:30s}{NC}  STI={a['sti']:6.1f}  LTI={a['lti']:5.2f}  "
                  f"{DIM}accessed {a['access_count']}x{NC}")

    elif cmd == "lti":
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
        atoms = ecan.long_term_important(n)
        print(f"\n{B}Top {n} Atoms by LTI (Long-Term Importance){NC}")
        for a in atoms:
            print(f"  {C}{a['name']:30s}{NC}  LTI={a['lti']:5.2f}  STI={a['sti']:6.1f}")

    elif cmd == "decay":
        n = ecan.decay()
        print(f"{DIM}Decay cycle complete. {n} atoms updated.{NC}")

    elif cmd == "seed":
        n1 = ecan.seed_from_history()
        n2 = ecan.seed_from_research()
        print(f"{G}Seeded attention from {n1} history entries, {n2} research keywords.{NC}")

    elif cmd == "dream":
        themes = ecan.dream_themes(7)
        print(f"\n{B}Tonight's Dream Themes (ECAN){NC}")
        for t in themes:
            print(f"  {C}• {t}{NC}")

    else:
        print("Usage: nova opencog ecan [status|boost NAME|top [N]|lti|decay|seed|dream]")

    ecan.close()


if __name__ == "__main__":
    main()
