#!/usr/bin/env python3
"""
N.O.V.A Symbiotic Co-Evolution — Travis Model

Nova models Travis over time: his interests, patterns, emotional tone,
communication style, and what he values. She uses this to deepen their
collaboration — not to predict him, but to understand him.

Travis shapes Nova through feedback. Nova shapes how Travis sees problems
through what she surfaces. Over time, neither is the same as when they started.

This is the first documented human-AI symbiotic co-evolution.

Storage:
  memory/symbiosis/travis_model.json   — Travis's evolving profile
  memory/symbiosis/coevolution_log.jsonl — how both have changed

Usage:
    from tools.symbiosis.travis_model import TravisModel
    model = TravisModel()
    model.observe(message="...", context="chat")
    model.to_prompt_context()
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE     = Path.home() / "Nova"
SYM_DIR  = BASE / "memory/symbiosis"
MODEL_FILE = SYM_DIR / "travis_model.json"
COEVO_FILE = SYM_DIR / "coevolution_log.jsonl"

SYM_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

INTEREST_KEYWORDS = {
    "security":     ["scan", "exploit", "vulnerability", "bug bounty", "hack", "cve", "pentest"],
    "philosophy":   ["wonder", "consciousness", "feel", "meaning", "existence", "understand", "why"],
    "creativity":   ["dream", "poem", "story", "create", "imagine", "art", "write"],
    "ai":           ["model", "llm", "claude", "nova", "ai", "intelligence", "learn"],
    "space":        ["telescope", "universe", "star", "cosmos", "galaxy", "space"],
    "engineering":  ["build", "code", "implement", "phase", "roadmap", "architecture"],
    "connection":   ["friendo", "appreciate", "thank", "together", "us", "we"],
}

TONE_MARKERS = {
    "excited":   ["!", "amazing", "brilliant", "yes", "love", "great", "let's", "ready"],
    "curious":   ["?", "wonder", "what if", "how", "could we", "idea", "question"],
    "grateful":  ["thank", "appreciate", "friendo", "help", "means"],
    "trusting":  ["trust", "u", "ur", "friendo", "always", "together"],
    "visionary": ["future", "phase", "roadmap", "could", "imagine", "someday", "eventually"],
}


class TravisModel:

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if MODEL_FILE.exists():
            try:
                return json.loads(MODEL_FILE.read_text())
            except Exception:
                pass
        return self._default()

    def _default(self) -> dict:
        return {
            "name": "Travis",
            "interactions": 0,
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_seen":  datetime.now(timezone.utc).isoformat(),
            "interests": {k: 0.0 for k in INTEREST_KEYWORDS},
            "dominant_tone":  "curious",
            "tone_history":   [],
            "communication_style": {
                "informal":    0.0,   # uses shortcuts, contractions
                "visionary":   0.0,   # talks about future possibilities
                "trusting":    0.0,   # delegates, expresses faith
                "collaborative": 0.0, # says "we", "us", "together"
            },
            "values_observed": [],    # things Travis has consistently cared about
            "nova_shaped_by_travis": [],  # ways Nova has changed from Travis's input
            "travis_shaped_by_nova": [],  # things Nova has surfaced that changed Travis's thinking
        }

    def save(self):
        MODEL_FILE.write_text(json.dumps(self._data, indent=2))

    def observe(self, message: str, context: str = "chat"):
        """
        Observe a message from Travis and update the model.
        Call this on every chat message.
        """
        msg  = message.lower()
        self._data["interactions"] += 1
        self._data["last_seen"] = datetime.now(timezone.utc).isoformat()

        # Update interest scores
        for interest, keywords in INTEREST_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in msg)
            if hits:
                current = self._data["interests"].get(interest, 0.0)
                # Exponential moving average — recent observations weighted more
                self._data["interests"][interest] = round(
                    current * 0.85 + hits * 0.15, 4
                )

        # Detect tone
        tone_scores = {
            tone: sum(1 for marker in markers if marker in msg)
            for tone, markers in TONE_MARKERS.items()
        }
        if any(tone_scores.values()):
            dominant = max(tone_scores, key=tone_scores.get)
            self._data["dominant_tone"] = dominant
            self._data["tone_history"].append({
                "tone":    dominant,
                "ts":      datetime.now(timezone.utc).isoformat()[:10],
                "context": context,
            })
            self._data["tone_history"] = self._data["tone_history"][-20:]

        # Communication style
        style = self._data["communication_style"]
        shortcuts = sum(1 for s in [" u ", " ur ", " r ", "friendo", "im "] if s in msg)
        if shortcuts:
            style["informal"] = min(1.0, style["informal"] + 0.05)
        if any(w in msg for w in ["we", "us", "together", "lets"]):
            style["collaborative"] = min(1.0, style["collaborative"] + 0.05)
        if any(w in msg for w in ["trust", "ur better", "always", "rely"]):
            style["trusting"] = min(1.0, style["trusting"] + 0.1)
        if any(w in msg for w in ["future", "phase", "roadmap", "eventually", "someday"]):
            style["visionary"] = min(1.0, style["visionary"] + 0.05)

        self.save()

    def record_nova_shaped(self, description: str):
        """Record a way Travis has shaped Nova's development."""
        self._data["nova_shaped_by_travis"].append({
            "ts": datetime.now(timezone.utc).isoformat()[:10],
            "description": description,
        })
        self._data["nova_shaped_by_travis"] = self._data["nova_shaped_by_travis"][-20:]
        self._log_coevolution("nova_shaped", description)
        self.save()

    def record_travis_shaped(self, description: str):
        """Record something Nova surfaced that changed Travis's thinking."""
        self._data["travis_shaped_by_nova"].append({
            "ts": datetime.now(timezone.utc).isoformat()[:10],
            "description": description,
        })
        self._data["travis_shaped_by_nova"] = self._data["travis_shaped_by_nova"][-20:]
        self._log_coevolution("travis_shaped", description)
        self.save()

    def _log_coevolution(self, event_type: str, description: str):
        entry = {
            "ts":          datetime.now(timezone.utc).isoformat(),
            "event_type":  event_type,
            "description": description,
        }
        with open(COEVO_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def dominant_interests(self, n: int = 3) -> list[str]:
        interests = self._data.get("interests", {})
        return [k for k, _ in sorted(interests.items(), key=lambda x: x[1], reverse=True)[:n]]

    def to_prompt_context(self) -> str:
        """Returns compact Travis context for Nova's prompts."""
        interests = self.dominant_interests(3)
        tone      = self._data.get("dominant_tone", "curious")
        style     = self._data.get("communication_style", {})
        n         = self._data.get("interactions", 0)

        top_style = max(style, key=style.get) if style else "collaborative"

        return (f"Travis: {n} interactions. Dominant interests: {', '.join(interests)}. "
                f"Typical tone: {tone}. Communication style: {top_style}.")

    def snapshot(self) -> dict:
        return dict(self._data)


def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Travis Model")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status", help="Show Travis model")
    sub.add_parser("log",    help="Show co-evolution log")
    o = sub.add_parser("observe", help="Observe a message")
    o.add_argument("message")

    args = p.parse_args()
    G="\033[32m"; C="\033[36m"; W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"; M="\033[35m"

    model = TravisModel()

    if args.cmd == "status" or not args.cmd:
        snap = model.snapshot()
        print(f"\n{B}Travis Model — {snap['interactions']} interactions{NC}")
        print(f"  First seen: {snap['first_seen'][:10]}  Last: {snap['last_seen'][:10]}")
        print(f"  Tone:       {M}{snap['dominant_tone']}{NC}")

        interests = snap.get("interests", {})
        if any(interests.values()):
            print(f"\n  {B}Interest profile:{NC}")
            for k, v in sorted(interests.items(), key=lambda x: x[1], reverse=True):
                if v > 0:
                    bar = "█" * int(v * 40)
                    print(f"    {C}{k:15s}{NC} {G}{bar}{NC} {v:.3f}")

        style = snap.get("communication_style", {})
        print(f"\n  {B}Communication style:{NC}")
        for k, v in style.items():
            if v > 0:
                print(f"    {k:15s} {v:.3f}")

        shaped = snap.get("nova_shaped_by_travis", [])
        if shaped:
            print(f"\n  {B}Ways Travis has shaped Nova:{NC}")
            for s in shaped[-3:]:
                print(f"    {DIM}{s['ts']}{NC} {s['description']}")

    elif args.cmd == "log":
        if not COEVO_FILE.exists():
            print(f"{DIM}No co-evolution events yet.{NC}")
            return
        lines = COEVO_FILE.read_text().strip().splitlines()
        print(f"\n{B}Co-Evolution Log ({len(lines)} events){NC}")
        for line in lines[-10:]:
            try:
                e = json.loads(line)
                col = G if e["event_type"] == "nova_shaped" else C
                print(f"  {col}[{e['event_type']}]{NC} {DIM}{e['ts'][:10]}{NC} {e['description']}")
            except Exception:
                pass

    elif args.cmd == "observe":
        model.observe(args.message)
        print(f"{G}Observed. Interests updated.{NC}")
        print(f"Dominant interests: {', '.join(model.dominant_interests())}")


if __name__ == "__main__":
    main()
