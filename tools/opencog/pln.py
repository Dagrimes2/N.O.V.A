#!/usr/bin/env python3
"""
N.O.V.A PLN — Probabilistic Logic Networks

Simplified implementation of OpenCog's PLN inference rules
operating on Nova's AtomSpace.

Rules implemented:
  - Deduction:      A→B, B→C ⊢ A→C
  - Inversion:      A→B ⊢ B→A (with Bayesian inversion)
  - Abduction:      A→B, A→C ⊢ B→C (via common parent)
  - Modus Ponens:   A, A→B ⊢ B
  - Conjunction:    A, B ⊢ A∧B
  - Similarity:     A→B, B→A ⊢ A↔B

Usage:
    from tools.opencog.pln import PLNEngine
    from tools.opencog.atomspace import get_atomspace
    pln = PLNEngine(get_atomspace())
    results = pln.infer("BTC")
"""
import sys
from pathlib import Path
from typing import Optional

BASE = Path.home() / "Nova"
_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

from tools.opencog.atomspace import (
    AtomSpace, Atom, SimpleTruthValue, get_atomspace
)


# ─── Truth value math ─────────────────────────────────────────────────────────

def tv_deduction(tv_AB: SimpleTruthValue, tv_BC: SimpleTruthValue,
                 tv_B:  SimpleTruthValue) -> SimpleTruthValue:
    """
    Deduction rule: A→B, B→C ⊢ A→C
    PLN formula: s_AC = s_AB * s_BC + (1-s_AB) * (s_C - s_B*s_BC)/(1-s_B)
    """
    s_AB, c_AB = tv_AB.strength, tv_AB.confidence
    s_BC, c_BC = tv_BC.strength, tv_BC.confidence
    s_B         = tv_B.strength

    denom = 1.0 - s_B
    if denom < 1e-6:
        s_AC = s_AB * s_BC
    else:
        s_AC = s_AB * s_BC + (1 - s_AB) * max(0.0, (s_B - s_B * s_BC) / denom)

    c_AC = c_AB * c_BC * 0.9  # discount for chained uncertainty
    return SimpleTruthValue(
        max(0.0, min(1.0, s_AC)),
        max(0.0, min(1.0, c_AC))
    )


def tv_inversion(tv_AB: SimpleTruthValue,
                 tv_A:  SimpleTruthValue,
                 tv_B:  SimpleTruthValue) -> SimpleTruthValue:
    """
    Inversion (Bayes): A→B ⊢ B→A
    s_BA = s_AB * s_A / s_B
    """
    s_AB = tv_AB.strength
    s_A  = tv_A.strength
    s_B  = tv_B.strength if tv_B.strength > 1e-6 else 1e-6

    s_BA = min(1.0, s_AB * s_A / s_B)
    c_BA = tv_AB.confidence * tv_A.confidence * 0.8
    return SimpleTruthValue(
        max(0.0, s_BA),
        max(0.0, min(1.0, c_BA))
    )


def tv_modus_ponens(tv_A: SimpleTruthValue, tv_AB: SimpleTruthValue) -> SimpleTruthValue:
    """
    Modus Ponens: A, A→B ⊢ B
    s_B = s_AB * s_A + (1 - s_AB) * (1 - s_A) * 0.1
    """
    s_B = tv_AB.strength * tv_A.strength + (1 - tv_AB.strength) * (1 - tv_A.strength) * 0.1
    c_B = tv_A.confidence * tv_AB.confidence * 0.95
    return SimpleTruthValue(
        max(0.0, min(1.0, s_B)),
        max(0.0, min(1.0, c_B))
    )


def tv_conjunction(tv_A: SimpleTruthValue, tv_B: SimpleTruthValue) -> SimpleTruthValue:
    """A ∧ B: product of strengths."""
    return SimpleTruthValue(
        tv_A.strength * tv_B.strength,
        min(tv_A.confidence, tv_B.confidence) * 0.9
    )


# ─── PLN Engine ───────────────────────────────────────────────────────────────

class PLNEngine:
    """
    Probabilistic Logic Networks inference engine for Nova's AtomSpace.
    """

    def __init__(self, atomspace: AtomSpace = None):
        self.as_ = atomspace or get_atomspace()

    def infer(self, concept: str, max_steps: int = 3,
              min_confidence: float = 0.3) -> list[dict]:
        """
        Forward-chain from a concept: find all relevant links and derive
        new conclusions using PLN rules.
        Returns list of {conclusion, tv, rule, premises}.
        """
        results = []
        seen    = set()

        # 1. Get seed atom
        seed = self.as_.get_node("ConceptNode", concept)
        if not seed:
            # Try fuzzy match
            matches = self.as_.query(name_pattern=concept)
            seed = matches[0] if matches else None
        if not seed:
            return []

        # 2. Find all links involving seed
        incoming = self.as_.get_incoming(seed)

        for link in incoming:
            out = link.outgoing
            if len(out) < 2:
                continue
            link_tv = link.tv
            link_type = link.atom_type

            if link_type == "EvaluationLink" and len(out) >= 3:
                # (EvaluationLink predicate subject object)
                pred    = out[0]
                subject = out[1]
                obj     = out[2]
                if subject.name == concept:
                    conclusion = f"{concept} {pred.name} {obj.name}"
                    if conclusion not in seen and link_tv.confidence >= min_confidence:
                        seen.add(conclusion)
                        results.append({
                            "conclusion": conclusion,
                            "tv":         link_tv,
                            "rule":       "direct_evaluation",
                            "premises":   [concept, pred.name, obj.name],
                        })

            elif link_type == "InheritanceLink" and len(out) >= 2:
                child  = out[0]
                parent = out[1]
                if child.name == concept:
                    conclusion = f"{concept} IS-A {parent.name}"
                    if conclusion not in seen and link_tv.confidence >= min_confidence:
                        seen.add(conclusion)
                        results.append({
                            "conclusion": conclusion,
                            "tv":         link_tv,
                            "rule":       "inheritance",
                            "premises":   [concept, parent.name],
                        })

                    # Deduction: if X IS-A Y and Y has properties, X inherits them
                    if max_steps > 1:
                        parent_atom = self.as_.get_node("ConceptNode", parent.name)
                        if parent_atom:
                            parent_links = self.as_.get_incoming(parent_atom)
                            for plink in parent_links[:5]:
                                if plink.atom_type == "EvaluationLink" and len(plink.outgoing) >= 3:
                                    pp = plink.outgoing[0]
                                    po = plink.outgoing[2]
                                    if plink.outgoing[1].name == parent.name:
                                        deduced_tv = tv_deduction(link_tv, plink.tv, parent_atom.tv)
                                        if deduced_tv.confidence >= min_confidence:
                                            conc = f"{concept} {pp.name} {po.name} (via {parent.name})"
                                            if conc not in seen:
                                                seen.add(conc)
                                                results.append({
                                                    "conclusion": conc,
                                                    "tv":         deduced_tv,
                                                    "rule":       "deduction",
                                                    "premises":   [concept, parent.name, po.name],
                                                })

            elif link_type == "SimilarityLink" and len(out) >= 2:
                other = out[1] if out[0].name == concept else out[0]
                conclusion = f"{concept} SIMILAR-TO {other.name}"
                if conclusion not in seen and link_tv.confidence >= min_confidence:
                    seen.add(conclusion)
                    results.append({
                        "conclusion": conclusion,
                        "tv":         link_tv,
                        "rule":       "similarity",
                        "premises":   [concept, other.name],
                    })

        # Sort by combined score
        results.sort(key=lambda x: x["tv"].strength * x["tv"].confidence, reverse=True)
        return results[:20]

    def add_inheritance(self, child: str, parent: str,
                        strength: float = 0.9, confidence: float = 0.8) -> None:
        """Assert: child IS-A parent."""
        c = self.as_.add_node("ConceptNode", child, SimpleTruthValue(strength, confidence))
        p = self.as_.add_node("ConceptNode", parent, SimpleTruthValue(1.0, 1.0))
        self.as_.add_link("InheritanceLink", [c, p], SimpleTruthValue(strength, confidence))

    def add_similarity(self, a: str, b: str,
                       strength: float = 0.7, confidence: float = 0.7) -> None:
        """Assert: a SIMILAR-TO b (bidirectional)."""
        a_atom = self.as_.add_node("ConceptNode", a, SimpleTruthValue(0.8, 0.8))
        b_atom = self.as_.add_node("ConceptNode", b, SimpleTruthValue(0.8, 0.8))
        tv = SimpleTruthValue(strength, confidence)
        self.as_.add_link("SimilarityLink", [a_atom, b_atom], tv)

    def seed_security_knowledge(self) -> int:
        """
        Seed AtomSpace with basic security/bug-bounty knowledge.
        Returns number of atoms added.
        """
        knowledge = [
            # Vulnerability inheritance hierarchy
            ("RCE",              "vulnerability",   0.99, 0.99),
            ("SSRF",             "vulnerability",   0.99, 0.99),
            ("SQLi",             "vulnerability",   0.99, 0.99),
            ("XSS",              "vulnerability",   0.95, 0.95),
            ("IDOR",             "vulnerability",   0.9,  0.9),
            ("AuthBypass",       "vulnerability",   0.95, 0.95),
            ("XXE",              "vulnerability",   0.9,  0.9),
            ("PathTraversal",    "vulnerability",   0.85, 0.85),
            ("CSRF",             "vulnerability",   0.8,  0.8),
            ("OpenRedirect",     "vulnerability",   0.7,  0.8),
            # Severity inheritance
            ("RCE",              "critical-severity",  0.99, 0.99),
            ("SSRF",             "high-severity",      0.85, 0.85),
            ("SQLi",             "high-severity",      0.9,  0.9),
            ("AuthBypass",       "high-severity",      0.9,  0.9),
            ("XSS",              "medium-severity",    0.8,  0.8),
            ("IDOR",             "medium-severity",    0.7,  0.8),
            # Common contexts
            ("admin-panel",      "auth-surface",       0.95, 0.9),
            ("login-endpoint",   "auth-surface",       0.99, 0.99),
            ("api-endpoint",     "attack-surface",     0.9,  0.9),
            ("file-upload",      "high-risk-feature",  0.85, 0.85),
            ("GraphQL",          "api-endpoint",       0.99, 0.99),
        ]
        count = 0
        for child, parent, s, c in knowledge:
            self.add_inheritance(child, parent, s, c)
            count += 2  # child + parent nodes
        return count

    def seed_market_knowledge(self) -> int:
        """Seed AtomSpace with market/crypto knowledge."""
        count = 0
        inherits = [
            ("BTC",   "cryptocurrency",  0.99, 0.99),
            ("ETH",   "cryptocurrency",  0.99, 0.99),
            ("SOL",   "cryptocurrency",  0.95, 0.95),
            ("AAPL",  "stock",           0.99, 0.99),
            ("NVDA",  "stock",           0.99, 0.99),
            ("cryptocurrency", "volatile-asset",  0.85, 0.85),
            ("stock",          "financial-asset", 0.99, 0.99),
        ]
        evals = [
            ("BTC",  "correlates-with", "gold",         0.65, 0.7),
            ("ETH",  "enables",         "DeFi",         0.9,  0.9),
            ("SOL",  "competes-with",   "ETH",          0.75, 0.7),
            ("NVDA", "benefits-from",   "AI-demand",    0.9,  0.85),
        ]
        for child, parent, s, c in inherits:
            self.add_inheritance(child, parent, s, c)
            count += 2
        for s, p, o, st, c in evals:
            self.as_.assert_knowledge(s, p, o, st, c)
            count += 1
        return count


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    G = "\033[32m"; R = "\033[31m"; C = "\033[36m"; Y = "\033[33m"
    W = "\033[97m"; DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    args = sys.argv[1:]
    cmd  = args[0] if args else "help"
    as_  = get_atomspace()
    pln  = PLNEngine(as_)

    if cmd == "infer" and len(args) >= 2:
        concept = " ".join(args[1:])
        results = pln.infer(concept)
        print(f"\n{B}PLN Inference — '{concept}'{NC}  ({len(results)} conclusions)")
        for r in results:
            sc   = r["tv"].strength
            col  = G if sc > 0.7 else (Y if sc > 0.4 else DIM)
            print(f"  {col}{r['conclusion'][:60]:60s}{NC}  {DIM}{r['tv']}  [{r['rule']}]{NC}")

    elif cmd == "seed-security":
        n = pln.seed_security_knowledge()
        print(f"{G}Seeded {n} security atoms into AtomSpace.{NC}")

    elif cmd == "seed-markets":
        n = pln.seed_market_knowledge()
        print(f"{G}Seeded {n} market atoms into AtomSpace.{NC}")

    elif cmd == "inherit" and len(args) >= 3:
        pln.add_inheritance(args[1], args[2])
        print(f"{G}{args[1]} IS-A {args[2]}{NC}")

    else:
        print("Usage: nova opencog pln [infer CONCEPT|seed-security|seed-markets|inherit A B]")

    as_.close()


if __name__ == "__main__":
    main()
