#!/usr/bin/env python3
"""
N.O.V.A Web Dashboard

Browser-based UI for Nova's full status, market signals,
wallet, security findings, and inner life.

Runs as a local Flask server on http://localhost:5000

Usage:
    nova web                    start dashboard
    nova web --port 8080        custom port
    nova web --host 0.0.0.0     expose to LAN (to access from phone/tablet)
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path.home() / "Nova"
_nova_root = str(BASE)
if _nova_root not in sys.path:
    sys.path.insert(0, _nova_root)

try:
    from flask import Flask, jsonify, render_template_string, request
except ImportError:
    print("Flask not installed. Run: pip install flask")
    sys.exit(1)

app = Flask(__name__)


# ─── Data helpers ─────────────────────────────────────────────────────────────

def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def get_inner_state() -> dict:
    try:
        state_file = BASE / "memory/inner_state.json"
        if state_file.exists():
            return json.loads(state_file.read_text())
    except Exception:
        pass
    return {}


def get_recent_notifications(n: int = 10) -> list:
    try:
        nf = BASE / "memory/notifications.json"
        if nf.exists():
            return json.loads(nf.read_text())[-n:]
    except Exception:
        pass
    return []


def get_history(n: int = 10) -> list:
    try:
        hf = BASE / "memory/autonomous_history.json"
        if hf.exists():
            return json.loads(hf.read_text())[-n:]
    except Exception:
        pass
    return []


def get_identity() -> dict:
    try:
        f = BASE / "memory/nova_identity.json"
        if f.exists():
            return json.loads(f.read_text())
    except Exception:
        pass
    return {}


def get_dream_arcs() -> list:
    try:
        f = BASE / "memory/inner/dream_arcs.json"
        if f.exists():
            return json.loads(f.read_text()).get("arcs", [])[:10]
    except Exception:
        pass
    return []


def get_semantic_facts(n: int = 10) -> list:
    try:
        facts = []
        d = BASE / "memory/semantic"
        if d.exists():
            for f in sorted(d.glob("fact_*.json"), reverse=True)[:n]:
                facts.append(json.loads(f.read_text()))
        return facts
    except Exception:
        return []


def get_paper_portfolio() -> dict:
    try:
        from tools.markets.paper_trading import portfolio_value
        return portfolio_value()
    except Exception:
        return {}


def get_phantom_portfolio() -> dict:
    try:
        from tools.markets.phantom import portfolio_value, get_wallet_address
        addr = get_wallet_address()
        return portfolio_value(addr)
    except Exception:
        return {}


def get_price_alerts() -> list:
    try:
        from tools.markets.alerts import list_alerts
        return list_alerts()
    except Exception:
        return []


def get_ecan_focus() -> list:
    try:
        from tools.opencog.ecan import get_ecan
        ecan   = get_ecan()
        focus  = ecan.attentional_focus(8)
        ecan.close()
        return focus
    except Exception:
        return []


def get_recent_creative() -> list:
    try:
        from tools.inner.creative import list_creative
        return list_creative(5)
    except Exception:
        return []


def get_log_tail(n: int = 20) -> list:
    try:
        lf = BASE / "logs/autonomous.log"
        if lf.exists():
            lines = lf.read_text().splitlines()
            return lines[-n:]
    except Exception:
        pass
    return []


# ─── HTML template ────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>N.O.V.A Dashboard</title>
<style>
  :root {
    --bg:     #0d0d14;
    --panel:  #13131f;
    --border: #1e1e30;
    --accent: #7c3aed;
    --green:  #22c55e;
    --red:    #ef4444;
    --yellow: #eab308;
    --cyan:   #06b6d4;
    --text:   #e2e8f0;
    --dim:    #64748b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 13px; }
  header { background: var(--panel); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; gap: 16px; }
  header h1 { color: var(--accent); font-size: 18px; letter-spacing: 2px; }
  header .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .ts { color: var(--dim); font-size: 11px; margin-left: auto; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; padding: 16px; }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .panel-header { background: rgba(124,58,237,0.1); border-bottom: 1px solid var(--border); padding: 8px 14px; font-size: 11px; color: var(--accent); letter-spacing: 1px; text-transform: uppercase; display: flex; justify-content: space-between; }
  .panel-body { padding: 12px 14px; }
  .row { display: flex; justify-content: space-between; padding: 3px 0; border-bottom: 1px solid rgba(30,30,48,.5); }
  .row:last-child { border: none; }
  .label { color: var(--dim); }
  .val { color: var(--text); }
  .green { color: var(--green); }
  .red   { color: var(--red); }
  .yellow{ color: var(--yellow); }
  .cyan  { color: var(--cyan); }
  .purple{ color: var(--accent); }
  .dim   { color: var(--dim); }
  .bar-wrap { display: flex; align-items: center; gap: 8px; }
  .bar { height: 6px; border-radius: 3px; background: var(--border); flex: 1; }
  .bar-fill { height: 100%; border-radius: 3px; background: var(--accent); }
  .bar-fill.green { background: var(--green); }
  .bar-fill.red   { background: var(--red); }
  pre { font-family: inherit; font-size: 11px; color: var(--dim); white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
  .tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; background: rgba(124,58,237,.2); color: var(--accent); margin: 2px; }
  .tag.green { background: rgba(34,197,94,.15); color: var(--green); }
  .tag.red   { background: rgba(239,68,68,.15); color: var(--red); }
  .tag.yellow{ background: rgba(234,179,8,.15);  color: var(--yellow); }
  .refresh-btn { background: var(--accent); color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 11px; }
  .refresh-btn:hover { opacity: .8; }
  .alert-item { padding: 4px 0; border-bottom: 1px solid var(--border); }
  .alert-item:last-child { border: none; }
  .wide { grid-column: span 2; }
  @media (max-width: 720px) { .wide { grid-column: span 1; } }
</style>
</head>
<body>
<header>
  <div class="status-dot"></div>
  <h1>N.O.V.A</h1>
  <span style="color:var(--dim)">Neural Ontology for Virtual Awareness</span>
  <span class="ts" id="ts"></span>
  <button class="refresh-btn" onclick="location.reload()">↻ Refresh</button>
</header>

<div class="grid" id="dashboard">
  <!-- Panels injected by JS -->
</div>

<script>
const data = {{ data|tojson }};

function val(v, suffix='', decimals=2) {
  if (v === null || v === undefined) return '<span class="dim">—</span>';
  if (typeof v === 'number') return `${v.toFixed(decimals)}${suffix}`;
  return String(v);
}

function colorVal(v, good='green', mid='yellow', bad='red', threshold_good=0.7, threshold_mid=0.3) {
  const cls = v >= threshold_good ? good : v >= threshold_mid ? mid : bad;
  return `<span class="${cls}">${(v*100).toFixed(0)}%</span>`;
}

function bar(v, cls='') {
  const pct = Math.min(100, Math.max(0, v * 100));
  return `<div class="bar"><div class="bar-fill ${cls}" style="width:${pct}%"></div></div>`;
}

function row(label, value) {
  return `<div class="row"><span class="label">${label}</span><span class="val">${value}</span></div>`;
}

function panel(title, body, subtitle='', wide=false) {
  return `<div class="panel${wide?' wide':''}">
    <div class="panel-header"><span>${title}</span><span class="dim">${subtitle}</span></div>
    <div class="panel-body">${body}</div>
  </div>`;
}

// Identity panel
function identityPanel() {
  const id = data.identity || {};
  const inner = data.inner_state || {};
  let body = '';
  body += row('Name',    `<span class="purple">${id.name || 'N.O.V.A'}</span>`);
  body += row('Version', id.version || '?');
  body += row('Mission', `<span class="dim" style="font-size:11px">${(id.mission||'').slice(0,50)}</span>`);
  if (inner.mood) body += row('Mood', `<span class="cyan">${inner.mood}</span>`);
  if (inner.valence !== undefined) {
    body += `<div class="row"><span class="label">Valence</span>
      <div class="bar-wrap" style="width:60%">${bar(inner.valence, inner.valence > 0.5 ? 'green' : 'red')}</div></div>`;
  }
  return panel('🧠 Identity', body, id.version || '');
}

// Inner state
function innerPanel() {
  const s = data.inner_state || {};
  const needs = s.needs || {};
  let body = '';
  for (const [k,v] of Object.entries(needs)) {
    const cls = v > 0.7 ? 'green' : v > 0.3 ? '' : 'red';
    body += `<div class="row"><span class="label">${k}</span>
      <div class="bar-wrap" style="width:65%">${bar(v, cls)}<span class="${cls}">${(v*100).toFixed(0)}%</span></div></div>`;
  }
  if (!body) body = '<span class="dim">No inner state data</span>';
  return panel('💜 Inner State', body, 'needs');
}

// ECAN attention
function ecanPanel() {
  const atoms = data.ecan_focus || [];
  let body = '';
  for (const a of atoms) {
    const sti = Math.max(0, a.sti);
    const pct = Math.min(1, sti / 100);
    body += `<div class="row"><span class="label" style="max-width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${a.name}</span>
      <div class="bar-wrap" style="width:40%">${bar(pct,'green')}</div></div>`;
  }
  if (!body) body = '<span class="dim">No attention data — run: nova opencog ecan seed</span>';
  return panel('⚡ Attention (ECAN)', body, 'top STI');
}

// Dream arcs
function dreamsPanel() {
  const arcs = data.dream_arcs || [];
  let body = '';
  for (const a of arcs.slice(0,6)) {
    const cls = a.status === 'deep' ? 'purple' : 'yellow';
    body += `<div class="row">
      <span class="label">${a.symbol}</span>
      <span><span class="tag ${cls}">${a.status}</span> <span class="dim">×${a.count}</span></span>
    </div>`;
  }
  if (!body) body = '<span class="dim">No dream arcs yet</span>';
  return panel('🌙 Dream Arcs', body, 'recurring symbols');
}

// Paper portfolio
function paperPanel() {
  const p = data.paper_portfolio || {};
  let body = '';
  const ret = p.total_return_pct || 0;
  const col = ret >= 0 ? 'green' : 'red';
  body += row('Total Value',  `<span class="${col}">$${(p.total_val||0).toFixed(2)}</span>`);
  body += row('Return',       `<span class="${col}">${ret >= 0?'+':''}${ret.toFixed(1)}%</span>`);
  body += row('Cash',         `$${(p.cash_usd||0).toFixed(2)}`);
  body += row('Realized P&L', `<span class="${p.realized_pnl>=0?'green':'red'}">$${(p.realized_pnl||0).toFixed(2)}</span>`);
  body += row('Trades',       p.trades || 0);
  const positions = p.positions || [];
  if (positions.length) {
    body += `<div style="margin-top:8px;font-size:11px;color:var(--dim)">POSITIONS</div>`;
    for (const pos of positions) {
      const pc = pos.unreal_pct >= 0 ? 'green' : 'red';
      body += row(pos.symbol, `<span class="${pc}">${pos.unreal_pct >= 0?'+':''}${pos.unreal_pct.toFixed(1)}%</span>`);
    }
  }
  return panel('📊 Paper Portfolio', body, 'simulated');
}

// Phantom wallet
function phantomPanel() {
  const p = data.phantom || {};
  if (p.error || !p.total_usd) {
    return panel('👛 Phantom Wallet', '<span class="dim">Not configured — run: nova phantom setup</span>', 'Solana');
  }
  let body = '';
  body += row('Total Value', `<span class="green">$${p.total_usd.toFixed(2)}</span>`);
  body += row('SOL', `${(p.sol||0).toFixed(4)} SOL @ $${(p.sol_price||0).toFixed(2)}`);
  body += row('SPL Tokens', p.tokens?.length || 0);
  body += row('NFTs', p.nft_count || 0);
  for (const t of (p.tokens||[]).slice(0,4)) {
    body += row(t.symbol, `<span class="green">$${t.usd_value.toFixed(2)}</span>`);
  }
  return panel('👛 Phantom Wallet', body, 'real holdings');
}

// Price alerts
function alertsPanel() {
  const alerts = data.price_alerts || [];
  let body = '';
  if (!alerts.length) { body = '<span class="dim">No active alerts</span>'; }
  for (const a of alerts) {
    const cls = a.direction === 'above' ? 'green' : 'red';
    body += `<div class="alert-item">
      <span class="${cls}">${a.symbol}</span>
      <span class="dim"> ${a.direction} </span>
      <span>$${Number(a.target).toLocaleString()}</span>
      <span class="dim" style="float:right">${a.created?.slice(0,10)||''}</span>
    </div>`;
  }
  return panel('🔔 Price Alerts', body, `${alerts.length} active`);
}

// Semantic memory
function memoryPanel() {
  const facts = data.semantic_facts || [];
  let body = '';
  for (const f of facts.slice(0,6)) {
    const col = f.topic === 'security' ? 'red' : f.topic === 'markets' ? 'green' : f.topic === 'identity' ? 'purple' : 'cyan';
    body += `<div class="row" style="flex-direction:column;align-items:flex-start;gap:2px;padding:4px 0">
      <span class="tag ${col}">${f.topic}</span>
      <span style="font-size:11px">${f.fact}</span>
    </div>`;
  }
  if (!body) body = '<span class="dim">No semantic facts yet — run: nova memory consolidate</span>';
  return panel('🧩 Semantic Memory', body, 'learned facts');
}

// Creative work
function creativePanel() {
  const works = data.recent_creative || [];
  let body = '';
  for (const w of works) {
    body += `<div class="row"><span class="label purple">${w.form}</span><span class="dim">${w.ts}</span></div>
    <div style="font-size:11px;color:var(--dim);padding:2px 0 6px 0">${w.preview}</div>`;
  }
  if (!body) body = '<span class="dim">No creative works yet — run: nova create poem</span>';
  return panel('✨ Creative Works', body, 'poetry & reflections');
}

// Activity log
function logPanel() {
  const log = data.log_tail || [];
  const body = `<pre>${log.join('\\n') || 'No log entries'}</pre>`;
  return panel('📋 Activity Log', body, 'autonomous.log', true);
}

// Recent history
function historyPanel() {
  const hist = data.history || [];
  let body = '';
  for (const h of hist.reverse()) {
    body += `<div class="row">
      <span class="label" style="max-width:70%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${h.action}: ${h.target||''}</span>
      <span class="dim">${(h.timestamp||'').slice(5,16)}</span>
    </div>`;
  }
  if (!body) body = '<span class="dim">No history yet</span>';
  return panel('🔄 Recent Activity', body, 'autonomous decisions');
}

// Notifications
function notifsPanel() {
  const notifs = data.notifications || [];
  let body = '';
  for (const n of notifs.reverse().slice(0,6)) {
    const pri = n.priority === 'high' ? 'red' : 'yellow';
    body += `<div class="alert-item">
      <span class="tag ${pri}">${n.priority||'normal'}</span>
      <span> ${n.title}</span><br>
      <span class="dim" style="font-size:11px">${n.message?.slice(0,60)||''}</span>
    </div>`;
  }
  if (!body) body = '<span class="dim">No notifications</span>';
  return panel('🔔 Notifications', body, `${notifs.length} total`);
}

// Render all panels
const dash = document.getElementById('dashboard');
dash.innerHTML = [
  identityPanel(),
  innerPanel(),
  ecanPanel(),
  dreamsPanel(),
  paperPanel(),
  phantomPanel(),
  alertsPanel(),
  memoryPanel(),
  creativePanel(),
  notifsPanel(),
  historyPanel(),
  logPanel(),
].join('');

// Live clock
setInterval(() => {
  document.getElementById('ts').textContent = new Date().toLocaleTimeString();
}, 1000);
</script>
</body>
</html>
"""


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    data = {
        "identity":       _safe(get_identity),
        "inner_state":    _safe(get_inner_state),
        "notifications":  _safe(get_recent_notifications),
        "history":        _safe(get_history),
        "dream_arcs":     _safe(get_dream_arcs),
        "semantic_facts": _safe(get_semantic_facts),
        "paper_portfolio":_safe(get_paper_portfolio),
        "phantom":        _safe(get_phantom_portfolio),
        "price_alerts":   _safe(get_price_alerts),
        "ecan_focus":     _safe(get_ecan_focus),
        "recent_creative":_safe(get_recent_creative),
        "log_tail":       _safe(get_log_tail),
        "generated_at":   datetime.now(timezone.utc).isoformat(),
    }
    return render_template_string(DASHBOARD_HTML, data=data)


@app.route("/api/data")
def api_data():
    data = {
        "identity":        _safe(get_identity),
        "inner_state":     _safe(get_inner_state),
        "paper_portfolio": _safe(get_paper_portfolio),
        "phantom":         _safe(get_phantom_portfolio),
        "price_alerts":    _safe(get_price_alerts),
        "ecan_focus":      _safe(get_ecan_focus),
        "history":         _safe(get_history),
        "notifications":   _safe(get_recent_notifications),
    }
    return jsonify(data)


@app.route("/api/think", methods=["POST"])
def api_think():
    question = request.json.get("question", "")
    if not question:
        return jsonify({"error": "no question"})
    try:
        import requests as req
        from tools.config import cfg
        resp = req.post(cfg.ollama_url, json={
            "model": cfg.model("general"),
            "prompt": f"You are N.O.V.A. Travis asks: {question}\n\nRespond as Nova.",
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 300}
        }, timeout=120)
        return jsonify({"response": resp.json().get("response", "")})
    except Exception as e:
        return jsonify({"error": str(e)})


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    port = 5000
    host = "127.0.0.1"

    args = sys.argv[1:]
    if "--port" in args:
        i = args.index("--port")
        port = int(args[i+1]) if i+1 < len(args) else 5000
    if "--host" in args:
        i = args.index("--host")
        host = args[i+1] if i+1 < len(args) else "127.0.0.1"

    print(f"\033[35m[N.O.V.A]\033[0m Web Dashboard → http://{host}:{port}")
    if host == "0.0.0.0":
        import socket
        ip = socket.gethostbyname(socket.gethostname())
        print(f"\033[35m[N.O.V.A]\033[0m LAN access   → http://{ip}:{port}")
    print(f"\033[2mCtrl+C to stop\033[0m\n")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
