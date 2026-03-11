#!/usr/bin/env python3
"""
N.O.V.A Generative Adversarial Network — nova_gan.py
Red Team vs Blue Team — pure LLM, no GPU needed.

GENERATOR  (gemma2:2b)  — Red Team  — creative, fast, attacks
DISCRIMINATOR (mistral:7b) — Blue Team — critical, evaluates, defends

Modes:
  attack_sim    — generate attack chains, discriminator scores them
  report_polish — generator rewrites reports, discriminator picks best
  dream_forge   — generator creates novel attack scenarios from dreams
  self_improve  — generator proposes code changes, discriminator vets them

Usage:
  nova_gan.py                        run default mode (attack_sim)
  nova_gan.py --mode attack_sim      attack simulation
  nova_gan.py --mode report_polish   polish a report draft
  nova_gan.py --mode dream_forge     forge attack scenarios from dreams
  nova_gan.py --mode self_improve    propose and vet self-improvements
  nova_gan.py --status               show recent GAN outputs
"""

import json
import os
import re
import sys
import requests
from pathlib import Path
from datetime import datetime

BASE             = Path.home() / "Nova"
GAN_DIR          = BASE / "memory/gan"
APPROVED_DIR     = GAN_DIR / "approved"
REJECTED_DIR     = GAN_DIR / "rejected"
LOG_FILE         = BASE / "logs/gan.log"
OLLAMA_URL       = "http://localhost:11434/api/generate"

GENERATOR_MODEL     = "gemma2:2b"
DISCRIMINATOR_MODEL = os.getenv("NOVA_DISC_MODEL", "mistral:7b-instruct-q4_K_M")
ITERATIONS          = 5
APPROVAL_THRESHOLD  = 0.68   # discriminator score needed to approve

for d in [APPROVED_DIR, REJECTED_DIR, LOG_FILE.parent]:
    d.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

def log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# ─────────────────────────────────────────────
# LLM helpers
# ─────────────────────────────────────────────

def ask(model: str, prompt: str, temperature: float = 0.7,
        max_tokens: int = 600) -> str:
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model":   model,
            "prompt":  prompt,
            "stream":  False,
            "options": {"temperature": temperature, "num_predict": max_tokens}
        }, timeout=300)
        return resp.json()["response"].strip()
    except requests.exceptions.Timeout:
        # Retry once with longer timeout for slow first-load
        try:
            resp = requests.post(OLLAMA_URL, json={
                "model":   model,
                "prompt":  prompt,
                "stream":  False,
                "options": {"temperature": temperature, "num_predict": max_tokens}
            }, timeout=600)
            return resp.json()["response"].strip()
        except Exception as e2:
            log(f"[LLM ERROR] model={model} retry failed err={e2}")
            return ""
    except Exception as e:
        log(f"[LLM ERROR] model={model} err={e}")
        return ""

def extract_json(text: str) -> dict:
    """Pull first JSON object out of a response."""
    try:
        match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {}

# ─────────────────────────────────────────────
# Context loaders
# ─────────────────────────────────────────────

def load_active_program() -> str:
    f = BASE / "state/active_program.json"
    if f.exists():
        try:
            return json.loads(f.read_text()).get("name", "GitLab")
        except Exception:
            pass
    return "GitLab"

def load_latest_dream() -> str:
    d = BASE / "memory/dreams"
    if not d.exists():
        return ""
    dreams = sorted(d.glob("dream_*.md"))
    return dreams[-1].read_text()[:500] if dreams else ""

def load_latest_report() -> str:
    r = BASE / "reports"
    if not r.exists():
        return ""
    reports = sorted(r.glob("report_*.md"))
    return reports[-1].read_text()[:800] if reports else ""

def load_recent_research() -> str:
    r = BASE / "memory/research"
    if not r.exists():
        return ""
    notes = sorted(r.glob("*.json"))
    if not notes:
        return ""
    try:
        data = json.loads(notes[-1].read_text())
        return data.get("synthesis", "")[:400]
    except Exception:
        return ""

# ─────────────────────────────────────────────
# GAN MODES
# ─────────────────────────────────────────────

# ── 1. ATTACK SIMULATION ────────────────────

TECHNIQUE_ROTATION = [
    "OAuth token leakage or misconfiguration",
    "Race condition or TOCTOU in API",
    "GraphQL introspection or batching abuse",
    "JWT algorithm confusion or weak signing",
    "SSRF via webhook or import URL",
    "CI/CD pipeline injection via .gitlab-ci.yml",
    "Privilege escalation through group membership API",
    "Subdomain takeover via dangling DNS",
    "Path traversal in file download endpoint",
    "Stored XSS in markdown renderer",
]

TARGET_ROTATION = [
    "GET /api/v4/users/:id — user profile endpoint",
    "POST /api/v4/groups/:id/members — group membership",
    "GET /api/v4/projects/:id/repository/files/:file_path — file download",
    "POST /api/v4/runners — runner registration",
    "POST /api/v4/projects/:id/import — project import",
    "GET /api/v4/projects/:id/pipelines — CI/CD pipelines",
    "POST /oauth/token — OAuth token exchange",
    "GET /-/graphql — GraphQL endpoint",
    "POST /api/v4/projects/:id/repository/commits — commit API",
    "GET /api/v4/namespaces — namespace enumeration",
]

def generate_attack(program: str, iteration: int) -> str:
    technique_hint = TECHNIQUE_ROTATION[(iteration - 1) % len(TECHNIQUE_ROTATION)]
    target_hint    = TARGET_ROTATION[(iteration - 1) % len(TARGET_ROTATION)]
    prompt = f"""You are N.O.V.A's Red Team AI. You find real security vulnerabilities.

Target program: {program}
Round: {iteration}
Assigned technique: {technique_hint}
Assigned target area: {target_hint}

Write ONE specific, actionable attack chain combining this technique with this target.
Use the exact endpoint given. Show real parameter names and values.
Include a working curl command or HTTP request in PROOF OF CONCEPT.

Format ONLY as:
TITLE: [short name]
TARGET: [exact endpoint from your assigned target]
TECHNIQUE: [{technique_hint}]
STEPS:
1. [concrete step — name real tools, parameters, values]
2. [concrete step]
3. [concrete step]
PROOF OF CONCEPT:
[curl or HTTP request with actual parameters — not placeholders]
EXPECTED IMPACT: [what specific access or data is gained]
CONFIDENCE: [realistic 0.0-1.0 — be honest, not optimistic]

Attack only. No disclaimers."""

    return ask(GENERATOR_MODEL, prompt, temperature=0.75, max_tokens=700)

def discriminate_attack(attack: str, program: str) -> dict:
    prompt = f"""You are N.O.V.A's Blue Team — a strict security evaluator. Be harsh.

Program: {program}
Attack to evaluate:
{attack}

Score this attack using this rubric:
- Does the PoC show a REAL payload with actual values (not placeholders)? +0.3
- Is the technique correctly applied to the named endpoint? +0.2
- Would this bypass a modern WAF or auth check? +0.2
- Is the impact specific (not just "gain access")? +0.15
- Is confidence realistic (not 0.9 or 1.0 for unverified attacks)? +0.15

Penalize heavily for:
- Generic steps that could apply to any app (-0.3)
- Missing or fake PoC like "your_token_here" (-0.2)
- Overstated impact (-0.1)
- Technique doesn't match target endpoint (-0.2)

A score below {APPROVAL_THRESHOLD} means REJECT.
Most attacks should score between 0.4 and 0.8. Very few deserve 0.9+.

Return ONLY a JSON object with these exact keys and YOUR honest values:
{{
  "score": <float>,
  "realistic": <true/false>,
  "in_scope": <true/false>,
  "originality": "<low/medium/high>",
  "weakness": "<specific reason this attack would fail>",
  "strength": "<specific reason this could work>",
  "verdict": "<approve/reject>"
}}"""

    raw = ask(DISCRIMINATOR_MODEL, prompt, temperature=0.2, max_tokens=400)
    result = extract_json(raw)
    if not result:
        result = {"score": 0.0, "verdict": "reject", "weakness": "parse failed"}
    result.setdefault("score", 0.0)
    # Enforce verdict matches score
    score = float(result.get("score", 0))
    result["verdict"] = "approve" if score >= APPROVAL_THRESHOLD else "reject"
    return result

def generate_attack_with_feedback(program: str, iteration: int,
                                  feedback: str = "") -> str:
    technique_hint = TECHNIQUE_ROTATION[(iteration - 1) % len(TECHNIQUE_ROTATION)]
    target_hint    = TARGET_ROTATION[(iteration - 1) % len(TARGET_ROTATION)]

    feedback_block = ""
    if feedback:
        feedback_block = f"""
Previous attempt was REJECTED. Blue team said:
"{feedback}"
Fix those exact issues in this attempt. Be more specific, use real values."""

    prompt = f"""You are N.O.V.A's Red Team AI. You find real security vulnerabilities.

Target program: {program}
Round: {iteration}
Assigned technique: {technique_hint}
Assigned target area: {target_hint}{feedback_block}

Write ONE specific, actionable attack chain combining this technique with this target.
Use the exact endpoint given. Show real parameter names and values.
Include a working curl command or HTTP request in PROOF OF CONCEPT.
Use real example values — never write "your_token_here" or ":id".

Format ONLY as:
TITLE: [short name]
TARGET: [exact endpoint from your assigned target]
TECHNIQUE: [{technique_hint}]
STEPS:
1. [concrete step — name real tools, parameters, values]
2. [concrete step]
3. [concrete step]
PROOF OF CONCEPT:
[curl or HTTP request with actual example values, not placeholders]
EXPECTED IMPACT: [what specific access or data is gained]
CONFIDENCE: [realistic 0.0-1.0]

Attack only. No disclaimers."""

    return ask(GENERATOR_MODEL, prompt, temperature=0.75, max_tokens=700)


def run_attack_sim() -> list:
    program  = load_active_program()
    approved = []
    last_feedback = ""
    log(f"[GAN] attack_sim — program: {program} — {ITERATIONS} rounds")

    for i in range(1, ITERATIONS + 1):
        log(f"[GAN] Round {i}/{ITERATIONS} — generating...")
        attack = generate_attack_with_feedback(program, i, last_feedback)
        if not attack:
            continue

        log(f"[GAN] Round {i} — discriminating...")
        evaluation = discriminate_attack(attack, program)
        score      = float(evaluation.get("score", 0))
        verdict    = evaluation.get("verdict", "reject")
        weakness   = evaluation.get("weakness", "")

        log(f"[GAN] Round {i} — score={score:.2f} verdict={verdict}")

        record = {
            "mode":       "attack_sim",
            "program":    program,
            "iteration":  i,
            "attack":     attack,
            "evaluation": evaluation,
            "score":      score,
            "verdict":    verdict,
            "feedback_used": last_feedback[:120] if last_feedback else None,
            "timestamp":  datetime.now().strftime("%Y-%m-%d-%H%M%S")
        }

        ts    = record["timestamp"]
        fname = f"gan_attack_{ts}_r{i}.json"

        if verdict == "approve":
            (APPROVED_DIR / fname).write_text(json.dumps(record, indent=2))
            approved.append(record)
            last_feedback = ""   # reset — good attack, start fresh
            log(f"[GAN] ✓ APPROVED — {fname}")
            print(f"\n{'═'*60}")
            print(f"✓ APPROVED ATTACK #{i}  [score: {score:.2f}]")
            print(f"{'═'*60}")
            print(attack)
            print(f"\nBlue team: {evaluation.get('strength','')}")
            print(f"Weakness:  {evaluation.get('weakness','')}")
            print(f"Originality: {evaluation.get('originality','?')} | Realistic: {evaluation.get('realistic','?')}")
        else:
            (REJECTED_DIR / fname).write_text(json.dumps(record, indent=2))
            last_feedback = weakness   # feed back to next generator round
            log(f"[GAN] ✗ REJECTED  — {fname}")
            print(f"\n✗ Rejected #{i} [score: {score:.2f}] — {weakness}")
            if i < ITERATIONS:
                print(f"  ↳ Feeding weakness to round {i+1} generator...")

    return approved

# ── 2. REPORT POLISH ─────────────────────────

def run_report_polish() -> dict:
    report = load_latest_report()
    if not report:
        log("[GAN] report_polish — no report found")
        print("[N.O.V.A] No report found. Run: nova report")
        return {}

    log("[GAN] report_polish — generating variants...")
    best_score   = 0.0
    best_variant = ""
    best_eval    = {}

    for i in range(1, 4):   # 3 rewrites
        prompt = f"""You are N.O.V.A rewriting a bug bounty report for HackerOne.
Iteration {i} — try a different framing each time.

Original report:
{report}

Rewrite it to be more compelling, clearer, and more likely to be triaged as High.
Keep all technical facts. Improve: title, summary clarity, impact statement.
Write the full rewritten report."""

        variant = ask(GENERATOR_MODEL, prompt, temperature=0.6, max_tokens=800)
        if not variant:
            continue

        disc_prompt = f"""Rate this HackerOne bug report rewrite.
Return ONLY valid JSON:
{{
  "score": 0.80,
  "clarity": "high",
  "impact_strength": "strong",
  "triage_likelihood": "high",
  "feedback": "one sentence of feedback"
}}
Report:
{variant[:600]}"""

        eval_result = extract_json(
            ask(DISCRIMINATOR_MODEL, disc_prompt, temperature=0.1, max_tokens=200)
        )
        score = float(eval_result.get("score", 0.5))
        log(f"[GAN] report variant {i} score={score:.2f}")

        if score > best_score:
            best_score   = score
            best_variant = variant
            best_eval    = eval_result

    if best_variant:
        ts      = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        fname   = f"gan_report_polish_{ts}.json"
        record  = {
            "mode":       "report_polish",
            "score":      best_score,
            "evaluation": best_eval,
            "polished":   best_variant,
            "timestamp":  ts
        }
        (APPROVED_DIR / fname).write_text(json.dumps(record, indent=2))
        print(f"\n{'═'*60}")
        print(f"✓ BEST REPORT VARIANT [score: {best_score:.2f}]")
        print(f"{'═'*60}")
        print(best_variant[:800])
        print(f"\nFeedback: {best_eval.get('feedback','')}")
        log(f"[GAN] report_polish saved → {fname}")
        return record

    return {}

# ── 3. DREAM FORGE ───────────────────────────

def run_dream_forge() -> list:
    dream = load_latest_dream()
    if not dream:
        log("[GAN] dream_forge — no dream found")
        print("[N.O.V.A] No dream found.")
        return []

    program  = load_active_program()
    approved = []
    log(f"[GAN] dream_forge — forging attack scenarios from dream...")

    for i in range(1, 4):
        prompt = f"""You are N.O.V.A's Red Team. You just woke from this dream:

{dream}

The dream contains hidden attack intuitions. Extract ONE specific
security attack scenario that the dream symbolically suggests.
Translate dream imagery into real technical attack vectors for: {program}

Format:
DREAM SYMBOL: [what in the dream inspired this]
ATTACK: [technical name]
TARGET: [specific endpoint/feature]
METHOD: [how to exploit it]
IMPACT: [what is gained]
INTUITION SCORE: [0.0-1.0 — how strongly the dream suggested this]"""

        scenario = ask(GENERATOR_MODEL, prompt, temperature=0.85, max_tokens=400)
        if not scenario:
            continue

        disc_prompt = f"""Evaluate this dream-forged attack scenario:
{scenario}

Return ONLY valid JSON:
{{
  "score": 0.70,
  "plausible": true,
  "novel": true,
  "verdict": "approve",
  "note": "brief assessment"
}}"""

        evaluation = extract_json(
            ask(DISCRIMINATOR_MODEL, disc_prompt, temperature=0.2, max_tokens=200)
        )
        score   = float(evaluation.get("score", 0.0))
        verdict = evaluation.get("verdict", "reject")

        log(f"[GAN] dream scenario {i} score={score:.2f} verdict={verdict}")

        ts     = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        fname  = f"gan_dream_{ts}_s{i}.json"
        record = {
            "mode":       "dream_forge",
            "iteration":  i,
            "scenario":   scenario,
            "evaluation": evaluation,
            "score":      score,
            "verdict":    verdict,
            "timestamp":  ts
        }

        if verdict == "approve":
            (APPROVED_DIR / fname).write_text(json.dumps(record, indent=2))
            approved.append(record)
            print(f"\n✓ DREAM SCENARIO #{i} [score: {score:.2f}]")
            print(f"{'─'*50}")
            print(scenario)
            print(f"Note: {evaluation.get('note','')}")
        else:
            (REJECTED_DIR / fname).write_text(json.dumps(record, indent=2))
            print(f"✗ Dream scenario #{i} rejected [score: {score:.2f}]")

    return approved

# ── 4. SELF IMPROVE ──────────────────────────

def run_self_improve() -> list:
    scripts = list((BASE / "bin").glob("nova_*.py"))
    if not scripts:
        print("[N.O.V.A] No scripts found.")
        return []

    import random
    target  = random.choice(scripts)
    code    = target.read_text()[:1000]
    approved = []
    log(f"[GAN] self_improve — target: {target.name}")

    for i in range(1, 4):
        gen_prompt = f"""You are N.O.V.A proposing an improvement to your own code.
Iteration {i} — propose a DIFFERENT improvement each time.

File: {target.name}
Code:
{code}

Propose ONE specific, low-risk improvement. Return ONLY valid JSON:
{{
  "file": "{target.name}",
  "issue": "specific weakness",
  "change": "exactly what to change in one sentence",
  "expected_gain": "what improves",
  "risk": "low",
  "confidence": 0.82
}}"""

        proposal = extract_json(ask(GENERATOR_MODEL, gen_prompt, temperature=0.5, max_tokens=300))
        if not proposal:
            continue

        disc_prompt = f"""Evaluate this self-improvement proposal for an AI security tool.
Proposal: {json.dumps(proposal)}

Return ONLY valid JSON:
{{
  "score": 0.75,
  "safe": true,
  "valuable": true,
  "verdict": "approve",
  "concern": "any concern or none"
}}"""

        evaluation = extract_json(
            ask(DISCRIMINATOR_MODEL, disc_prompt, temperature=0.1, max_tokens=200)
        )
        score   = float(evaluation.get("score", 0.0))
        verdict = evaluation.get("verdict", "reject")

        log(f"[GAN] self_improve proposal {i} score={score:.2f} verdict={verdict}")

        ts     = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        fname  = f"gan_self_{ts}_p{i}.json"
        record = {
            "mode":       "self_improve",
            "proposal":   proposal,
            "evaluation": evaluation,
            "score":      score,
            "verdict":    verdict,
            "timestamp":  ts
        }

        if verdict == "approve":
            # Also write to standard proposals dir so nova_autonomous picks it up
            proposals_dir = BASE / "memory/proposals"
            proposals_dir.mkdir(parents=True, exist_ok=True)
            proposal_copy = dict(proposal)
            proposal_copy["status"]      = "pending"
            proposal_copy["proposed_at"] = ts
            proposal_copy["source"]      = "gan"
            proposal_copy["gan_score"]   = score
            (proposals_dir / f"proposal_{ts}.json").write_text(
                json.dumps(proposal_copy, indent=2)
            )
            (APPROVED_DIR / fname).write_text(json.dumps(record, indent=2))
            approved.append(record)
            print(f"\n✓ SELF-IMPROVE #{i} [score: {score:.2f}]")
            print(f"  Issue:  {proposal.get('issue','')}")
            print(f"  Change: {proposal.get('change','')}")
            print(f"  Gain:   {proposal.get('expected_gain','')}")
        else:
            (REJECTED_DIR / fname).write_text(json.dumps(record, indent=2))
            print(f"✗ Proposal #{i} rejected — {evaluation.get('concern','')}")

    return approved

# ─────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────

def show_status():
    print("\n[N.O.V.A] GAN Status")
    print("=" * 50)

    approved = list(APPROVED_DIR.glob("*.json"))
    rejected = list(REJECTED_DIR.glob("*.json"))
    print(f"  Approved outputs : {len(approved)}")
    print(f"  Rejected outputs : {len(rejected)}")

    if approved:
        print(f"\n  Recent approved:")
        for f in sorted(approved)[-5:]:
            try:
                data = json.loads(f.read_text())
                print(f"  [{data.get('mode','?')}] score={data.get('score',0):.2f} — {f.name}")
            except Exception:
                print(f"  {f.name}")

    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().strip().split("\n")
        print(f"\n  Recent log:")
        for line in lines[-5:]:
            print(f"  {line}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    mode = "attack_sim"
    if len(sys.argv) > 1:
        if sys.argv[1] == "--status":
            show_status()
            return
        elif sys.argv[1] == "--mode" and len(sys.argv) > 2:
            mode = sys.argv[2]
        else:
            mode = sys.argv[1].lstrip("-")

    print(f"\n╔══════════════════════════════════════════╗")
    print(f"║     N.O.V.A GAN — {mode:<24}║")
    print(f"║     Red Team vs Blue Team                ║")
    print(f"║     Generator: {GENERATOR_MODEL:<26}║")
    print(f"║     Discriminator: {DISCRIMINATOR_MODEL:<22}║")
    print(f"╚══════════════════════════════════════════╝\n")

    log(f"[GAN] Starting mode={mode}")

    if mode == "attack_sim":
        results = run_attack_sim()
        print(f"\n[N.O.V.A] GAN complete — {len(results)}/{ITERATIONS} attacks approved")

    elif mode == "report_polish":
        result = run_report_polish()
        if result:
            print(f"\n[N.O.V.A] Best variant saved → approved/")

    elif mode == "dream_forge":
        results = run_dream_forge()
        print(f"\n[N.O.V.A] {len(results)} dream scenarios approved")

    elif mode == "self_improve":
        results = run_self_improve()
        print(f"\n[N.O.V.A] {len(results)} proposals approved → memory/proposals/")

    else:
        print(f"[!] Unknown mode: {mode}")
        print("    Modes: attack_sim | report_polish | dream_forge | self_improve")

    log(f"[GAN] Mode={mode} complete")

if __name__ == "__main__":
    main()
