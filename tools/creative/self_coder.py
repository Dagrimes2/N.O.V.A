#!/usr/bin/env python3
"""
N.O.V.A Self-Coder

Nova uses CodeLlama to write Python modules toward her own goals.
All code goes through syntax checking before being proposed.
Nothing is auto-executed — Travis reviews and approves via agency system.
"""
import json
import os
import py_compile
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE           = Path.home() / "Nova"
SELF_CODE_DIR  = BASE / "memory/self_code"
PROPOSALS_DIR  = SELF_CODE_DIR / "proposals"
LOG_FILE       = SELF_CODE_DIR / "log.jsonl"

_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from tools.config import cfg
    TIMEOUT = cfg.timeout("heavy")
except Exception:
    TIMEOUT = 300


# ── Internal helpers ──────────────────────────────────────────────────────────

def _append_log(entry: dict):
    SELF_CODE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _read_log() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    results = []
    for line in LOG_FILE.read_text().strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except Exception:
            pass
    return results


# ── Core pipeline ─────────────────────────────────────────────────────────────

def _write_code(spec: str, module_name: str) -> str:
    """
    Use CodeLlama to write a Python module from a spec description.
    Returns the generated code string.
    """
    try:
        from tools.llm.router import generate_code
    except Exception:
        return ""

    prompt = (
        f"Write a complete Python module for N.O.V.A called {module_name}.\n"
        f"The module should: {spec}\n\n"
        "Requirements:\n"
        "- Pure Python, no external dependencies beyond stdlib and existing Nova tools\n"
        "- Include module docstring\n"
        "- Include main() function with basic CLI\n"
        "- Follow Nova's module pattern:\n"
        "    BASE = Path.home() / 'Nova'\n"
        "    _nova_root = str(BASE)\n"
        "    if _nova_root not in sys.path: sys.path.insert(0, _nova_root)\n"
        "- Use Path from pathlib for all file paths\n"
        "- Include: #!/usr/bin/env python3 shebang\n"
        "- End with: if __name__ == '__main__': main()\n\n"
        "Write the complete module:"
    )
    return generate_code(prompt, language="python")


def _syntax_check(code: str) -> tuple[bool, str]:
    """
    Check Python syntax using py_compile.
    Returns (True, "") on success or (False, error_message) on failure.
    """
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp = f.name
        py_compile.compile(tmp, doraise=True)
        return True, ""
    except py_compile.PyCompileError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)
    finally:
        if tmp:
            try:
                Path(tmp).unlink()
            except Exception:
                pass


def _fix_code(code: str, error: str, spec: str) -> str:
    """
    Ask CodeLlama to fix a syntax error.
    Returns fixed code string (one retry attempt).
    """
    try:
        from tools.llm.router import generate_code
    except Exception:
        return code

    prompt = (
        f"The following Python module has a syntax error and must be fixed.\n\n"
        f"Error:\n{error}\n\n"
        f"Original spec: {spec[:200]}\n\n"
        f"Broken code:\n{code}\n\n"
        "Return ONLY the corrected, complete Python module with no explanation:"
    )
    fixed = generate_code(prompt, language="python")
    return fixed if fixed.strip() else code


# ── Public API ────────────────────────────────────────────────────────────────

def propose_module(
    spec: str,
    module_name: str,
    target_path: str = None,
) -> dict:
    """
    Full pipeline: write → check → fix if needed → save → propose via agency.
    target_path: where the module should go (e.g. "tools/inner/new_module.py")
                 defaults to "tools/creative/{module_name}.py"
    Returns {"ok": bool, "path": str, "proposal_id": str, "syntax_ok": bool}
    """
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

    ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = module_name.replace(" ", "_").lower()

    # Determine target path
    if target_path:
        dest = BASE / target_path
    else:
        dest = BASE / f"tools/creative/{safe_name}.py"

    # Write code
    code = _write_code(spec, module_name)
    if not code.strip():
        entry = {
            "ts":          ts,
            "module_name": module_name,
            "spec":        spec[:200],
            "ok":          False,
            "syntax_ok":   False,
            "proposal_id": "",
            "path":        str(dest),
            "error":       "LLM returned empty code",
        }
        _append_log(entry)
        return {"ok": False, "path": str(dest), "proposal_id": "", "syntax_ok": False}

    # Syntax check
    ok, err = _syntax_check(code)
    syntax_ok = ok

    if not ok:
        # One fix attempt
        code    = _fix_code(code, err, spec)
        ok, err = _syntax_check(code)
        syntax_ok = ok

    # Save proposal file regardless — Travis inspects it
    proposal_filename = f"{ts}_{safe_name}.py"
    proposal_file     = PROPOSALS_DIR / proposal_filename
    proposal_file.write_text(code, encoding="utf-8")

    # Agency proposal
    prop_id = ""
    try:
        from tools.operator.agency import propose_action
        prop_id = propose_action(
            action_type="write_file",
            description=(
                f"Self-coder proposes new module '{module_name}'. "
                f"Syntax {'OK' if syntax_ok else 'ERRORS PRESENT'}."
            ),
            target=str(dest),
            payload={
                "module_name":      module_name,
                "spec":             spec[:300],
                "proposal_file":    str(proposal_file),
                "syntax_ok":        syntax_ok,
            },
            reason=f"Nova self-generated this module to fulfil: {spec[:120]}",
        )
    except Exception as exc:
        prop_id = f"agency_error:{exc}"

    entry = {
        "ts":          ts,
        "module_name": module_name,
        "spec":        spec[:200],
        "ok":          syntax_ok,
        "syntax_ok":   syntax_ok,
        "proposal_id": prop_id,
        "path":        str(dest),
        "proposal_file": str(proposal_file),
    }
    _append_log(entry)

    return {
        "ok":          syntax_ok,
        "path":        str(dest),
        "proposal_id": prop_id,
        "syntax_ok":   syntax_ok,
    }


def generate_from_goal(goal_title: str) -> dict:
    """
    Given a goal title (from goals.py), auto-generate a spec and propose a module.
    Uses reasoning model to turn goal into a technical spec first,
    then calls propose_module().
    """
    try:
        from tools.llm.router import generate as llm_generate
        spec_prompt = (
            f"Convert this N.O.V.A goal into a precise technical specification "
            f"for a Python module.\n\n"
            f"Goal: {goal_title}\n\n"
            "Write a 2-4 sentence technical spec describing exactly what the module "
            "should do, what functions it needs, and what data it stores. "
            "Be specific and concrete. "
            "Output ONLY the spec text, no preamble:"
        )
        spec = llm_generate(spec_prompt, task_type="reasoning",
                             temperature=0.2, max_tokens=200)
    except Exception:
        spec = goal_title

    if not spec.strip():
        spec = goal_title

    # Derive a module name from the goal title
    module_name = (
        goal_title.lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )
    # Trim to reasonable length
    module_name = "_".join(module_name.split("_")[:5])

    return propose_module(spec, module_name)


def list_proposals() -> list[dict]:
    """List pending self-code proposals from memory/self_code/log.jsonl."""
    entries = _read_log()
    return [e for e in entries if not e.get("executed")]


def status() -> None:
    """Print recent coding sessions and proposals."""
    G = "\033[32m"; C = "\033[36m"; Y = "\033[33m"; R = "\033[31m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    entries = _read_log()
    print(f"\n{B}N.O.V.A Self-Coder{NC}")
    print(f"  Total sessions: {len(entries)}")

    if not entries:
        print(f"  {DIM}No coding sessions yet.{NC}\n")
        return

    # Count stats
    ok_count   = sum(1 for e in entries if e.get("syntax_ok"))
    fail_count = len(entries) - ok_count
    print(f"  {G}Syntax OK:{NC} {ok_count}   {R}Syntax errors:{NC} {fail_count}")

    recent = entries[-5:]
    print(f"\n  {B}Recent sessions:{NC}")
    for e in reversed(recent):
        ts    = e.get("ts", "?")[:15]
        name  = e.get("module_name", "?")
        ok    = e.get("syntax_ok", False)
        pid   = e.get("proposal_id", "")[:20]
        ok_s  = f"{G}OK{NC}" if ok else f"{R}FAIL{NC}"
        print(f"    {DIM}{ts}{NC}  {C}{name:<30}{NC}  {ok_s}  {DIM}{pid}{NC}")

    # Proposal files on disk
    if PROPOSALS_DIR.exists():
        files = sorted(PROPOSALS_DIR.glob("*.py"))
        print(f"\n  Proposal files on disk: {len(files)}")
    print()


def main():
    import argparse

    p   = argparse.ArgumentParser(description="N.O.V.A Self-Coder")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show recent sessions and proposals (default)")
    sub.add_parser("list",   help="List pending proposals")

    prp = sub.add_parser("propose", help='Propose a new module: propose "spec" MODULE_NAME')
    prp.add_argument("spec")
    prp.add_argument("module_name")
    prp.add_argument("--target", default=None,
                     help="Target path relative to Nova root, e.g. tools/inner/foo.py")

    gol = sub.add_parser("goal", help='Generate module from a goal title')
    gol.add_argument("title", nargs="+")

    args = p.parse_args()

    G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"
    DIM = "\033[2m"; NC = "\033[0m"; B = "\033[1m"

    if args.cmd in (None, "status"):
        status()

    elif args.cmd == "list":
        proposals = list_proposals()
        if not proposals:
            print(f"{DIM}No proposals on record.{NC}")
        else:
            print(f"\n{B}Self-code proposals ({len(proposals)}):{NC}")
            for e in proposals[-10:]:
                ts   = e.get("ts", "?")[:15]
                name = e.get("module_name", "?")
                ok   = e.get("syntax_ok", False)
                pid  = e.get("proposal_id", "")
                col  = G if ok else R
                print(f"\n  {DIM}{ts}{NC}  {col}{name}{NC}")
                print(f"    Spec:        {e.get('spec','')[:70]}")
                print(f"    Proposal ID: {DIM}{pid}{NC}")
                print(f"    File:        {DIM}{e.get('proposal_file','?')}{NC}")
        print()

    elif args.cmd == "propose":
        print(f"\nWriting module '{args.module_name}'...")
        result = propose_module(args.spec, args.module_name, args.target)
        if result["ok"]:
            print(f"{G}Proposed:{NC} {result['proposal_id']}")
            print(f"  Path:      {result['path']}")
            print(f"  Syntax OK: {G}yes{NC}")
        else:
            print(f"{R}Proposal created with syntax errors.{NC}")
            print(f"  Proposal ID: {result['proposal_id']}")
            print(f"  Path:        {result['path']}")
            print(f"  {Y}Review the proposal file before approving.{NC}")
        print()

    elif args.cmd == "goal":
        title = " ".join(args.title)
        print(f"\nGenerating module from goal: '{title}'...")
        result = generate_from_goal(title)
        col = G if result["ok"] else R
        print(f"{col}Done.{NC}  proposal_id={result['proposal_id']}")
        print(f"  Path: {result['path']}")
        print()


if __name__ == "__main__":
    main()
