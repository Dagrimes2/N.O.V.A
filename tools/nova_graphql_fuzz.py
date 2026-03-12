#!/usr/bin/env python3
"""
nova_graphql_fuzz.py — GraphQL mutation auth fuzzer for N.O.V.A
Pulls schema, attempts minimal mutations, classifies auth responses.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

BASE = Path.home() / "Nova"
LOG  = BASE / "logs" / "graphql_fuzz.log"
OUT  = BASE / "memory" / "graphql_findings.json"

TARGETS = {
    "gitlab": {
        "url": "https://gitlab.com/api/graphql",
        "pat_file": str(Path.home() / ".nova_gitlab_pat"),
    }
}

PERMISSION_MARKERS = [
    "you don't have permission",
    "you must be an admin",
    "not authorized",
    "access denied",
    "403",
]

BYPASS_MARKERS = [
    "resource is unavailable",
    "feature flag",
    "not found",
    "doesn't exist on type",
    "argument",
    "invalid value",
    "required",
]


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def graphql(url, query, token):
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", url,
         "-H", f"Authorization: Bearer {token}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"query": query})],
        capture_output=True, text=True, timeout=15
    )
    try:
        return json.loads(result.stdout)
    except Exception:
        return {}


def get_mutations(url, token):
    resp = graphql(url, "{ __type(name: \"Mutation\") { fields { name } } }", token)
    # Fall back to full schema search
    try:
        types = resp["data"]["__schema"]["types"]
        mutation = next((t for t in types if t["name"] == "Mutation"), None)
        if mutation and mutation.get("fields"):
            return [f["name"] for f in mutation["fields"]]
    except Exception:
        pass
    return []


def classify(resp):
    text = json.dumps(resp).lower()
    if not resp.get("errors") and resp.get("data"):
        data = resp["data"]
        for v in data.values():
            if v and isinstance(v, dict):
                errors = v.get("errors", [])
                if not errors:
                    return "SUCCESS"
                err = " ".join(errors).lower()
                if any(m in err for m in PERMISSION_MARKERS):
                    return "PERMISSION_DENIED"
                return "INNER_ERROR"
    if resp.get("errors"):
        errs = " ".join(e.get("message","") for e in resp["errors"]).lower()
        if any(m in errs for m in PERMISSION_MARKERS):
            return "PERMISSION_DENIED"
        if any(m in errs for m in BYPASS_MARKERS):
            return "AUTH_BYPASS_CANDIDATE"
    return "UNKNOWN"


def probe_mutation(url, token, name):
    # Minimal probe — just errors field
    query = f'mutation {{ {name}(input: {{}}) {{ errors }} }}'
    resp = graphql(url, query, token)
    classification = classify(resp)
    errors = []
    if resp.get("errors"):
        errors = [e.get("message","") for e in resp["errors"]]
    return classification, errors


def run(target_name="gitlab"):
    cfg = TARGETS[target_name]
    token = Path(cfg["pat_file"]).read_text().strip()
    url = cfg["url"]

    log(f"Starting GraphQL fuzz on {target_name} ({url})")

    mutations = get_mutations(url, token)
    if not mutations:
        # Use cached schema
        schema_file = Path("/tmp/gitlab_schema.json")
        if schema_file.exists():
            data = json.loads(schema_file.read_text())
            types = data["data"]["__schema"]["types"]
            mutation = next((t for t in types if t["name"] == "Mutation"), None)
            if mutation and mutation.get("fields"):
                mutations = [f["name"] for f in mutation["fields"]]

    log(f"Found {len(mutations)} mutations to probe")

    findings = {"bypasses": [], "successes": [], "timestamp": datetime.now(timezone.utc).isoformat()}

    for i, name in enumerate(mutations):
        classification, errors = probe_mutation(url, token, name)
        if classification in ("AUTH_BYPASS_CANDIDATE", "SUCCESS"):
            log(f"🔥 {classification}: {name} — {errors[:1]}")
            findings["bypasses" if classification == "AUTH_BYPASS_CANDIDATE" else "successes"].append({
                "mutation": name,
                "classification": classification,
                "errors": errors
            })
        else:
            if i % 20 == 0:
                log(f"[{i}/{len(mutations)}] scanning...")
        time.sleep(0.3)  # gentle rate limiting

    OUT.write_text(json.dumps(findings, indent=2))
    log(f"Done. Bypasses: {len(findings['bypasses'])}, Successes: {len(findings['successes'])}")
    log(f"Results saved to {OUT}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "gitlab"
    run(target)
