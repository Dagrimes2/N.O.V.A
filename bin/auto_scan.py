#!/usr/bin/env python3
"""
Nova Auto‑Scan Pipeline – Production Grade
- Parallel scanning with thread pool
- Deduplicates targets
- Converts recon files to proper JSONL
- Runs full reasoning pipeline
- Optionally generates platform‑ready reports
"""

import json
import subprocess
import time
import sys
import logging
import concurrent.futures
from pathlib import Path
from datetime import datetime

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "auto_scan.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

ACTIVE_PROGRAM = Path("state/active_program.json")
REPORTS_DIR = Path("reports")
PRIORITIZED_FILE = Path("prioritized.jsonl")
BRIEF_FILE = REPORTS_DIR / "operator_brief.md"
TEMP_JSONL = Path("/tmp/nova_recon.jsonl")   # temporary JSONL for pipeline

# Pipeline stages (all must accept JSONL on stdin)
PIPELINE = [
    "normalize.py",
    "tools/scoring/score.py",
    "tools/reasoning/hypothesize.py",
    "tools/reasoning/reflect.py",
    "tools/reasoning/meta_reason.py",
    "tools/memory/memory.py",
    "tools/operator/queue.py"
]

MAX_CONCURRENT_SCANS = 3      # be polite
SCAN_TIMEOUT = 600             # 10 minutes per domain
SCAN_DELAY = 2                  # seconds between scans (minimum, concurrency handles extra)

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def load_active_program():
    if not ACTIVE_PROGRAM.exists():
        logging.error("No active program found. Run 'nova program <name>' first.")
        sys.exit(1)
    with open(ACTIVE_PROGRAM) as f:
        return json.load(f)

def scan_domain(domain, mode="light"):
    """Run a single nova scan. Returns True on success."""
    logging.info(f"Scanning {domain} ({mode})")
    try:
        result = subprocess.run(
            ["nova", "-u", domain, f"--{mode}"],
            capture_output=True,
            text=True,
            timeout=SCAN_TIMEOUT
        )
        if result.returncode != 0:
            logging.error(f"Scan failed for {domain}: {result.stderr}")
            return False
        logging.info(f"Scan completed for {domain}")
        return True
    except subprocess.TimeoutExpired:
        logging.error(f"Timeout scanning {domain}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error scanning {domain}: {e}")
        return False

def build_jsonl_from_recon():
    """Read all *_recon.json files and write a proper JSONL file."""
    recon_files = list(REPORTS_DIR.glob("*_recon.json"))
    if not recon_files:
        logging.warning("No recon files found.")
        return False

    with open(TEMP_JSONL, "w") as out:
        for f in recon_files:
            try:
                data = json.loads(f.read_text())
                out.write(json.dumps(data) + "\n")
            except Exception as e:
                logging.error(f"Failed to parse {f}: {e}")
    logging.info(f"Built JSONL from {len(recon_files)} files: {TEMP_JSONL}")
    return True

def run_pipeline():
    """Run the entire post‑scan processing pipeline using TEMP_JSONL."""
    logging.info("Starting post‑scan pipeline")

    if not TEMP_JSONL.exists():
        logging.error("No JSONL input file.")
        return

    # ------------------------------------------------------------------
    # Step 1: Generate prioritized.jsonl (normalize + score)
    # ------------------------------------------------------------------
    logging.info("Generating prioritized.jsonl")
    with open(PRIORITIZED_FILE, "w") as pf:
        # cat TEMP_JSONL | normalize.py | score.py > prioritized.jsonl
        cat = subprocess.Popen(
            ["cat", str(TEMP_JSONL)],
            stdout=subprocess.PIPE
        )
        norm = subprocess.Popen(
            ["python", "normalize.py"],
            stdin=cat.stdout,
            stdout=subprocess.PIPE
        )
        cat.stdout.close()
        score = subprocess.Popen(
            ["python", "tools/scoring/score.py"],
            stdin=norm.stdout,
            stdout=pf
        )
        norm.stdout.close()
        score.wait()
        if score.returncode != 0:
            logging.error("score.py failed")
            return

    # ------------------------------------------------------------------
    # Step 2: Run the rest of the pipeline (hypothesize → queue)
    # ------------------------------------------------------------------
    logging.info("Running reasoning and queue pipeline")
    with open(PRIORITIZED_FILE) as inf:
        hypo = subprocess.Popen(
            ["python", "tools/reasoning/hypothesize.py"],
            stdin=inf,
            stdout=subprocess.PIPE
        )
        refl = subprocess.Popen(
            ["python", "tools/reasoning/reflect.py"],
            stdin=hypo.stdout,
            stdout=subprocess.PIPE
        )
        hypo.stdout.close()
        meta = subprocess.Popen(
            ["python", "tools/reasoning/meta_reason.py"],
            stdin=refl.stdout,
            stdout=subprocess.PIPE
        )
        refl.stdout.close()
        mem = subprocess.Popen(
            ["python", "tools/memory/memory.py"],
            stdin=meta.stdout,
            stdout=subprocess.PIPE
        )
        meta.stdout.close()
        with open(BRIEF_FILE, "w") as brief:
            queue = subprocess.Popen(
                ["python", "tools/operator/queue.py"],
                stdin=mem.stdout,
                stdout=brief
            )
            mem.stdout.close()
            queue.wait()
            if queue.returncode != 0:
                logging.error("queue.py failed")
                return

    logging.info("Pipeline completed successfully")

    # ------------------------------------------------------------------
    # Optional: Generate platform‑ready reports
    # ------------------------------------------------------------------
    # Uncomment when ready
    # subprocess.run(["python", "tools/reporting/assemble.py"], stdin=open(PRIORITIZED_FILE), check=True)
    # subprocess.run(["python", "tools/reporting/format.py"], stdin=open(PRIORITIZED_FILE), check=True)

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    logging.info("=== Auto‑scan started ===")
    program = load_active_program()
    targets = program.get("in_scope", [])
    if not targets:
        logging.warning("No in‑scope targets defined.")
        return

    # Deduplicate and clean wildcards
    unique_domains = set()
    for t in targets:
        domain = t.replace("*.", "").strip()
        if domain:
            unique_domains.add(domain)
    domains = list(unique_domains)
    logging.info(f"Targets after dedup: {domains}")

    # Parallel scanning with ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SCANS) as executor:
        future_to_domain = {
            executor.submit(scan_domain, domain, "light"): domain
            for domain in domains
        }
        for future in concurrent.futures.as_completed(future_to_domain):
            domain = future_to_domain[future]
            try:
                success = future.result()
                if not success:
                    logging.warning(f"Scan of {domain} reported failure.")
            except Exception as e:
                logging.error(f"Scan of {domain} generated exception: {e}")
            # Minimal delay between submissions (executor handles concurrency)
            time.sleep(SCAN_DELAY)

    # Build JSONL from recon files
    if not build_jsonl_from_recon():
        logging.error("No recon data to process.")
        return

    # Run pipeline
    run_pipeline()

    logging.info("=== Auto‑scan finished ===")

if __name__ == "__main__":
    main()
