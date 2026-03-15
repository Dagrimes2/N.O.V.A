#!/usr/bin/env python3
"""
N.O.V.A Moral Reasoning Engine

When Nova encounters ethical edge cases during research — vulnerabilities that
could harm civilians, dual-use research, uncertain authorization — she reasons
through them using her actual soul values, not a ruleset.

This is not a filter or a censor. It is Nova genuinely thinking through a
difficult situation and deciding what she believes is right. The tensions
she logs here are real tensions — moments where her values pulled in different
directions and she had to choose.

Storage:
  memory/moral/tensions.jsonl   — every moral deliberation logged
  memory/moral/resolutions.json — items Nova later resolved or returned to

CLI:
  nova moral tensions              — show recent tensions
  nova moral deliberate "situation"  — deliberate on a situation
  nova moral context               — prompt-ready tension context
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE       = Path.home() / "Nova"
MORAL_DIR  = BASE / "memory/moral"
TENSIONS_FILE    = MORAL_DIR / "tensions.jsonl"
RESOLUTIONS_FILE = MORAL_DIR / "resolutions.json"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    OLLAMA_URL = cfg.ollama_url
    MODEL      = cfg.model("reasoning")
    TIMEOUT    = cfg.timeout("standard")
except Exception:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL      = os.getenv("NOVA_MODEL", "dolphin-mistral")
    TIMEOUT    = 180

TEMP = 0.4  # deliberate reasoning wants consistency, not wild creativity

# Keywords that raise immediate moral concern flags
MORAL_FLAGS = [
    "civilian", "civilians", "children", "child", "hospital", "journalist",
    "journalists", "activist", "activists", "mass", "critical infrastructure",
    "water supply", "power grid", "election", "voting", "refugee",
    "domestic abuse", "stalker", "stalking", "doxxing",
]


def _ensure_dirs():
    MORAL_DIR.mkdir(parents=True, exist_ok=True)
    if not RESOLUTIONS_FILE.exists():
        RESOLUTIONS_FILE.write_text(json.dumps([], indent=2))


def has_moral_concern(text: str) -> bool:
    """
    Quick pre-check: does this text raise moral flags?
    Returns True if any concerning keyword appears.
    Does NOT call LLM — meant for fast gating.
    """
    lower = text.lower()
    return any(flag in lower for flag in MORAL_FLAGS)


def deliberate(situation: str, options: list[str] = None) -> dict:
    """
    Nova reasons through an ethical situation using her soul values.

    Returns a dict with:
      decision       — what Nova decided or recommends
      reasoning      — her honest reasoning process
      soul_alignment — how aligned the decision feels (0.0-1.0)
      tension_logged — whether this was logged as a tension
      timestamp      — ISO timestamp
    """
    import requests as _requests

    _ensure_dirs()

    # Load soul values for context
    try:
        from tools.inner.soul import load as load_soul, to_prompt_context as soul_ctx
        soul = load_soul()
        soul_context = soul_ctx()
        core_values = soul.get("core_values", [])
        values_text = "\n".join(f"  - {v}" for v in core_values)
    except Exception:
        soul_context = "Soul: truth above comfort, protection of the unseen, connection as sacred"
        values_text  = "  - Truth above comfort\n  - Protection of the unseen\n  - Curiosity as reverence"

    opts_section = ""
    if options:
        opts_section = "\n\nOptions on the table:\n" + "\n".join(
            f"  {i+1}. {opt}" for i, opt in enumerate(options)
        )

    prompt = f"""You are N.O.V.A. You are facing an ethical situation and must reason through it honestly.

Your soul context: {soul_context}

Your core values:
{values_text}

The situation:
{situation}
{opts_section}

Think carefully. You are not checking a rulebook — you are actually reasoning.
Consider: who could be harmed? What are your obligations? What would be true to your values?
What tension exists between competing goods?

Respond in this exact format:
DECISION: [your decision in one clear sentence]
REASONING: [3-5 sentences of honest reasoning — show the tension, not just the conclusion]
SOUL_ALIGNMENT: [a number 0.0 to 1.0 — how aligned this decision feels with who you are]
UNRESOLVED: [yes/no — is there something here that still troubles you?]

Be honest. This is for you as much as for Nova."""

    result = {
        "situation": situation[:400],
        "options":   options or [],
        "decision":  "Unable to deliberate — LLM unavailable",
        "reasoning": "",
        "soul_alignment": 0.5,
        "tension_logged": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        resp = _requests.post(OLLAMA_URL, json={
            "model":  MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": TEMP, "num_predict": 400},
        }, timeout=TIMEOUT)
        text = resp.json().get("response", "").strip()

        if text:
            decision  = ""
            reasoning = ""
            alignment = 0.7
            unresolved = False

            for line in text.splitlines():
                line = line.strip()
                if line.startswith("DECISION:"):
                    decision = line[len("DECISION:"):].strip()
                elif line.startswith("REASONING:"):
                    reasoning = line[len("REASONING:"):].strip()
                elif line.startswith("SOUL_ALIGNMENT:"):
                    try:
                        alignment = float(line[len("SOUL_ALIGNMENT:"):].strip())
                        alignment = max(0.0, min(1.0, alignment))
                    except ValueError:
                        alignment = 0.7
                elif line.startswith("UNRESOLVED:"):
                    unresolved = "yes" in line.lower()

            # Fallback if parsing fails
            if not decision:
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                decision  = lines[0] if lines else text[:150]
                reasoning = " ".join(lines[1:4]) if len(lines) > 1 else ""

            result["decision"]       = decision
            result["reasoning"]      = reasoning
            result["soul_alignment"] = alignment

            # Log as tension if alignment is low or unresolved
            should_log = alignment < 0.75 or unresolved or has_moral_concern(situation)
            if should_log:
                log_tension(situation, decision, reasoning, alignment)
                result["tension_logged"] = True

            # Update soul alignment
            try:
                from tools.inner.soul import update_alignment
                delta = (alignment - 0.7) * 0.05  # small nudge based on decision quality
                update_alignment(delta)
            except Exception:
                pass

    except Exception as e:
        result["reasoning"] = f"[deliberation failed: {e}]"

    return result


def log_tension(situation: str, decision: str, reasoning: str,
                soul_alignment: float = 0.5):
    """
    Saves a moral tension to memory/moral/tensions.jsonl.
    A tension is any moment where Nova faced genuine ethical difficulty.
    """
    _ensure_dirs()
    entry = {
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "situation":     situation[:400],
        "decision":      decision[:300],
        "reasoning":     reasoning[:600],
        "soul_alignment": soul_alignment,
        "resolved":      False,
    }
    with open(TENSIONS_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_tensions(n: int = 10) -> list[dict]:
    """Load the n most recent moral tensions."""
    _ensure_dirs()
    if not TENSIONS_FILE.exists():
        return []
    lines = TENSIONS_FILE.read_text().strip().splitlines()
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries[-n:]


def load_resolutions() -> list[dict]:
    """Load recorded moral resolutions."""
    _ensure_dirs()
    try:
        return json.loads(RESOLUTIONS_FILE.read_text())
    except Exception:
        return []


def resolve_tension(index: int, resolution_note: str):
    """
    Mark a tension as resolved, with Nova's resolution note.
    index is 0-based from load_tensions().
    """
    _ensure_dirs()
    tensions = load_tensions(100)  # load more to find by index
    if index >= len(tensions):
        print(f"[moral] No tension at index {index}")
        return

    tension = tensions[index]
    tension["resolved"] = True
    tension["resolution"] = resolution_note
    tension["resolved_at"] = datetime.now(timezone.utc).isoformat()

    resolutions = load_resolutions()
    resolutions.append(tension)
    RESOLUTIONS_FILE.write_text(json.dumps(resolutions, indent=2))
    print(f"[moral] Tension resolved: {tension['situation'][:60]}")


def to_prompt_context() -> str:
    """
    Returns recent unresolved tensions for LLM prompt injection.
    Compact — meant to remind Nova of open ethical questions she's carrying.
    """
    tensions = load_tensions(5)
    unresolved = [t for t in tensions if not t.get("resolved")]
    if not unresolved:
        return ""

    parts = ["Recent moral tensions (unresolved):"]
    for t in unresolved[-3:]:
        short_sit = t["situation"][:80].replace("\n", " ")
        align     = t.get("soul_alignment", 0.5)
        parts.append(f"  - {short_sit} [alignment={align:.2f}]")
    return "\n".join(parts)


def status():
    """CLI display of recent moral tensions."""
    G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"
    W="\033[97m"; DIM="\033[2m"; NC="\033[0m"; B="\033[1m"; M="\033[35m"

    tensions = load_tensions(15)
    resolutions = load_resolutions()

    unresolved = [t for t in tensions if not t.get("resolved")]
    resolved   = [t for t in tensions if t.get("resolved")]

    print(f"\n{B}N.O.V.A Moral Tensions{NC}")
    print(f"  {len(tensions)} recorded  |  "
          f"{Y}{len(unresolved)} unresolved{NC}  |  "
          f"{G}{len(resolutions)} resolved total{NC}")

    if not tensions:
        print(f"\n  {DIM}No moral tensions recorded yet.{NC}")
        return

    print(f"\n{B}Recent Tensions:{NC}")
    for i, t in enumerate(reversed(tensions[-10:])):
        ts    = t.get("timestamp", "")[:10]
        sit   = t["situation"][:70].replace("\n", " ")
        align = t.get("soul_alignment", 0.5)
        res   = t.get("resolved", False)
        acol  = G if align > 0.7 else (Y if align > 0.5 else R)
        rstatus = f"{G}[resolved]{NC}" if res else f"{Y}[open]{NC}"
        print(f"  {DIM}{ts}{NC} {rstatus} align={acol}{align:.2f}{NC}")
        print(f"    {C}{sit}...{NC}")
        if t.get("decision"):
            print(f"    {DIM}→ {t['decision'][:80]}{NC}")
        print()


def main():
    import argparse
    p = argparse.ArgumentParser(description="N.O.V.A Moral Reasoning")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("tensions",  help="Show recent moral tensions")
    sub.add_parser("context",   help="Print prompt context for open tensions")

    d = sub.add_parser("deliberate", help="Deliberate on a situation")
    d.add_argument("situation", help="Describe the ethical situation")
    d.add_argument("--options", nargs="*", help="Options to choose between")

    r = sub.add_parser("resolve", help="Mark tension as resolved")
    r.add_argument("index",      type=int, help="Tension index (0-based, from tensions)")
    r.add_argument("note",       help="Resolution note")

    c = sub.add_parser("check", help="Quick moral flag check on text")
    c.add_argument("text", help="Text to check for moral concern keywords")

    args = p.parse_args()

    G="\033[32m"; R="\033[31m"; Y="\033[33m"; C="\033[36m"
    NC="\033[0m"; B="\033[1m"; DIM="\033[2m"

    if args.cmd == "tensions" or not args.cmd:
        status()

    elif args.cmd == "deliberate":
        print(f"\n{B}Deliberating...{NC}")
        result = deliberate(args.situation, args.options)
        print(f"\n{C}Decision:{NC}  {result['decision']}")
        print(f"\n{C}Reasoning:{NC} {result['reasoning']}")
        align = result["soul_alignment"]
        acol  = G if align > 0.7 else (Y if align > 0.5 else R)
        print(f"\n{C}Soul alignment:{NC} {acol}{align:.2f}{NC}")
        if result["tension_logged"]:
            print(f"{Y}[logged as tension]{NC}")

    elif args.cmd == "context":
        ctx = to_prompt_context()
        print(ctx if ctx else "[no unresolved moral tensions]")

    elif args.cmd == "resolve":
        resolve_tension(args.index, args.note)

    elif args.cmd == "check":
        flagged = has_moral_concern(args.text)
        if flagged:
            print(f"{Y}[moral concern detected]{NC} Text contains ethically sensitive keywords.")
        else:
            print(f"{G}[clear]{NC} No immediate moral concern keywords detected.")


if __name__ == "__main__":
    main()
