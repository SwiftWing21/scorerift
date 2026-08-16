"""Single-page dashboard HTML — fully self-contained (no external deps).

The entire UI is one HTML string with embedded CSS and JS. It fetches data
from the JSON API endpoints and renders everything client-side. Zero build
step, zero CDN dependencies.

Security: All dynamic content is inserted via textContent or safe DOM
construction. No innerHTML with user-controlled data.
"""

from __future__ import annotations


def render_dashboard() -> str:
    """Return the complete dashboard HTML page."""
    return _DASHBOARD_HTML


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ScoreRift</title>
<style>
/* ── Reset & Base ──────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #0f1117;
  --surface: #1a1d27;
  --card: #222632;
  --border: #2e3345;
  --text: #e2e8f0;
  --muted: #64748b;
  --accent: #818cf8;
  --accent-dim: #6366f1;
  --green: #34d399;
  --yellow: #fbbf24;
  --red: #f87171;
  --orange: #fb923c;
  --radius: 10px;
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  --mono: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
}

body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  min-height: 100vh;
}

/* ── Layout ────────────────────────────────────────────────────────── */
.container {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 20px 48px;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 28px;
}

header h1 {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.5px;
}

header h1 span { color: var(--accent); }

.meta-path {
  font-size: 11px;
  font-family: var(--mono);
  color: var(--muted);
  margin-top: 2px;
  max-width: 500px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ── Health Badge ──────────────────────────────────────────────────── */
.health-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 14px;
}

.health-badge.ok { background: rgba(52,211,153,0.12); color: var(--green); }
.health-badge.warn { background: rgba(251,191,36,0.12); color: var(--yellow); }
.health-badge.fail { background: rgba(248,113,113,0.12); color: var(--red); }
.health-badge .dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: currentColor;
}

/* ── Grade Ring ────────────────────────────────────────────────────── */
.grade-section {
  display: flex;
  gap: 28px;
  margin-bottom: 28px;
}

.grade-ring-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.grade-ring {
  width: 120px; height: 120px;
  position: relative;
}

.grade-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.grade-ring circle {
  fill: none;
  stroke-width: 8;
  stroke-linecap: round;
}
.grade-ring .track { stroke: var(--border); }
.grade-ring .fill { stroke: var(--accent); transition: stroke-dashoffset 0.8s ease; }
.grade-ring .label {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.grade-ring .grade-letter { font-size: 32px; font-weight: 800; color: var(--accent); }
.grade-ring .grade-score { font-size: 12px; color: var(--muted); font-family: var(--mono); }

.grade-ring-label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }

/* ── Stats Cards ───────────────────────────────────────────────────── */
.stats-row {
  display: flex;
  flex: 1;
  gap: 12px;
  flex-wrap: wrap;
  align-items: stretch;
}

.stat-card {
  flex: 1;
  min-width: 140px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-card .stat-value { font-size: 28px; font-weight: 700; font-family: var(--mono); }
.stat-card .stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.stat-value.green { color: var(--green); }
.stat-value.yellow { color: var(--yellow); }
.stat-value.red { color: var(--red); }

/* ── Score Table ───────────────────────────────────────────────────── */
.section-title {
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--muted);
  margin-bottom: 12px;
  margin-top: 28px;
}

.score-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.score-table th, .score-table td {
  padding: 10px 16px;
  text-align: left;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
}

.score-table th {
  background: var(--surface);
  color: var(--muted);
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.score-table tr:last-child td { border-bottom: none; }
.score-table tr:hover td { background: rgba(129,140,248,0.04); }

.dim-name { font-weight: 600; }

/* ── Score Bar ─────────────────────────────────────────────────────── */
.score-bar-cell { min-width: 180px; }
.score-bar-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}
.score-bar {
  flex: 1;
  height: 6px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}
.score-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}
.score-num {
  font-family: var(--mono);
  font-size: 12px;
  min-width: 38px;
  text-align: right;
}

/* ── Status Badges ─────────────────────────────────────────────────── */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}
.status-badge.ok { background: rgba(52,211,153,0.12); color: var(--green); }
.status-badge.warn { background: rgba(251,191,36,0.12); color: var(--yellow); }
.status-badge.fail { background: rgba(248,113,113,0.12); color: var(--red); }
.status-badge.ack { background: rgba(100,116,139,0.15); color: var(--muted); }

/* ── Manual Grade Detail ───────────────────────────────────────────── */
.manual-cell { position: relative; }
.manual-grade { font-weight: 600; }
.manual-unreviewed {
  color: var(--muted);
  font-size: 11px;
  font-style: italic;
}
.manual-meta {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.3;
  margin-top: 2px;
}
.manual-source {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.manual-source.human { background: rgba(129,140,248,0.12); color: var(--accent); }
.manual-source.llm { background: rgba(251,191,36,0.12); color: var(--yellow); }
.manual-source.feedback { background: rgba(52,211,153,0.12); color: var(--green); }
.manual-notes {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.manual-notes:hover {
  white-space: normal;
  overflow: visible;
}

.confidence-bar {
  display: inline-block;
  width: 50px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  vertical-align: middle;
  margin-right: 6px;
}
.confidence-fill { height: 100%; border-radius: 2px; background: var(--accent); }

/* ── Action Bar ────────────────────────────────────────────────────── */
.action-bar {
  display: flex;
  gap: 10px;
  margin-top: 20px;
  flex-wrap: wrap;
}

.btn {
  padding: 8px 18px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.btn:hover { background: var(--surface); border-color: var(--accent-dim); }
.btn:active { transform: scale(0.98); }
.btn.primary { background: var(--accent-dim); border-color: var(--accent); color: #fff; }
.btn.primary:hover { background: var(--accent); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

.btn .spinner {
  display: inline-block;
  width: 12px; height: 12px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  margin-right: 6px;
  vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Feedback Section ──────────────────────────────────────────────── */
.feedback-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-top: 20px;
}

.feedback-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.feedback-stars {
  display: flex;
  gap: 4px;
}
.feedback-stars .star {
  font-size: 24px;
  cursor: pointer;
  color: var(--border);
  transition: color 0.1s;
  user-select: none;
}
.feedback-stars .star.active { color: var(--yellow); }
.feedback-stars .star:hover { color: var(--yellow); }

.feedback-text {
  flex: 1;
  min-width: 200px;
  padding: 8px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-size: 13px;
  font-family: var(--font);
  resize: none;
  height: 38px;
}
.feedback-text::placeholder { color: var(--muted); }
.feedback-text:focus { outline: none; border-color: var(--accent-dim); }

/* ── Toast ─────────────────────────────────────────────────────────── */
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 10px 20px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  opacity: 0;
  transform: translateY(10px);
  transition: all 0.3s;
  z-index: 100;
}
.toast.show { opacity: 1; transform: translateY(0); }
.toast.success { border-color: var(--green); color: var(--green); }
.toast.error { border-color: var(--red); color: var(--red); }

/* ── Divergence Detail ─────────────────────────────────────────────── */
.ack-btn {
  padding: 2px 10px;
  font-size: 11px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.ack-btn:hover { border-color: var(--yellow); color: var(--yellow); }

/* ── Footer ────────────────────────────────────────────────────────── */
footer {
  margin-top: 40px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--muted);
  display: flex;
  justify-content: space-between;
}
footer a { color: var(--accent); text-decoration: none; }

/* ── Responsive ────────────────────────────────────────────────────── */
@media (max-width: 700px) {
  .grade-section { flex-direction: column; align-items: center; }
  .stats-row { flex-direction: column; }
  .score-table { font-size: 12px; }
  .score-table th, .score-table td { padding: 8px 10px; }
}
</style>
</head>
<body>
<div class="container">

<!-- ── Header ──────────────────────────────────────────────────────── -->
<header>
  <div>
    <h1><span>Score</span>Rift</h1>
    <div id="meta-path" class="meta-path"></div>
  </div>
  <div class="header-right">
    <div id="health-badge" class="health-badge ok">
      <div class="dot"></div>
      <span id="health-text">Loading...</span>
    </div>
  </div>
</header>

<!-- ── Grade + Stats ───────────────────────────────────────────────── -->
<div class="grade-section">
  <div class="grade-ring-container">
    <div class="grade-ring">
      <svg viewBox="0 0 120 120">
        <circle class="track" cx="60" cy="60" r="52"></circle>
        <circle class="fill" id="grade-arc" cx="60" cy="60" r="52"
                stroke-dasharray="326.73" stroke-dashoffset="326.73"></circle>
      </svg>
      <div class="label">
        <div class="grade-letter" id="grade-letter">--</div>
        <div class="grade-score" id="grade-score">--</div>
      </div>
    </div>
    <div class="grade-ring-label">Overall Grade</div>
  </div>

  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-value" id="stat-dimensions">--</div>
      <div class="stat-label">Dimensions</div>
    </div>
    <div class="stat-card">
      <div class="stat-value green" id="stat-passing">--</div>
      <div class="stat-label">Passing</div>
    </div>
    <div class="stat-card">
      <div class="stat-value yellow" id="stat-divergences">--</div>
      <div class="stat-label">Divergences</div>
    </div>
    <div class="stat-card">
      <div class="stat-value red" id="stat-failing">--</div>
      <div class="stat-label">Failing</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" id="stat-reviewed" style="color:var(--accent)">--</div>
      <div class="stat-label">Reviewed</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" id="stat-feedback" style="color:var(--accent)">--</div>
      <div class="stat-label">Feedback</div>
    </div>
  </div>
</div>

<!-- ── Score Table ─────────────────────────────────────────────────── -->
<div class="section-title">Dimension Scores</div>
<table class="score-table">
  <thead>
    <tr>
      <th>Dimension</th>
      <th>Auto Score</th>
      <th>Grade</th>
      <th>Manual Review</th>
      <th>Status</th>
      <th>Confidence</th>
      <th>Last Scan</th>
      <th></th>
    </tr>
  </thead>
  <tbody id="scores-body">
    <tr><td colspan="8" style="text-align:center;color:var(--muted);padding:24px;">Loading...</td></tr>
  </tbody>
</table>

<!-- ── Action Bar ──────────────────────────────────────────────────── -->
<div class="action-bar">
  <button class="btn primary" onclick="runTier('light')" id="btn-light">Run Light</button>
  <button class="btn" onclick="runTier('medium')" id="btn-medium">Run Medium</button>
  <button class="btn" onclick="runTier('daily')" id="btn-daily">Run Daily</button>
  <button class="btn" onclick="runTier('weekly')" id="btn-weekly">Run Weekly</button>
</div>

<!-- ── Feedback ────────────────────────────────────────────────────── -->
<div class="section-title">User Feedback</div>
<div class="feedback-card">
  <div class="feedback-row">
    <div class="feedback-stars" id="stars">
      <span class="star" data-v="1">&#9733;</span>
      <span class="star" data-v="2">&#9733;</span>
      <span class="star" data-v="3">&#9733;</span>
      <span class="star" data-v="4">&#9733;</span>
      <span class="star" data-v="5">&#9733;</span>
    </div>
    <textarea class="feedback-text" id="feedback-text" placeholder="Optional: what's on your mind?" rows="1"></textarea>
    <button class="btn primary" onclick="submitFeedback()" id="btn-feedback">Submit</button>
  </div>
</div>

<footer>
  <span>ScoreRift v0.1.0</span>
  <span>Auto-refreshes every 30s &middot; <a href="health">API Health</a></span>
</footer>

</div><!-- /.container -->

<!-- ── Toast ───────────────────────────────────────────────────────── -->
<div class="toast" id="toast"></div>

<script>
/* ── State ─────────────────────────────────────────────────────────── */
let feedbackScore = 0;
const BASE = window.location.pathname.replace(/\\/$/, '');

/* ── Grade helpers ─────────────────────────────────────────────────── */
const GRADES = {S:1,'A+': .95,A:.9,'A-':.85,'B+':.8,B:.75,'B-':.7,'C+':.65,C:.6,D:.5,F:.3};
function scoreToGrade(s) {
  const entries = Object.entries(GRADES).sort((a,b) => b[1]-a[1]);
  for (const [g, t] of entries) { if (s >= t - 0.035) return g; }
  return 'F';
}
function scoreColor(s) {
  if (s >= 0.85) return 'var(--green)';
  if (s >= 0.70) return 'var(--accent)';
  if (s >= 0.55) return 'var(--yellow)';
  return 'var(--red)';
}

/* ── Safe DOM helpers ──────────────────────────────────────────────── */
function el(tag, attrs, children) {
  const e = document.createElement(tag);
  if (attrs) Object.entries(attrs).forEach(([k,v]) => {
    if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k === 'className') e.className = v;
    else if (k === 'onclick') e.addEventListener('click', v);
    else e.setAttribute(k, v);
  });
  if (children) {
    if (typeof children === 'string') e.textContent = children;
    else if (Array.isArray(children)) children.forEach(c => { if (c) e.appendChild(c); });
    else e.appendChild(children);
  }
  return e;
}

/* ── API ───────────────────────────────────────────────────────────── */
async function api(path, opts) {
  const r = await fetch(BASE + path, opts);
  return r.json();
}

/* ── Build a score row using safe DOM methods ──────────────────────── */
function buildScoreRow(s) {
  const grade = scoreToGrade(s.auto_score);
  const color = scoreColor(s.auto_score);
  const pctW = Math.round(s.auto_score * 100);
  const manual = s.manual_grade || '\\u2014';
  let status = 'ok', statusLabel = 'OK';
  /* Mirror health_check: a failing score only counts when trusted; an
     untrusted one (tool-failure placeholder) is absence of evidence. */
  if (s.auto_score <= 0.5 && (s.auto_confidence || 0) >= 0.5) { status = 'fail'; statusLabel = 'FAIL'; }
  else if (s.auto_score <= 0.5) { status = 'ack'; statusLabel = 'NO EVIDENCE'; }
  else if (s.divergent && !s.acknowledged) { status = 'warn'; statusLabel = 'DIVERGED'; }
  else if (s.acknowledged) { status = 'ack'; statusLabel = 'ACK'; }
  const conf = s.auto_confidence || 0;
  const confPct = Math.round(conf * 100);

  const tr = el('tr');

  // Dimension name
  tr.appendChild(el('td', {className:'dim-name'}, s.name));

  // Score bar
  const barFill = el('div', {className:'score-bar-fill', style:{width:pctW+'%', background:color}});
  const bar = el('div', {className:'score-bar'}, [barFill]);
  const num = el('span', {className:'score-num', style:{color:color}}, s.auto_score.toFixed(3));
  const wrap = el('div', {className:'score-bar-wrap'}, [bar, num]);
  tr.appendChild(el('td', {className:'score-bar-cell'}, [wrap]));

  // Grade
  tr.appendChild(el('td', {style:{fontWeight:'700', color:color}}, grade));

  // Manual review cell — shows grade + source + date + notes
  var manualTd = el('td', {className:'manual-cell'});
  if (s.manual_grade) {
    manualTd.appendChild(el('div', {className:'manual-grade', style:{color:color}}, s.manual_grade));
    var metaDiv = el('div', {className:'manual-meta'});
    if (s.manual_source) {
      var srcClass = 'manual-source';
      if (s.manual_source === 'human') srcClass += ' human';
      else if (s.manual_source === 'oauth_review' || s.manual_source === 'llm_review') srcClass += ' llm';
      else if (s.manual_source === 'user_feedback') srcClass += ' feedback';
      metaDiv.appendChild(el('span', {className:srcClass}, s.manual_source));
    }
    if (s.manual_updated) {
      metaDiv.appendChild(document.createTextNode(' ' + s.manual_updated));
    }
    manualTd.appendChild(metaDiv);
    if (s.manual_notes) {
      manualTd.appendChild(el('div', {className:'manual-notes', title:s.manual_notes}, s.manual_notes));
    }
  } else {
    manualTd.appendChild(el('span', {className:'manual-unreviewed'}, 'not reviewed'));
  }
  tr.appendChild(manualTd);

  // Status badge
  tr.appendChild(el('td', null, [el('span', {className:'status-badge '+status}, statusLabel)]));

  // Confidence
  const confFill = el('div', {className:'confidence-fill', style:{width:confPct+'%'}});
  const confBar = el('div', {className:'confidence-bar'}, [confFill]);
  const confTd = el('td');
  confTd.appendChild(confBar);
  confTd.appendChild(document.createTextNode(confPct + '%'));
  tr.appendChild(confTd);

  // Last scan timestamp
  var scanTd = el('td', {style:{fontSize:'11px', color:'var(--muted)', fontFamily:'var(--mono)'}});
  if (s.timestamp) {
    scanTd.textContent = s.timestamp.replace('T', ' ').substring(0, 16);
  } else {
    scanTd.textContent = '\u2014';
  }
  tr.appendChild(scanTd);

  // Acknowledge button (only for diverged)
  const ackTd = el('td');
  if (status === 'warn') {
    const dimName = s.name;
    ackTd.appendChild(el('button', {className:'ack-btn', onclick:function(){ack(dimName);}}, 'dismiss'));
  }
  tr.appendChild(ackTd);

  return tr;
}

/* ── Refresh ───────────────────────────────────────────────────────── */
async function refresh() {
  try {
    const [scores, health, fb] = await Promise.all([
      api('/scores'), api('/health'), api('/feedback/summary'),
    ]);

    // Health badge
    const badge = document.getElementById('health-badge');
    const htxt = document.getElementById('health-text');
    badge.className = 'health-badge ' + (health.ok ? 'ok' : (health.failing.length ? 'fail' : 'warn'));
    htxt.textContent = health.ok ? 'Healthy' : (health.failing.length ? 'Failing' : 'Diverged');

    // Grade ring
    const pct = health.score;
    const circ = 2 * Math.PI * 52;
    document.getElementById('grade-arc').style.strokeDashoffset = String(circ * (1 - pct));
    document.getElementById('grade-arc').style.stroke = scoreColor(pct);
    document.getElementById('grade-letter').textContent = health.grade;
    document.getElementById('grade-letter').style.color = scoreColor(pct);
    document.getElementById('grade-score').textContent = pct.toFixed(3);

    // Stats
    const passing = scores.filter(function(s){return s.auto_score > 0.5 && !s.divergent;}).length;
    const failing = scores.filter(function(s){return s.auto_score <= 0.5;}).length;
    const divs = scores.filter(function(s){return s.divergent && !s.acknowledged;}).length;
    var reviewed = scores.filter(function(s){return s.manual_grade;}).length;
    document.getElementById('stat-dimensions').textContent = String(scores.length);
    document.getElementById('stat-passing').textContent = String(passing);
    document.getElementById('stat-divergences').textContent = String(divs);
    document.getElementById('stat-failing').textContent = String(failing);
    document.getElementById('stat-reviewed').textContent = reviewed + '/' + scores.length;
    document.getElementById('stat-feedback').textContent = String(fb.count || 0);

    // Score table — safe DOM construction
    const tbody = document.getElementById('scores-body');
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    if (!scores.length) {
      const emptyTr = el('tr');
      const emptyTd = el('td', {colspan:'7', style:{textAlign:'center', color:'var(--muted)', padding:'24px'}});
      emptyTd.textContent = 'No scores yet. Click Run Light to start.';
      emptyTr.appendChild(emptyTd);
      tbody.appendChild(emptyTr);
      return;
    }
    scores.forEach(function(s) { tbody.appendChild(buildScoreRow(s)); });
  } catch (e) {
    console.error('Refresh failed:', e);
  }
}

/* ── Actions ───────────────────────────────────────────────────────── */
async function runTier(tier) {
  const btn = document.getElementById('btn-' + tier);
  const orig = btn.textContent;
  btn.textContent = tier + '...';
  btn.disabled = true;
  try {
    await api('/trigger/' + encodeURIComponent(tier), { method: 'POST' });
    toast('Ran ' + tier + ' tier', 'success');
    await refresh();
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
  btn.textContent = orig;
  btn.disabled = false;
}

async function ack(dim) {
  await api('/acknowledge/' + encodeURIComponent(dim), { method: 'POST' });
  toast('Acknowledged ' + dim, 'success');
  refresh();
}

/* ── Feedback ──────────────────────────────────────────────────────── */
document.querySelectorAll('#stars .star').forEach(function(star) {
  star.addEventListener('click', function() {
    feedbackScore = parseInt(star.dataset.v);
    document.querySelectorAll('#stars .star').forEach(function(s, i) {
      s.classList.toggle('active', i < feedbackScore);
    });
  });
  star.addEventListener('mouseenter', function() {
    var v = parseInt(star.dataset.v);
    document.querySelectorAll('#stars .star').forEach(function(s, i) {
      s.classList.toggle('active', i < v);
    });
  });
});
document.getElementById('stars').addEventListener('mouseleave', function() {
  document.querySelectorAll('#stars .star').forEach(function(s, i) {
    s.classList.toggle('active', i < feedbackScore);
  });
});

async function submitFeedback() {
  if (!feedbackScore) { toast('Select a star rating first', 'error'); return; }
  var text = document.getElementById('feedback-text').value.trim();
  try {
    await api('/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ score: feedbackScore * 0.2, scope: 'overall', text: text || null }),
    });
    toast('Feedback submitted', 'success');
    feedbackScore = 0;
    document.querySelectorAll('#stars .star').forEach(function(s){s.classList.remove('active');});
    document.getElementById('feedback-text').value = '';
    refresh();
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

/* ── Toast ──────────────────────────────────────────────────────────── */
function toast(msg, type) {
  var toastEl = document.getElementById('toast');
  toastEl.textContent = msg;
  toastEl.className = 'toast ' + (type || '') + ' show';
  clearTimeout(toastEl._timer);
  toastEl._timer = setTimeout(function(){ toastEl.className = 'toast'; }, 3000);
}

/* ── Init ──────────────────────────────────────────────────────────── */
refresh();
setInterval(refresh, 30000);

// Load meta (db/baseline paths) once
api('/meta').then(function(meta) {
  var pathEl = document.getElementById('meta-path');
  if (meta.db_path) {
    pathEl.textContent = meta.db_path;
    pathEl.title = 'DB: ' + meta.db_path + '\\nBaseline: ' + meta.baseline_path;
  }
}).catch(function(){});
</script>
</body>
</html>"""
