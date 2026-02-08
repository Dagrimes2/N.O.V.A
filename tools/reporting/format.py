#!/usr/bin/env python3
import json
import yaml
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
CORE = BASE / "core"
REPORTS = BASE / "reports"

def load_active():
    with open(CORE / "active_program.yaml") as f:
        return yaml.safe_load(f)["platform"]

def hackerone_fmt(r):
    return f"""
## Summary
{r['note']}

## Steps to Reproduce
{chr(10).join(r['markdown'].split("**Proof of Concept:**")[1].strip().splitlines())}

## Impact
An attacker may exploit this endpoint to bypass intended access controls, potentially leading to unauthorized data access or privilege escalation.

## Affected Endpoint
`{r['host']}{r['path']}`
""".strip()

def bugcrowd_fmt(r):
    return f"""
### Description
{r['note']}

### Proof of Concept
{chr(10).join(r['markdown'].split("**Proof of Concept:**")[1].strip().splitlines())}

### Impact
This issue could allow unintended behavior including unauthorized access or logic abuse.

### Endpoint
`{r['host']}{r['path']}`
""".strip()

def main():
    platform = load_active()
    outdir = REPORTS / platform
    outdir.mkdir(exist_ok=True)

    for line in sys.stdin:
        r = json.loads(line)
        name = f"{r['host'].replace('.', '_')}{r['path'].replace('/', '_')}.md"

        if platform == "hackerone":
            content = hackerone_fmt(r)
        else:
            content = bugcrowd_fmt(r)

        with open(outdir / name, "w") as f:
            f.write(content)

        print(f"[+] {platform.upper()} report written:", outdir / name)

if __name__ == "__main__":
    main()
