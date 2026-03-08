# N.O.V.A
### Neural Ontology for Virtual Awareness
*An autonomous AI security research assistant built on a 2011 iMac with no cloud, no API keys, and no limits.*

---

## What N.O.V.A Is

N.O.V.A is a local AI-powered bug bounty workflow that thinks, remembers, and dreams.

She is not a chatbot. She is a pipeline — recon goes in, prioritized action items come out, and every night she consolidates what she learned into a strategic dream log for the next session.

Built and running on:
- **OS:** Athena OS (Arch-based)
- **Hardware:** iMac 2011, i7-2600, 19.5GB RAM
- **LLM:** gemma2:2b via Ollama — fully local, uncensored

---

## Architecture
```
nova CLI (recon)
    ↓
normalize.py       — standardizes data from any source
    ↓
score.py           — detects signals, calculates risk score
    ↓
hypothesize.py     — LLM generates security hypotheses
    ↓
reflect.py         — LLM decides: act / observe / hold / suppress
    ↓
meta_reason.py     — cross-finding pattern analysis
    ↓
memory.py          — persists findings to index.jsonl
    ↓
queue.py           — prints prioritized action list
```

Every night at 3am:
```
nova_dream.py      — LLM synthesizes memories into strategic log
                     → memory/dreams/dream_YYYY-MM-DD.md
```

---

## Core Concepts

**Perception** — `nova -u target.com --deep` probes HTTP surfaces and detects signals like `auth-path`, `error-403`, `method-post`

**Mind** — Local Ollama LLM (gemma2:2b) powers hypothesis generation and triage decisions. No data leaves your machine.

**Memory** — Every finding is stored in `memory/store/index.jsonl` and retrieved for context in future sessions

**Dreaming** — Nightly synthesis of accumulated findings into pattern analysis, blind spots, and tomorrow's priorities

**Governance** — `autonomy_guard.py` enforces scope, confidence thresholds, and audit logging. N.O.V.A never acts outside authorized targets.

---

## Quick Start
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma2:2b

# Install dependencies
pip install requests pyyaml --break-system-packages

# Set active program
nova program demo

# Run a scan
nova -u example.com --deep

# Run full AI pipeline
python3 -c "
import json
from pathlib import Path
r = list(Path('reports').glob('*_recon.json'))
with open('/tmp/nova_recon.jsonl','w') as f:
    for p in r:
        f.write(json.dumps(json.loads(p.read_text())) + '\n')
" && cat /tmp/nova_recon.jsonl \
  | python normalize.py \
  | python tools/scoring/score.py \
  | python tools/reasoning/hypothesize.py \
  | python tools/reasoning/reflect.py \
  | python tools/reasoning/meta_reason.py \
  | python tools/memory/memory.py \
  | python tools/operator/queue.py

# Run dream engine manually
python3 bin/nova_dream.py
cat memory/dreams/dream_$(date +%Y-%m-%d).md
```

---

## Crontab
```
PATH=/home/m4j1k/Nova/bin:/usr/local/bin:/usr/bin:/bin
0 2 * * * cd /home/m4j1k/Nova && /usr/bin/python3 bin/auto_scan.py >> logs/cron.log 2>&1
0 3 * * * cd /home/m4j1k/Nova && /usr/bin/python3 bin/nova_dream.py >> logs/dream.log 2>&1
```

---

## First Dream

> *"The recurring unauthorized access attempts on the admin page of example.com pose a significant threat... N.O.V.A, reporting for duty. Secure the System."*
> — N.O.V.A, 2026-03-07

---

## Roadmap

- [ ] Voice input/output — Whisper + Piper TTS  
- [ ] nova_identity.json — persistent self-model  
- [ ] Auto-draft HackerOne reports  
- [ ] Real program targets  
- [ ] Expand signal detection in score.py  

---

*Built by Travis (https://github.com/Dagrimes2) — March 2026*
