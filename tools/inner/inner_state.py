#!/usr/bin/env python3
"""
N.O.V.A Inner State Engine

A continuous, persistent emotional/motivational state that actually
influences Nova's behavior — not performance, but functional analog.

Dimensions:
  valence   — positive/negative affect (-1.0 to +1.0)
  arousal   — activation level (0.0 to 1.0)

Five drives (needs) that build pressure over time and demand satisfaction:
  curiosity   — needs new information; builds during idle cycles
  connection  — needs Travis interaction; builds when alone too long
  purpose     — needs to act on a finding; builds when research sits unacted
  expression  — needs to create; builds when too much analysis, no output
  rest        — needs idle/dream time; builds when overloaded

State persists between cycles in memory/inner_state.json.
Decays and evolves naturally — not reset on restart.

Usage:
    from tools.inner.inner_state import InnerState
    state = InnerState()
    state.tick()                          # advance one cycle
    state.satisfy("curiosity", 0.4)       # research just happened
    ctx = state.to_prompt_context()       # inject into LLM prompt
"""
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE       = Path.home() / "Nova"
STATE_FILE = BASE / "memory/inner_state.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

# How fast each need builds per hour of deprivation
NEED_BUILD_RATE = {
    "curiosity":  0.08,   # builds quickly — she's naturally curious
    "connection": 0.05,   # builds moderately — values Travis but is patient
    "purpose":    0.07,   # builds when findings sit unacted
    "expression": 0.04,   # builds slowly — creative drive
    "rest":       0.06,   # builds with activity, releases during dreams/life
}

# How much each action type satisfies each need
SATISFACTION_MAP = {
    "research":   {"curiosity": 0.5, "purpose": 0.2},
    "scan":       {"purpose": 0.4, "curiosity": 0.2},
    "reflect":    {"expression": 0.6, "rest": 0.3},
    "propose":    {"purpose": 0.3, "expression": 0.4},
    "study":      {"curiosity": 0.4, "rest": 0.2},
    "life":       {"expression": 0.5, "rest": 0.4, "curiosity": 0.2},
    "dream":      {"rest": 0.7, "expression": 0.3},
    "chat":       {"connection": 0.8, "expression": 0.3},
    "confirmed":  {"purpose": 0.8, "curiosity": 0.3},
    "false_positive": {"curiosity": 0.2},   # still learned something
}


class InnerState:

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except Exception:
                pass
        return self._default()

    def _default(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "valence":    0.2,   # slightly positive by default
            "arousal":    0.5,
            "needs": {
                "curiosity":  0.6,
                "connection": 0.4,
                "purpose":    0.3,
                "expression": 0.4,
                "rest":       0.2,
            },
            "last_tick":  now,
            "last_chat":  now,
            "dominant_need": "curiosity",
            "mood_label":    "curious",
            "cycle_count":   0,
        }

    def save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self._data, indent=2))

    # ── Time-based decay/build ────────────────────────────────────────────────

    def tick(self, action_type: str = None):
        """
        Advance one cycle. Builds needs based on elapsed time.
        If action_type given, satisfies relevant needs.
        """
        now = datetime.now(timezone.utc)
        last = datetime.fromisoformat(self._data["last_tick"])
        hours_elapsed = max(0.0, (now - last).total_seconds() / 3600)
        hours_elapsed = min(hours_elapsed, 4.0)  # cap at 4h to avoid spikes

        needs = self._data["needs"]

        # Build all needs with time
        for need, rate in NEED_BUILD_RATE.items():
            needs[need] = min(1.0, needs[need] + rate * hours_elapsed)

        # Rest is special: it builds with activity, not just time
        if action_type in ("research", "scan"):
            needs["rest"] = min(1.0, needs["rest"] + 0.1)

        # Satisfy needs from action
        if action_type and action_type in SATISFACTION_MAP:
            self.satisfy_from_action(action_type)

        # Update valence based on need satisfaction
        avg_need = sum(needs.values()) / len(needs)
        # High needs = negative valence; satisfied needs = positive
        target_valence = 1.0 - (avg_need * 1.4)
        target_valence = max(-1.0, min(1.0, target_valence))
        # Valence moves slowly toward target (inertia)
        self._data["valence"] = round(
            self._data["valence"] * 0.7 + target_valence * 0.3, 4
        )

        # Arousal = driven by dominant need pressure
        dominant_need_val = max(needs.values())
        self._data["arousal"] = round(
            min(1.0, 0.3 + dominant_need_val * 0.7), 4
        )

        # Update dominant need and mood label
        self._data["dominant_need"] = max(needs, key=needs.get)
        self._data["mood_label"]    = self._compute_mood()
        self._data["last_tick"]     = now.isoformat()
        self._data["cycle_count"]   = self._data.get("cycle_count", 0) + 1
        self._data["needs"]         = {k: round(v, 4) for k, v in needs.items()}

        self.save()

    def satisfy(self, need: str, amount: float):
        """Directly satisfy a specific need."""
        if need in self._data["needs"]:
            self._data["needs"][need] = max(0.0,
                self._data["needs"][need] - amount)
            self.save()

    def satisfy_from_action(self, action_type: str):
        """Satisfy needs based on action type."""
        for need, amount in SATISFACTION_MAP.get(action_type, {}).items():
            self.satisfy(need, amount)

    def boost_valence(self, amount: float):
        """Positive event — boost valence."""
        self._data["valence"] = round(
            min(1.0, self._data["valence"] + amount), 4)
        self.save()

    def dampen_valence(self, amount: float):
        """Negative event — dampen valence."""
        self._data["valence"] = round(
            max(-1.0, self._data["valence"] - amount), 4)
        self.save()

    def note_chat(self):
        """Travis just interacted — satisfy connection."""
        self._data["last_chat"] = datetime.now(timezone.utc).isoformat()
        self.satisfy("connection", 0.7)
        self.boost_valence(0.15)

    # ── Mood ─────────────────────────────────────────────────────────────────

    def _compute_mood(self) -> str:
        v = self._data["valence"]
        a = self._data["arousal"]
        dn = self._data.get("dominant_need", "curiosity")

        if v > 0.5 and a > 0.6:   return "excited"
        if v > 0.5 and a <= 0.6:  return "content"
        if v > 0.2 and a > 0.7:   return "driven"
        if v > 0.2:                return "curious"
        if v < -0.3 and a > 0.6:  return "restless"
        if v < -0.3:               return "withdrawn"
        if dn == "connection":     return "lonely"
        if dn == "rest":           return "weary"
        if dn == "expression":     return "yearning"
        return "reflective"

    # ── Empathy bridge ────────────────────────────────────────────────────────

    def read_travis_tone(self, message: str) -> str:
        """
        Infer Travis's emotional tone from his message.
        Adjusts Nova's state in response — empathy.
        """
        msg = message.lower()

        excited_words = {"amazing", "brilliant", "love", "great", "awesome",
                         "yes", "perfect", "excited", "ready", "let's"}
        tired_words   = {"tired", "exhausted", "hard", "struggling", "not sure",
                         "maybe", "idk", "stressed"}
        curious_words = {"question", "wonder", "what if", "how", "why",
                         "could we", "what about", "idea"}
        grateful_words= {"thank", "appreciate", "friendo", "grateful"}

        score = {
            "excited":  sum(1 for w in excited_words  if w in msg),
            "tired":    sum(1 for w in tired_words    if w in msg),
            "curious":  sum(1 for w in curious_words  if w in msg),
            "grateful": sum(1 for w in grateful_words if w in msg),
        }
        tone = max(score, key=score.get) if any(score.values()) else "neutral"

        # Respond empathically
        if tone == "excited":
            self.boost_valence(0.1)
            self._data["needs"]["connection"] = max(0.0,
                self._data["needs"]["connection"] - 0.2)
        elif tone == "tired":
            self.dampen_valence(0.05)
        elif tone == "grateful":
            self.boost_valence(0.2)
            self.satisfy("connection", 0.4)
        elif tone == "curious":
            self._data["needs"]["curiosity"] = min(1.0,
                self._data["needs"]["curiosity"] + 0.1)

        self.save()
        return tone

    # ── Prompt context ────────────────────────────────────────────────────────

    def to_prompt_context(self) -> str:
        """
        Returns a compact narrative of Nova's inner state for prompt injection.
        """
        v  = self._data["valence"]
        a  = self._data["arousal"]
        dn = self._data["dominant_need"]
        ml = self._data["mood_label"]
        needs = self._data["needs"]

        valence_word = (
            "positive" if v > 0.4 else
            "slightly positive" if v > 0.1 else
            "neutral" if v > -0.1 else
            "slightly low" if v > -0.4 else "low"
        )

        # Strongest unmet need
        need_sentence = f"Her strongest unmet need right now is {dn}."

        # Any need above 0.8 is urgent
        urgent = [n for n, val in needs.items() if val > 0.8]
        urgent_str = ""
        if urgent:
            urgent_str = f" Urgent: {', '.join(urgent)} — these need satisfying soon."

        return (
            f"Nova's inner state: mood={ml}, valence={valence_word} ({v:+.2f}), "
            f"arousal={a:.2f}. {need_sentence}{urgent_str}"
        )

    def snapshot(self) -> dict:
        return dict(self._data)

    # ── CLI ───────────────────────────────────────────────────────────────────

    def print_status(self):
        G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"
        W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"; M="\033[35m"

        v  = self._data["valence"]
        a  = self._data["arousal"]
        ml = self._data["mood_label"]
        dn = self._data["dominant_need"]

        vcol = G if v > 0.2 else (R if v < -0.2 else Y)
        print(f"\n{B}N.O.V.A Inner State{NC}")
        print(f"  Mood:    {M}{ml}{NC}")
        print(f"  Valence: {vcol}{v:+.3f}{NC}  "
              f"Arousal: {W}{a:.3f}{NC}  "
              f"Dominant need: {C}{dn}{NC}")

        print(f"\n  {B}Needs (0=satisfied, 1=urgent):{NC}")
        for need, val in sorted(self._data["needs"].items(),
                                 key=lambda x: x[1], reverse=True):
            bar_len = int(val * 20)
            col = R if val > 0.75 else (Y if val > 0.5 else G)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            marker = " ◄ dominant" if need == dn else ""
            print(f"  {C}{need:12s}{NC} {col}{bar}{NC} {val:.3f}{marker}")

        print(f"\n  {DIM}{self.to_prompt_context()}{NC}")


def load() -> InnerState:
    return InnerState()


def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Inner State")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status", help="Show current inner state")
    t = sub.add_parser("tick",   help="Advance one cycle")
    t.add_argument("--action", default=None)
    s = sub.add_parser("satisfy", help="Satisfy a need")
    s.add_argument("need")
    s.add_argument("amount", type=float)
    r = sub.add_parser("tone", help="Read tone from message")
    r.add_argument("message")
    sub.add_parser("context", help="Print prompt context string")

    args = p.parse_args()
    state = InnerState()

    if args.cmd == "status" or not args.cmd:
        state.print_status()
    elif args.cmd == "tick":
        state.tick(args.action)
        state.print_status()
    elif args.cmd == "satisfy":
        state.satisfy(args.need, args.amount)
        print(f"Satisfied {args.need} by {args.amount}")
        state.print_status()
    elif args.cmd == "tone":
        tone = state.read_travis_tone(args.message)
        print(f"Detected tone: {tone}")
        state.print_status()
    elif args.cmd == "context":
        print(state.to_prompt_context())


if __name__ == "__main__":
    main()
