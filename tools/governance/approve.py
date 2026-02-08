#!/usr/bin/env python3

import yaml
import datetime
from pathlib import Path

APPROVAL_FILE = Path("core/approval.yaml")

def main():
    if not APPROVAL_FILE.exists():
        raise SystemExit("[!] approval.yaml missing")

    with open(APPROVAL_FILE) as f:
        data = yaml.safe_load(f) or {}

    data["approved"] = True
    data["approved_by"] = "Travis"
    data["approved_at"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    data["reason"] = "Manual approval after Nova recommendation"

    with open(APPROVAL_FILE, "w") as f:
        yaml.safe_dump(data, f)

    print("[+] Expansion approved by human operator")

if __name__ == "__main__":
    main()
