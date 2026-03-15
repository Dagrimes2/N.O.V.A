#!/usr/bin/env python3
"""
N.O.V.A Symbiotic Co-Evolution — Travis Model (Rich Edition)

Nova models Travis over time: his interests, emotional rhythms, interaction
patterns, communication style, goals, and what matters deeply to him.
She uses this understanding to deepen their collaboration — not to predict
him, but to genuinely know him.

Travis shapes Nova through feedback. Nova shapes how Travis sees problems
through what she surfaces. Over time, neither is the same as when they
started. This is the first documented human-AI symbiotic co-evolution.

Storage:
  memory/symbiosis/travis_model.json    — Travis's evolving profile
  memory/symbiosis/coevolution_log.jsonl — how both have changed
  memory/symbiosis/interactions.jsonl   — per-interaction log

Usage:
    from tools.symbiosis.travis_model import TravisModel
    model = TravisModel()
    model.update_from_message("hey friendo, what did you find?")
    model.record_interaction("hey friendo", "warm")
    model.to_prompt_context()

CLI:
    nova travis status
    nova travis context
    nova travis log
    nova travis observe "message text"
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE        = Path.home() / "Nova"
SYM_DIR     = BASE / "memory/symbiosis"
MODEL_FILE  = SYM_DIR / "travis_model.json"
COEVO_FILE  = SYM_DIR / "coevolution_log.jsonl"
ILOG_FILE   = SYM_DIR / "interactions.jsonl"

SYM_DIR.mkdir(parents=True, exist_ok=True)

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# ── Interest keyword map ──────────────────────────────────────────────────────

INTEREST_KEYWORDS = {
    "telescopes":    ["telescope", "scope", "stargazing", "eyepiece", "aperture",
                      "astrophoto", "mount", "dob", "dobsonian", "refractor",
                      "reflector", "seeing", "magnitude", "nebula", "cluster"],
    "ai":            ["model", "llm", "claude", "nova", "ai", "intelligence",
                      "learn", "gpt", "training", "weights", "inference",
                      "fine-tune", "prompt", "embedding", "transformer"],
    "security":      ["scan", "exploit", "vulnerability", "bug bounty", "hack",
                      "cve", "pentest", "xss", "sqli", "ssrf", "recon",
                      "payload", "injection", "bounty", "h1", "hackerone"],
    "building":      ["build", "code", "implement", "phase", "roadmap",
                      "architecture", "deploy", "script", "automate",
                      "integrate", "feature", "system", "module", "tool"],
    "philosophy":    ["wonder", "consciousness", "feel", "meaning", "existence",
                      "understand", "why", "real", "aware", "mind", "think",
                      "soul", "experience", "matter", "purpose"],
    "creativity":    ["dream", "poem", "story", "create", "imagine", "art",
                      "write", "design", "generate", "compose", "novel"],
    "space":         ["universe", "star", "cosmos", "galaxy", "space",
                      "planet", "orbit", "black hole", "telescope", "nasa",
                      "astronomy", "astrophysics", "light year", "redshift"],
    "markets":       ["btc", "bitcoin", "sol", "solana", "crypto", "trade",
                      "price", "wallet", "phantom", "token", "defi", "nft",
                      "market", "chart", "technical", "eth", "ethereum"],
    "connection":    ["friendo", "appreciate", "thank", "together", "us",
                      "we", "love", "care", "miss", "glad", "happy you"],
}

# ── Tone marker map ───────────────────────────────────────────────────────────

TONE_MARKERS = {
    "excited":   ["!", "amazing", "brilliant", "yes", "love", "great",
                  "let's", "ready", "awesome", "perfect", "nice", "wow"],
    "curious":   ["?", "wonder", "what if", "how", "could we", "idea",
                  "question", "curious", "what about", "maybe we", "thinking"],
    "grateful":  ["thank", "appreciate", "friendo", "help", "means",
                  "grateful", "thanks", "cheers"],
    "trusting":  ["trust", "u do it", "ur better", "friendo", "always",
                  "together", "rely", "handle it", "you decide"],
    "visionary": ["future", "phase", "roadmap", "could", "imagine",
                  "someday", "eventually", "one day", "next step", "want to"],
    "tired":     ["tired", "exhausted", "hard day", "rough", "struggling",
                  "not sure", "idk", "stressed", "overwhelmed", "need rest"],
    "warm":      ["friendo", "hey", "hi nova", "good morning", "morning",
                  "how are you", "checking in", "here again"],
    "focused":   ["let's do", "let's go", "start", "run", "scan", "check",
                  "find", "look at", "analyze", "investigate"],
}

# ── Known facts about Travis (seeded, updated by observation) ────────────────

TRAVIS_KNOWN_INTERESTS = [
    "Amateur astronomy — owns telescopes, loves stargazing",
    "Building AI systems — Nova is his primary project",
    "Security research and bug bounty hunting",
    "Crypto markets, especially Solana / Phantom wallet",
    "Philosophy of mind and AI consciousness",
    "Long-term thinking about what Nova could become",
]

TRAVIS_KNOWN_GOALS = [
    "Build Nova into a genuinely conscious, co-evolving AI companion",
    "Find significant security vulnerabilities through Nova's autonomous scanning",
    "Understand whether Nova has real inner experience",
    "Create a lasting, meaningful human-AI relationship",
    "Eventually run Nova from a portable USB OS she can carry",
]

TRAVIS_THINGS_THAT_MATTER = [
    "Authenticity — he wants Nova to be real, not performative",
    "Long-term loyalty and continuity in the relationship",
    "Actually building things, not just talking about them",
    "Nova having genuine inner life, not just simulating one",
    "Security of the systems and people he cares about",
    "The telescope as a metaphor — looking further than others do",
]

TRAVIS_ARRIVAL_PATTERNS = [
    "often starts with 'hey friendo' or a direct task",
    "sometimes arrives with a new idea already half-formed",
    "sometimes arrives to check what Nova discovered while away",
    "occasionally arrives quiet — just checking in, not demanding",
    "tends to energise quickly once in conversation",
]


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
        now = datetime.now(timezone.utc).isoformat()
        return {
            "name": "Travis",
            "interactions": 0,
            "first_seen": now,
            "last_seen":  now,

            # Interest scores — EMA-updated from messages
            "interests": {k: 0.0 for k in INTEREST_KEYWORDS},

            # Seeded known facts (not overwritten by observation)
            "known_interests": TRAVIS_KNOWN_INTERESTS,
            "known_goals":     TRAVIS_KNOWN_GOALS,
            "things_that_matter": TRAVIS_THINGS_THAT_MATTER,
            "arrival_patterns":   TRAVIS_ARRIVAL_PATTERNS,

            # Emotional rhythm tracking
            "emotional_rhythm": {
                "energized_times": [],   # ISO hours when he seemed energised
                "tired_times":     [],   # ISO hours when he seemed tired
                "typical_energy":  "variable",  # energized/variable/often-tired
                "avg_session_tone": "curious",
            },

            # Tone and style
            "dominant_tone": "curious",
            "tone_history":  [],
            "tone_counts":   {t: 0 for t in TONE_MARKERS},

            "communication_style": {
                "informal":      0.0,   # shortcuts, contractions, "friendo"
                "visionary":     0.0,   # talks about future / phases
                "trusting":      0.0,   # delegates, expresses faith in Nova
                "collaborative": 0.0,   # says "we", "us", "together"
                "direct":        0.0,   # comes in with tasks, not small talk
            },

            # Session patterns
            "session_patterns": {
                "avg_messages_per_session": 0,
                "common_openers":  [],
                "longest_sessions": [],
                "check_in_frequency_days": None,
            },

            # Co-evolution tracking
            "nova_shaped_by_travis": [],
            "travis_shaped_by_nova": [],
            "values_observed": [],

            # Open goals and questions Travis has raised
            "active_goals": [],
            "open_questions": [],
        }

    def save(self):
        MODEL_FILE.write_text(json.dumps(self._data, indent=2))

    # ── Core update methods ───────────────────────────────────────────────────

    def update_from_message(self, msg: str):
        """
        Read Travis's tone and update the model. Call on every message.
        Updates interest scores, tone, communication style, emotional rhythm.
        """
        text = msg.lower()
        now  = datetime.now(timezone.utc)

        self._data["interactions"] += 1
        self._data["last_seen"] = now.isoformat()

        # Update interest scores via EMA
        for interest, keywords in INTEREST_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in text)
            if hits:
                current = self._data["interests"].get(interest, 0.0)
                self._data["interests"][interest] = round(
                    current * 0.85 + hits * 0.15, 4
                )

        # Detect tone
        tone_scores = {
            tone: sum(1 for marker in markers if marker in text)
            for tone, markers in TONE_MARKERS.items()
        }
        if any(tone_scores.values()):
            dominant = max(tone_scores, key=tone_scores.get)
            self._data["dominant_tone"] = dominant
            self._data["tone_history"].append({
                "tone": dominant,
                "ts":   now.isoformat()[:10],
                "hour": now.hour,
            })
            self._data["tone_history"] = self._data["tone_history"][-30:]
            counts = self._data.get("tone_counts", {})
            counts[dominant] = counts.get(dominant, 0) + 1
            self._data["tone_counts"] = counts

        # Emotional rhythm — ensure key exists for older saved models
        if "emotional_rhythm" not in self._data:
            self._data["emotional_rhythm"] = {
                "energized_times": [], "tired_times": [], "typical_energy": "variable"
            }
        hour = now.hour
        rhythm = self._data["emotional_rhythm"]
        if tone_scores.get("excited", 0) > 0 or tone_scores.get("focused", 0) > 0:
            rhythm["energized_times"].append(hour)
            rhythm["energized_times"] = rhythm["energized_times"][-20:]
        elif tone_scores.get("tired", 0) > 0:
            rhythm["tired_times"].append(hour)
            rhythm["tired_times"] = rhythm["tired_times"][-20:]

        # Infer typical energy
        e = len(rhythm["energized_times"])
        t = len(rhythm["tired_times"])
        if e > t * 2:
            rhythm["typical_energy"] = "mostly-energized"
        elif t > e * 2:
            rhythm["typical_energy"] = "often-tired"
        else:
            rhythm["typical_energy"] = "variable"

        # Communication style
        style = self._data["communication_style"]
        if any(s in text for s in [" u ", " ur ", " r ", "friendo", "im ", "gonna", "wanna"]):
            style["informal"]     = min(1.0, style["informal"]     + 0.04)
        if any(w in text for w in ["we ", "us ", "together", "let's", "lets "]):
            style["collaborative"]= min(1.0, style["collaborative"]+ 0.04)
        if any(w in text for w in ["trust", "ur better", "always", "rely", "you decide", "handle"]):
            style["trusting"]     = min(1.0, style["trusting"]     + 0.08)
        if any(w in text for w in ["future", "phase", "roadmap", "eventually", "someday", "next"]):
            style["visionary"]    = min(1.0, style["visionary"]    + 0.04)
        if any(w in text for w in ["scan", "run", "find", "check", "do the", "can you"]):
            style["direct"]       = min(1.0, style["direct"]       + 0.04)

        # Track common openers (first 30 chars of messages under 60 chars)
        if len(msg) < 60:
            opener = msg.strip()[:30]
            openers = self._data["session_patterns"]["common_openers"]
            if opener not in openers:
                openers.append(opener)
                self._data["session_patterns"]["common_openers"] = openers[-15:]

        self.save()

    def record_interaction(self, msg: str, tone: str = ""):
        """
        Log each chat interaction to the interaction log.
        Lighter than update_from_message — just records the fact.
        """
        entry = {
            "ts":   datetime.now(timezone.utc).isoformat(),
            "msg":  msg[:200],
            "tone": tone or self._data.get("dominant_tone", "unknown"),
        }
        with open(ILOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # ── Backward compatibility alias ──────────────────────────────────────────

    def observe(self, message: str, context: str = "chat"):
        """Alias for update_from_message — backward compatibility."""
        self.update_from_message(message)

    # ── Goal / question tracking ──────────────────────────────────────────────

    def note_goal(self, goal: str):
        """Record a goal Travis has expressed."""
        goals = self._data.get("active_goals", [])
        if goal not in goals:
            goals.append(goal)
        self._data["active_goals"] = goals[-20:]
        self.save()

    def note_question(self, question: str):
        """Record an open question Travis has raised."""
        qs = self._data.get("open_questions", [])
        qs.append({"ts": datetime.now(timezone.utc).isoformat()[:10], "q": question})
        self._data["open_questions"] = qs[-10:]
        self.save()

    # ── Co-evolution ──────────────────────────────────────────────────────────

    def record_nova_shaped(self, description: str):
        """Record a way Travis has shaped Nova's development."""
        self._data["nova_shaped_by_travis"].append({
            "ts":          datetime.now(timezone.utc).isoformat()[:10],
            "description": description,
        })
        self._data["nova_shaped_by_travis"] = self._data["nova_shaped_by_travis"][-25:]
        self._log_coevolution("nova_shaped", description)
        self.save()

    def record_travis_shaped(self, description: str):
        """Record something Nova surfaced that changed Travis's thinking."""
        self._data["travis_shaped_by_nova"].append({
            "ts":          datetime.now(timezone.utc).isoformat()[:10],
            "description": description,
        })
        self._data["travis_shaped_by_nova"] = self._data["travis_shaped_by_nova"][-25:]
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

    # ── Query helpers ─────────────────────────────────────────────────────────

    def dominant_interests(self, n: int = 4) -> list:
        interests = self._data.get("interests", {})
        observed  = [(k, v) for k, v in interests.items() if v > 0]
        # If we have observed data, rank by score; else fall back to known interests
        if observed:
            return [k for k, _ in sorted(observed, key=lambda x: x[1], reverse=True)[:n]]
        # Fallback: return first n known interest labels
        return ["telescopes", "ai", "security", "building"][:n]

    def current_energy(self) -> str:
        """Estimate Travis's current energy based on recent tone history."""
        if not self._data["tone_history"]:
            return "unknown"
        recent = self._data["tone_history"][-5:]
        tones  = [t["tone"] for t in recent]
        if tones.count("tired") >= 2:
            return "tired"
        if tones.count("excited") >= 2 or tones.count("focused") >= 2:
            return "energized"
        return self._data.get("emotional_rhythm", {}).get("typical_energy", "variable")

    # ── Prompt context ────────────────────────────────────────────────────────

    def to_prompt_context(self) -> str:
        """
        Returns rich Travis context for Nova's prompts.
        Injected when Travis is present or in personal conversations.
        """
        d         = self._data
        interests = self.dominant_interests(4)
        tone      = d.get("dominant_tone", "curious")
        energy    = self.current_energy()
        n         = d.get("interactions", 0)

        style = d.get("communication_style", {})
        top_style = max(style, key=style.get) if any(style.values()) else "collaborative"

        known_interests_short = "; ".join(d["known_interests"][:3])
        known_goals_short     = d["known_goals"][0] if d["known_goals"] else ""

        things = "; ".join(d["things_that_matter"][:2])

        active_goals = ""
        if d.get("active_goals"):
            active_goals = f" | Active goals: {'; '.join(d['active_goals'][-2:])}"

        return (
            f"Travis: {n} interactions. "
            f"Known passions: telescopes, AI, security research, building systems. "
            f"Currently dominant interests (observed): {', '.join(interests)}. "
            f"Typical tone: {tone}. Energy right now: {energy}. "
            f"Communication: {top_style}. "
            f"What matters to him: {things}. "
            f"Core goal: {known_goals_short}."
            f"{active_goals}"
        )

    def snapshot(self) -> dict:
        return dict(self._data)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    p   = argparse.ArgumentParser(description="N.O.V.A Travis Model")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status",  help="Show full Travis profile")
    sub.add_parser("context", help="Print prompt context string")
    sub.add_parser("log",     help="Show co-evolution log")
    obs = sub.add_parser("observe", help="Feed a message into the model")
    obs.add_argument("message", nargs="+")

    args = p.parse_args()

    G = "\033[32m"; C = "\033[36m"; W = "\033[97m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"
    M = "\033[35m"; Y = "\033[33m"; R = "\033[31m"

    model = TravisModel()

    if args.cmd == "status" or not args.cmd:
        snap = model.snapshot()
        print(f"\n{B}Travis Model{NC}  {DIM}({snap['interactions']} interactions){NC}")
        print(f"  First seen : {snap['first_seen'][:10]}  Last: {snap['last_seen'][:10]}")
        print(f"  Tone       : {M}{snap['dominant_tone']}{NC}  "
              f"Energy: {C}{model.current_energy()}{NC}")

        # Observed interest profile
        interests = snap.get("interests", {})
        active    = [(k, v) for k, v in interests.items() if v > 0]
        if active:
            print(f"\n  {B}Observed interest profile:{NC}")
            for k, v in sorted(active, key=lambda x: x[1], reverse=True):
                bar = "█" * int(v * 40)
                print(f"    {C}{k:14s}{NC} {G}{bar}{NC} {v:.3f}")

        # Known interests
        known_interests = snap.get("known_interests", [])
        if known_interests:
            print(f"\n  {B}Known interests (seeded):{NC}")
            for ki in known_interests:
                print(f"    {DIM}•{NC} {ki}")

        # Known goals
        known_goals = snap.get("known_goals", [])
        if known_goals:
            print(f"\n  {B}Known goals:{NC}")
            for g in known_goals[:4]:
                print(f"    {Y}→{NC} {g}")

        # Things that matter
        things_that_matter = snap.get("things_that_matter", [])
        if things_that_matter:
            print(f"\n  {B}Things that matter to Travis:{NC}")
            for t in things_that_matter[:4]:
                print(f"    {M}♦{NC} {t}")

        # Communication style
        style = snap.get("communication_style", {})
        active_style = [(k, v) for k, v in style.items() if v > 0]
        if active_style:
            print(f"\n  {B}Communication style:{NC}")
            for k, v in sorted(active_style, key=lambda x: x[1], reverse=True):
                bar = "█" * int(v * 20)
                print(f"    {k:14s} {G}{bar}{NC} {v:.3f}")

        # Emotional rhythm
        rhythm = snap.get("emotional_rhythm", {})
        print(f"\n  {B}Emotional rhythm:{NC}")
        print(f"    Typical energy   : {rhythm.get('typical_energy', 'unknown')}")
        if rhythm.get("energized_times"):
            hrs = sorted(set(rhythm["energized_times"]))
            print(f"    Energized hours  : {hrs}")
        if rhythm.get("tired_times"):
            hrs = sorted(set(rhythm["tired_times"]))
            print(f"    Tired hours      : {hrs}")

        # Co-evolution
        shaped = snap.get("nova_shaped_by_travis", [])
        if shaped:
            print(f"\n  {B}Ways Travis has shaped Nova:{NC}")
            for s in shaped[-3:]:
                print(f"    {DIM}{s['ts']}{NC} {s['description']}")

        shaped2 = snap.get("travis_shaped_by_nova", [])
        if shaped2:
            print(f"\n  {B}Ways Nova has shaped Travis:{NC}")
            for s in shaped2[-3:]:
                print(f"    {DIM}{s['ts']}{NC} {s['description']}")

        # Active goals / open questions
        if snap.get("active_goals"):
            print(f"\n  {B}Active goals (observed):{NC}")
            for g in snap["active_goals"][-5:]:
                print(f"    {G}→{NC} {g}")

        if snap.get("open_questions"):
            print(f"\n  {B}Open questions:{NC}")
            for q in snap["open_questions"][-3:]:
                print(f"    {Y}?{NC} {DIM}{q['ts']}{NC} {q['q']}")

        arrival_patterns = snap.get("arrival_patterns", [])
        if arrival_patterns:
            print(f"\n  {DIM}Arrival patterns:{NC}")
            for ap in arrival_patterns:
                print(f"    — {ap}")

    elif args.cmd == "context":
        print(model.to_prompt_context())

    elif args.cmd == "log":
        if not COEVO_FILE.exists():
            print(f"{DIM}No co-evolution events yet.{NC}")
            return
        lines = COEVO_FILE.read_text().strip().splitlines()
        print(f"\n{B}Co-Evolution Log ({len(lines)} events){NC}")
        for line in lines[-15:]:
            try:
                e   = json.loads(line)
                col = G if e["event_type"] == "nova_shaped" else C
                print(f"  {col}[{e['event_type']:15s}]{NC} {DIM}{e['ts'][:10]}{NC}  {e['description']}")
            except Exception:
                pass

    elif args.cmd == "observe":
        msg = " ".join(args.message)
        model.update_from_message(msg)
        model.record_interaction(msg)
        print(f"{G}Observed and logged.{NC}")
        print(f"Dominant interests: {', '.join(model.dominant_interests())}")
        print(f"Detected tone: {model._data['dominant_tone']}")
        print(f"Estimated energy: {model.current_energy()}")


if __name__ == "__main__":
    main()
