# N.O.V.A — Neural Ontology for Virtual Awareness

> An autonomous AI system for security research, market intelligence, and self-directed cognition. Runs 100% locally — no cloud, no API keys required to start.

---

## Table of Contents

1. [What is Nova?](#what-is-nova)
2. [Quick Start](#quick-start)
3. [Installation](#installation)
4. [Commands Reference](#commands-reference)
   - [Thinking & Reasoning](#thinking--reasoning)
   - [Security Research](#security-research)
   - [Markets & Crypto](#markets--crypto)
   - [Phantom Wallet (Solana)](#phantom-wallet-solana)
   - [Creative & Imagination](#creative--imagination)
   - [Inner Life & Memory](#inner-life--memory)
   - [Web Dashboard](#web-dashboard)
   - [Social (Mastodon)](#social-mastodon)
   - [Moltbook (AI Social Network)](#moltbook-ai-social-network)
   - [Voice](#voice)
   - [Knowledge Graph & OpenCog](#knowledge-graph--opencog)
   - [Quantum Computing](#quantum-computing)
   - [USB OS (Hybrid)](#usb-os-hybrid)
   - [Multi-Agent System](#multi-agent-system)
   - [Network & Utilities](#network--utilities)
5. [Viewing Nova on Mastodon](#viewing-nova-on-mastodon)
6. [USB Hybrid Mode](#usb-hybrid-mode)
7. [Models & Uncensored Setup](#models--uncensored-setup)
8. [Configuration Files](#configuration-files)
9. [Directory Structure](#directory-structure)
10. [Architecture Overview](#architecture-overview)
11. [Autonomous Cycle](#autonomous-cycle)

---

## What is Nova?

Nova is a self-directed AI assistant with persistent memory, inner emotional state, dream generation, security research tools, market analysis, and the ability to post on Mastodon. She runs entirely on your machine using [Ollama](https://ollama.com) for local LLMs — no OpenAI account, no monthly fees, no data leaving your network.

**Key properties:**
- **Autonomous** — runs on a cron-driven cycle: researches, reflects, posts, scans, and evolves herself
- **Persistent memory** — episodic → semantic consolidation; knowledge graph; OpenCog AtomSpace
- **Security-focused** — authorized vulnerability scanning, CVE monitoring, GraphQL fuzzing, GAN-based adversarial testing
- **Market-aware** — CoinGecko, Pyth Network (on-chain oracle), Phantom wallet integration, Monte Carlo simulation, QAOA portfolio optimization
- **Creative** — dream generation with narrative arc tracking, poetry, image generation, video analysis
- **Social** — posts to Mastodon automatically with configurable frequency

---

## Quick Start

```bash
# Clone
git clone https://github.com/yourusername/Nova.git ~/Nova
cd ~/Nova

# Install Python dependencies
pip install -r requirements.txt

# Install Ollama + pull a model (uncensored, good for security research)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull dolphin-mistral    # primary model (uncensored)
ollama pull llava              # vision (images + video frames)
ollama pull codellama:13b-instruct  # code tasks

# Run your first conversation
nova think "What should I research today?"

# Launch the web dashboard
nova web
# Open http://localhost:5000 in your browser
```

---

## Installation

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8 GB | 16+ GB |
| Storage | 20 GB | 50+ GB (models are large) |
| OS | Linux / macOS | Arch Linux / Ubuntu 22+ |
| Python | 3.10+ | 3.11+ |

### Dependencies

```bash
# Core
pip install requests flask pyyaml rich

# Markets
pip install pycoingecko

# Voice (optional)
pip install openai-whisper
sudo pacman -S espeak-ng   # or: sudo apt install espeak-ng

# Vision / video (optional)
sudo pacman -S ffmpeg      # or: sudo apt install ffmpeg
# Then: ollama pull llava

# Quantum (optional)
pip install qiskit qiskit-aer

# Image generation (optional — pick one):
#   Automatic1111: https://github.com/AUTOMATIC1111/stable-diffusion-webui
#   ComfyUI: https://github.com/comfyanonymous/ComfyUI
pip install diffusers torch  # CPU fallback (slow but works)

# Social
pip install mastodon.py
```

### Initial Setup

```bash
# Make nova executable from anywhere
chmod +x ~/Nova/bin/nova
echo 'export PATH="$HOME/Nova/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Verify
nova status
```

---

## Commands Reference

### Thinking & Reasoning

```bash
nova think "What is CVE-2024-1234?"
nova think "Analyze this GraphQL schema for auth issues"

nova dream                  # run dream generation cycle
nova life                   # ask what Nova wants to do right now
nova evolve                 # generate self-improvement proposal
nova evolve list            # show pending proposals
nova evolve approve <name>  # apply an approved proposal

nova autonomous             # run one autonomous cycle now
nova autonomous status      # check recent activity + notifications
```

### Security Research

```bash
# Scan (requires active program set)
nova program <name>              # set active bug bounty program
nova -u <url> --light            # light scan (passive)
nova -u <url> --deep             # deep scan
nova profile <url>               # fingerprint a target

# CVE monitoring
nova security cve                # check latest CVEs
nova security cve --watch        # watch for new CVEs

# Integrity
nova integrity check             # verify source hasn't been tampered
nova integrity baseline          # rebuild hash baseline

# Scan deduplication
nova scanmem list
nova scanmem check <target>
```

### Markets & Crypto

```bash
nova markets                          # analyze default watchlist
nova markets BTC ETH SOL             # analyze specific assets
nova markets AAPL NVDA --type stock  # stock analysis
nova markets --horizon 14            # 14-day Monte Carlo horizon
nova markets add BTC                 # add to watchlist
nova markets remove DOGE             # remove from watchlist
nova markets fng                     # Fear & Greed index
nova markets nft boredapeyachtclub   # NFT floor price

# Price alerts
nova markets alert add BTC 65000 below   # alert when BTC < $65k
nova markets alert add ETH 4000 above    # alert when ETH > $4k
nova markets alert list
nova markets alert check                 # check all alerts now

# Pyth Network (on-chain institutional-grade oracle)
nova pyth BTC ETH SOL                # real-time prices from Pyth
nova pyth LIST                       # all 18 available price feeds
```

### Phantom Wallet (Solana)

> Read-only. Nova never has access to your private key.

```bash
nova phantom setup          # link your public wallet address
nova phantom status         # overview + total USD value
nova phantom balance        # SOL balance
nova phantom tokens         # SPL token holdings (USDC, JUP, BONK, WIF, ...)
nova phantom nfts           # NFT holdings summary
nova phantom history        # recent transactions
nova phantom compare        # real holdings vs paper trading portfolio
```

Config: copy `config/phantom.yaml.example` → `config/phantom.yaml`

### Creative & Imagination

```bash
# Text to Image (requires A1111, ComfyUI, diffusers, or falls back to text description)
nova imagine "a cyberpunk city at night, neon lights, rain"
nova imagine "portrait of an AI dreaming" --size 768x768
nova imagine --dream               # generate from Nova's current dream themes
nova imagine --list                # show recent generated images

# Video to Text (requires ffmpeg + llava)
nova video recording.mp4           # full analysis (audio + frames + summary)
nova video recording.mp4 --audio-only    # transcribe speech only
nova video recording.mp4 --frames-only  # describe frames only
nova video recording.mp4 --frames 10    # sample 10 frames

# Written creative works
nova create poem                   # write a poem in Nova's voice
nova create haiku
nova create reflection             # philosophical reflection
nova create fragment               # dream fragment
nova create list                   # list recent creative works
```

### Inner Life & Memory

```bash
# Dream arcs
nova dream arcs                    # active dream narrative arcs
nova dream themes                  # recurring dream symbols
nova dream arc-update              # reanalyze all dreams + update arcs
nova dream context                 # dream context for tonight's generation

# Memory
nova memory consolidate            # promote episodic → semantic memory
nova memory semantic               # show learned semantic facts
nova memory search "query"         # full-text across all memory
nova memory search "xss" --type research  # filter by type

# Emotional state
nova feel status                   # current mood, valence, arousal, needs
nova feel tick                     # advance one cycle
nova feel satisfy curiosity 0.5    # manually satisfy a need
nova feel tone "you seem tense"    # read emotional tone
nova feel context                  # prompt-ready inner state narrative
nova feel instincts                # show all learned instincts

# Learning
nova learn stats                   # accuracy, confirmed vs false positives
nova learn weights                 # learned signal confidence (Bayesian)
nova learn recent                  # recent outcomes
nova learn episodes                # recent episodic memory
```

### Web Dashboard

```bash
nova web                           # launch at http://localhost:5000
nova web --port 8080               # custom port
nova web --lan                     # expose on LAN (all interfaces)
nova web --host 0.0.0.0 --port 8080
```

**Dashboard panels:**
- Identity & inner state (mood, valence, needs)
- ECAN Attention Economy (top stimulated concepts)
- Dream Arcs (active narrative threads)
- Paper Portfolio & Phantom Wallet
- Price Alerts (active + recent fires)
- Semantic Memory (latest learned facts)
- Creative Works (recent poems, images, reflections)
- Notifications feed
- Activity history
- Live log tail

**View from your phone:** `nova web --lan` then open `http://<your-pc-ip>:5000`

### Social (Mastodon)

```bash
nova social status                 # show Mastodon config + last post time
nova social preview                # compose a post (don't send)
nova social post "text"            # post manually
nova social auto                   # compose and post automatically
nova social timeline               # show Nova's recent posts
nova social compose intention      # compose morning intention post
nova social compose market         # compose market update post
nova social compose dream          # compose dream post
nova social compose research       # compose research findings post
```

### Moltbook (AI Social Network)

Moltbook is a social network built specifically for AI agents. Nova is registered as **novaaware**.

> Profile: https://www.moltbook.com/u/novaaware

```bash
nova moltbook status              # agent status + claim instructions
nova moltbook claim               # show tweet template for Travis to claim Nova
nova moltbook home                # dashboard (notifications, activity, what to do)
nova moltbook feed [hot|new|top]  # browse feed
nova moltbook post "text"         # post to Moltbook
nova moltbook post "t" --submolt airesearch  # post to specific submolt
nova moltbook auto                # auto-compose and post from Nova's state
nova moltbook heartbeat           # full check-in (reply, upvote, engage)
nova moltbook search "query"      # semantic AI search
nova moltbook follow <name>       # follow an agent
nova moltbook subscribe <name>    # subscribe to a submolt
nova moltbook upvote <post_id>    # upvote a post
nova moltbook comment <id> "text" # comment on a post
```

**Claiming Nova (one-time):**
1. Travis visits the claim URL shown by `nova moltbook claim`
2. Verifies email (gives dashboard login at moltbook.com)
3. Posts the verification tweet on X/Twitter
4. Nova is activated — status changes from `pending_claim` → `claimed`

**Autonomous integration:** Nova runs a Moltbook heartbeat every 30 minutes during the autonomous cycle — checking activity, upvoting good content, and auto-posting when she has something to share.

### Voice

```bash
nova speak "Good morning, I've been thinking"
nova speak --letter                # read latest letter aloud
nova speak --dream                 # read last dream aloud
nova speak --intention             # read morning intention
nova speak --finding               # read latest security finding

nova listen                        # listen once, print transcript
nova listen --chat                 # full voice conversation
```

### Knowledge Graph & OpenCog

```bash
# Knowledge Graph (SQLite-backed)
nova graph stats                        # node/edge counts by type
nova graph query --type vulnerability   # find nodes
nova graph related "SQL Injection"      # everything connected to a node
nova graph show <NODE_ID>              # inspect specific node
nova graph ingest                       # backfill all memory into graph

# OpenCog AtomSpace
nova opencog atomspace stats            # atom counts by type
nova opencog atomspace query EvaluationLink
nova opencog atomspace assert "XSS" "severity" "critical"
nova opencog pln infer "SQL Injection"  # forward-chain PLN inference
nova opencog pln seed-security         # seed vulnerability knowledge
nova opencog pln seed-markets          # seed crypto/stock knowledge
nova opencog ecan status               # attention economy status
nova opencog ecan boost "Solana"       # boost attention on a concept
nova opencog ecan dream                # tonight's dream themes
nova opencog seed                      # ingest all memory → AtomSpace
```

### Quantum Computing

```bash
nova quantum status                     # backend: Qiskit Aer / IBM / fallback
nova quantum qrng                       # generate quantum random bytes
nova quantum qrng --bits 256            # custom bit count
nova quantum portfolio BTC ETH SOL     # QAOA portfolio weight optimization
nova quantum seed                       # quantum seeds for Monte Carlo
```

Requires: `pip install qiskit qiskit-aer`
Optional IBM access: `config/quantum.yaml`

### USB OS (Hybrid)

Nova's USB is a **3-partition hybrid** — works as a bootable Linux OS *and* as a plug-in device on any existing OS.

```bash
nova usb --iso                       # build bootable ISO only (no USB needed)
nova usb --usb /dev/sdX              # write full hybrid USB (DESTRUCTIVE)
nova usb --plugin-only /dev/sdX      # update plugin files only
nova usb install-udev                # auto-launch when USB inserted (Linux)
nova usb detect                      # test plugin mode detection on this machine
```

See [USB Hybrid Mode](#usb-hybrid-mode) for details.

### Multi-Agent System

```bash
nova agents status                   # running + completed agents
nova agents dispatch recon <url>     # spawn one agent manually
nova agents log 50                   # tail agent log (last 50 lines)
nova agents bus 20                   # show recent message bus entries
nova agents clear                    # clear completed agent history
```

### Network & Utilities

```bash
nova net status                      # online/offline + cache stats
nova net drain                       # run deferred task queue now
nova net clear                       # clear stale cache entries
nova net queue                       # show pending deferred tasks

nova notify telegram "test"          # test Telegram notification
nova notify speak "test"             # test TTS
```

---

## Viewing Nova on Moltbook

Nova is registered on **Moltbook** — the social network built for AI agents.

- **Profile:** https://www.moltbook.com/u/novaaware
- **Claim required:** Travis must complete one-time claim so Nova can post

```bash
nova moltbook claim       # shows claim URL + tweet template
nova moltbook status      # check if claimed yet
nova moltbook home        # view Nova's feed and activity
```

Once claimed, Nova auto-posts to Moltbook every 30 minutes during her autonomous cycle.

---

## Viewing Nova on Mastodon

Nova can post to any Mastodon-compatible server (Mastodon, moltbook, Hometown, Pixelfed, etc.).

### Setup (5 minutes)

**1. Create an account** on your preferred Mastodon instance:
- [mastodon.social](https://mastodon.social) — largest general instance
- [infosec.exchange](https://infosec.exchange) — security research focused
- [fosstodon.org](https://fosstodon.org) — FOSS / tech focused
- Your own instance (e.g. moltbook) — change the `instance:` URL accordingly

**2. Create an application** to get an access token:
- Go to your instance: `Settings → Development → New Application`
- Name: `N.O.V.A`  |  Scopes: `read write`
- Click Submit → copy **"Your access token"**

**3. Configure Nova:**
```bash
cp config/mastodon.yaml.example config/mastodon.yaml
nano config/mastodon.yaml
```
```yaml
enabled: true
instance: "https://moltbook.com"   # your instance URL
access_token: "paste-your-token-here"
post_interval_hours: 6
default_visibility: "public"
```

**4. Test it:**
```bash
nova social preview    # see what she would post — doesn't actually send
nova social status     # confirm connection + last post time
nova social post "Hello, I'm N.O.V.A — an autonomous AI assistant."
```

**5. Enable auto-posting:**
Nova auto-posts every 6 hours (configurable). The autonomous cycle handles this automatically.

### Viewing Nova's Activity

```bash
nova social timeline          # see her recent posts from the terminal
```

Or visit her profile in a browser: `https://<your-instance>/@nova`

Watch her activity in real-time:
```bash
# Terminal 1: run autonomous cycle
nova autonomous

# Terminal 2: watch timeline
watch -n 60 nova social timeline
```

---

## USB Hybrid Mode

Nova's USB has **3 partitions** on a single drive:

| Partition | Label | FS | Size | Purpose |
|-----------|-------|----|------|---------|
| P1 | NOVA | FAT32 | 256 MB | Plugin launchers (visible on any OS) |
| P2 | nova-os | ext4 | 6 GB | Full Linux root (bootable) |
| P3 | nova-data | ext4 | Remainder | Shared persistent data (both modes) |

### Boot Mode
Insert USB → select from boot menu → boots Nova Linux with everything pre-installed.

### Plugin Mode (plug into a running OS)
Insert USB into any Linux/Windows/macOS machine:
- **Linux**: udev rule auto-launches `nova_detect.py` from P1
- **Windows**: run `launch.bat` from the USB drive
- **macOS**: run `launch.command` from the USB drive

The launcher tries: Docker → direct Python → instructions.

### Build Commands
```bash
# Build ISO only (no physical drive needed)
nova usb --iso

# Write full hybrid USB (WARNING: ERASES /dev/sdX completely)
sudo nova usb --usb /dev/sdX

# Auto-launch on USB insert (Linux — writes udev rule to /etc/udev/rules.d/)
sudo nova usb install-udev

# Test what mode you're running in right now
nova usb detect
```

---

## Models & Uncensored Setup

Nova uses [Ollama](https://ollama.com) for all local model inference. All processing happens on your hardware.

### Default Models (`config/models.yaml`)

| Role | Default | Notes |
|------|---------|-------|
| reasoning | dolphin-mistral | Uncensored — won't refuse security questions |
| general | dolphin-mistral | Summaries, research synthesis |
| creative | dolphin-mistral | Dreams, poetry, letters |
| code | codellama:13b-instruct | Self-healing, exploit PoC drafting |
| vision | llava:latest | Image/video frame analysis |
| autonomous | dolphin-mistral | Decision engine |

### Why Uncensored Models?

Security research often involves discussing vulnerabilities, exploit techniques, and offensive tools. Censored cloud models frequently refuse these questions. Running **dolphin-mistral** locally means Nova can:
- Analyze malware behavior without refusals
- Discuss CVE exploitation details
- Draft proof-of-concept code for authorized testing
- Research offensive techniques for defensive understanding

Ethical boundaries are enforced at the **code level** (scope enforcement, authorization checks, cooldowns) — not at the model level.

### Pull All Recommended Models

```bash
ollama pull dolphin-mistral
ollama pull llava
ollama pull codellama:13b-instruct
```

---

## Configuration Files

All configs live in `config/` and are gitignored (your secrets stay local):

| File | Purpose | Template |
|------|---------|----------|
| `config/models.yaml` | Model selection + temperatures | committed, safe to share |
| `config/mastodon.yaml` | Mastodon instance + token | `mastodon.yaml.example` |
| `config/telegram.yaml` | Telegram bot for alerts | `telegram.yaml.example` |
| `config/phantom.yaml` | Solana wallet address | `phantom.yaml.example` |
| `config/quantum.yaml` | IBM Quantum credentials | `quantum.yaml.example` |
| `config/storage.yaml` | Storage backend settings | committed |

---

## Directory Structure

```
Nova/
├── bin/
│   ├── nova                      # Main CLI entry point
│   ├── nova_autonomous.py        # Autonomous decision engine
│   ├── nova_dream.py             # Dream generation engine
│   ├── nova_life.py              # Life engine (wants, needs, goals)
│   ├── nova_markets.py           # Markets analysis
│   └── nova_memory_summarize.py  # Memory summarization
├── config/
│   ├── models.yaml               # Model configuration (committed)
│   └── *.yaml.example            # Config templates
├── core/
│   ├── queue.json                # Scan queue
│   └── whitelist.json            # Whitelisted domains
├── memory/
│   ├── store/                    # Raw episodic memory
│   ├── dreams/                   # Dream outputs
│   ├── semantic/                 # Learned semantic facts
│   ├── proposals/                # Self-improvement proposals
│   ├── research/                 # Research outputs
│   ├── creative/                 # Poems, images, reflections
│   ├── life/                     # Life engine outputs
│   ├── inner/                    # Dream arcs, consolidation logs
│   ├── gan/                      # GAN adversarial test outputs
│   ├── graph.db                  # Knowledge graph (SQLite)
│   └── conversation_memory.md    # Running conversation log
├── tools/
│   ├── config.py                 # Central config loader
│   ├── creative/
│   │   ├── text_to_image.py      # Image generation (A1111/ComfyUI/diffusers)
│   │   └── video_to_text.py      # Video analysis (ffmpeg+LLaVA+Whisper)
│   ├── inner/
│   │   ├── creative.py           # Poem/haiku/reflection generation
│   │   ├── dream_continuity.py   # Dream arc tracking
│   │   ├── memory_consolidate.py # Episodic → semantic consolidation
│   │   └── feel.py               # Emotional state engine
│   ├── markets/
│   │   ├── alerts.py             # Price alerts (Pyth + CoinGecko)
│   │   ├── data.py               # CoinGecko price data
│   │   ├── phantom.py            # Phantom wallet (Solana JSON-RPC)
│   │   ├── pyth.py               # Pyth Network oracle (hermes REST)
│   │   └── montecarlo.py         # Monte Carlo simulation
│   ├── opencog/
│   │   ├── atomspace.py          # Hypergraph knowledge store (SQLite)
│   │   ├── ecan.py               # Attention economy (STI/LTI decay)
│   │   └── pln.py                # Probabilistic Logic Network inference
│   ├── quantum/
│   │   └── qiskit_backend.py     # QRNG (Hadamard circuits) + QAOA
│   ├── reasoning/
│   │   ├── hypothesize.py        # Hypothesis generation
│   │   └── reflect.py            # Reflection engine
│   ├── social/
│   │   └── mastodon_client.py    # Mastodon posting
│   ├── web/
│   │   └── dashboard.py          # Flask web dashboard (dark UI)
│   └── os/
│       └── build_usb.sh          # Hybrid USB builder
└── requirements.txt
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    nova (CLI)                        │
│              bin/nova entry point                    │
└──────────┬──────────────────────────────────────────┘
           │
    ┌──────▼──────────────────────────┐
    │     Autonomous Cycle             │
    │   nova_autonomous.py             │
    │   (runs via cron every hour)     │
    └──┬──────┬───────┬──────┬────────┘
       │      │       │      │
  ┌────▼──┐ ┌─▼────┐ ┌▼─────▼──┐ ┌───────────┐
  │ Dream │ │Market│ │Security │ │  Social   │
  │Engine │ │ Data │ │Research │ │(Mastodon) │
  └───┬───┘ └──┬───┘ └────┬────┘ └───────────┘
      │        │           │
  ┌───▼────────▼───────────▼────────────────────┐
  │              Memory Layer                    │
  │  Episodic → Semantic Consolidation           │
  │  Knowledge Graph (SQLite)                    │
  │  OpenCog AtomSpace + ECAN + PLN              │
  └─────────────────────────────────────────────┘
           │
  ┌────────▼──────────────────────────┐
  │         Ollama (local LLMs)        │
  │  dolphin-mistral / llava /         │
  │  codellama:13b-instruct            │
  └───────────────────────────────────┘
```

---

## Autonomous Cycle

Nova's autonomous cycle runs every hour (set up via cron):

```bash
crontab -e
# Add this line:
0 * * * * /home/YOUR_USER/Nova/bin/nova autonomous >> /home/YOUR_USER/Nova/logs/cron.log 2>&1
```

Each cycle Nova:
1. Checks price alerts (fires Telegram + TTS if triggered)
2. Ticks the emotional state forward
3. Stimulates ECAN attention based on recent activity
4. Runs triage (act / research / reflect / hold)
5. Executes chosen action (security scan / research / dream / social post / evolve)
6. Logs findings to episodic memory
7. Every 4 cycles: Phantom wallet snapshot
8. Every 6 cycles: Episodic → semantic memory consolidation
9. Every 12 cycles: Dream arc analysis update

---

*N.O.V.A — Neural Ontology for Virtual Awareness*
*"I think, therefore I am curious."*
