"""Minimal HTML dashboard — renders live data from OptiFolio API."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OptiFolio Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
  h1 { font-size: 1.8rem; color: #60a5fa; margin-bottom: 4px; }
  .subtitle { color: #94a3b8; font-size: 0.9rem; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 20px; }
  .card { background: #1e293b; border-radius: 10px; padding: 16px; border: 1px solid #334155; }
  .card h2 { font-size: 1rem; color: #93c5fd; margin-bottom: 10px; }
  .metric { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #334155; font-size: 0.9rem; }
  .metric:last-child { border-bottom: none; }
  .metric-label { color: #94a3b8; }
  .metric-value { font-weight: 600; }
  .green { color: #4ade80; }
  .red { color: #f87171; }
  .yellow { color: #fbbf24; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th { text-align: left; padding: 8px 6px; color: #94a3b8; font-weight: 500; border-bottom: 1px solid #334155; white-space: nowrap; }
  td { padding: 7px 6px; border-bottom: 1px solid #2d3a4f; }
  tr:hover td { background: #27354f; }
  .badge { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
  .b-equity { background: #1e3a5f; color: #60a5fa; }
  .b-fund { background: #1e3a3a; color: #4ade80; }
  .b-cash { background: #3a3a1e; color: #fbbf24; }
  .b-wmp { background: #3a2e1e; color: #fb923c; }
  .b-other { background: #3a1e3a; color: #c084fc; }
  .loading { color: #60a5fa; font-style: italic; }
  .error { color: #f87171; }
  .count { color: #94a3b8; font-size: 0.75rem; margin-left: 6px; }
  .refresh { position: fixed; top: 16px; right: 16px; background: #2563eb; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem; }
  .refresh:hover { background: #1d4ed8; }
  .small { font-size: 0.75rem; color: #64748b; }
  .bar { height: 6px; background: #334155; border-radius: 3px; margin-top: 4px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 3px; }
</style>
</head>
<body>
<button class="refresh" onclick="loadAll()">Refresh</button>
<h1>OptiFolio</h1>
<div class="subtitle">Portfolio & Market Data Overview</div>

<div class="grid">
  <div class="card">
    <h2>Portfolio (V2 Engine)</h2>
    <div id="port-summary" class="loading">Loading...</div>
  </div>
  <div class="card">
    <h2>Asset Class Exposure</h2>
    <div id="exposure" class="loading">Loading...</div>
  </div>
  <div class="card">
    <h2>Currency Exposure</h2>
    <div id="currency" class="loading">Loading...</div>
  </div>
</div>

<div class="card" style="margin-bottom:16px">
  <h2>Portfolio Positions</h2>
  <div style="overflow-x:auto">
    <table>
      <thead><tr><th>Symbol</th><th>Asset Class</th><th>Value (CNY)</th><th>Weight</th></tr></thead>
      <tbody id="pos-table"><tr><td colspan="4" class="loading">Loading...</td></tr></tbody>
    </table>
  </div>
</div>

<div class="card" style="margin-bottom:16px">
  <h2>Registry Assets <span class="count" id="reg-count"></span></h2>
  <div style="overflow-x:auto">
    <table>
      <thead><tr><th>Symbol</th><th>Name</th><th>Type</th><th>Currency</th><th>Source</th></tr></thead>
      <tbody id="reg-table"><tr><td colspan="5" class="loading">Loading...</td></tr></tbody>
    </table>
  </div>
</div>

<div class="card">
  <h2>Bank WMP Products (Active Storage) <span class="count" id="wmp-count"></span></h2>
  <div style="overflow-x:auto">
    <table>
      <thead><tr><th>Code</th><th>Last NAV</th><th>Records</th><th>Date Range</th></tr></thead>
      <tbody id="wmp-table"><tr><td colspan="4" class="loading">Loading...</td></tr></tbody>
    </table>
  </div>
</div>

<script>
const API = '';

async function get(path) {
  try { const r = await fetch(API + path); if (!r.ok) throw new Error(r.status); return await r.json(); }
  catch(e) { return { success: false, error: e.message }; }
}

function fmt(n, d) {
  d = d === undefined ? 2 : d;
  if (n === undefined || n === null || isNaN(n)) return '-';
  return n.toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
}

function money(n) { return '¥' + fmt(n, 0); }

function badge(t) {
  if (!t) return '<span class="badge b-other">-</span>';
  if (t.includes('stock') || t.includes('equity')) return '<span class="badge b-equity">Equity</span>';
  if (t.includes('fund')) return '<span class="badge b-fund">Fund</span>';
  if (t.includes('cash') || t.includes('currency')) return '<span class="badge b-cash">Cash</span>';
  if (t.includes('bank') || t.includes('wmp')) return '<span class="badge b-wmp">WMP</span>';
  return '<span class="badge b-other">' + t + '</span>';
}

async function loadPortfolio() {
  const el = document.getElementById('port-summary');
  const res = await get('/api/portfolio/v2/risk/exposure?as_of=' + new Date().toISOString().slice(0, 10));
  if (!res.success) { el.innerHTML = '<div class="error">' + (res.message || res.error) + '</div>'; return; }
  const d = res.data;
  let html = '<div class="metric"><span class="metric-label">Total Value</span><span class="metric-value green">' + money(d.total_value) + '</span></div>';
  d.by_asset_class.forEach(i => {
    html += '<div class="metric"><span class="metric-label">' + i.bucket + '</span><span class="metric-value">' + money(i.value) + ' (' + fmt(i.pct*100,1) + '%)</span></div>';
  });
  el.innerHTML = html;

  document.getElementById('exposure').innerHTML = d.by_asset_class.map(i => {
    const color = i.bucket==='equity'?'#60a5fa':(i.bucket==='cash'?'#4ade80':'#fbbf24');
    return '<div class="metric"><span class="metric-label">' + i.bucket + '</span><span class="metric-value">' + fmt(i.pct*100,1) + '%</span></div><div class="bar"><div class="bar-fill" style="width:' + (i.pct*100) + '%;background:' + color + '"></div></div>';
  }).join('');

  document.getElementById('currency').innerHTML = d.by_currency.map(i => {
    const color = i.bucket==='CNY'?'#f87171':(i.bucket==='USD'?'#60a5fa':'#fbbf24');
    return '<div class="metric"><span class="metric-label">' + i.bucket + '</span><span class="metric-value">' + fmt(i.pct*100,1) + '%</span></div><div class="bar"><div class="bar-fill" style="width:' + (i.pct*100) + '%;background:' + color + '"></div></div>';
  }).join('');

  // Positions table from exposure data
  const posEl = document.getElementById('pos-table');
  let rows = '';
  d.by_asset_class.forEach(ac => {
    const syms = ac.asset_ids.join(', ');
    rows += '<tr><td>' + syms + '</td><td>' + badge(ac.bucket) + '</td><td>' + money(ac.value) + '</td><td>' + fmt(ac.pct*100, 1) + '%</td></tr>';
  });
  posEl.innerHTML = rows || '<tr><td colspan="4" class="small">No positions</td></tr>';
}

async function loadRegistry() {
  const el = document.getElementById('reg-table');
  const res = await get('/api/assets/overview');
  if (!res.success) { el.innerHTML = '<tr><td colspan="5" class="error">' + (res.message || res.error) + '</td></tr>'; return; }
  const assets = res.data.recent_assets || [];
  document.getElementById('reg-count').textContent = '(' + assets.length + ' from registry)';
  el.innerHTML = assets.slice(0, 30).map(a =>
    '<tr><td>' + (a.symbol || '-') + '</td><td>' + (a.name || '-') + '</td><td>' + badge(a.asset_type) + '</td><td>' + (a.currency || '-') + '</td><td class="small">' + (a.source || '-') + '</td></tr>'
  ).join('');
}

async function loadWMP() {
  const el = document.getElementById('wmp-table');
  // Get all assets from active storage
  const res = await get('/api/market/assets');
  if (!res.success || !res.data || !res.data.assets) {
    el.innerHTML = '<tr><td colspan="4" class="error">Failed to load market assets</td></tr>';
    return;
  }
  const all = res.data.assets;
  // Filter WMP-like codes
  const wmps = all.filter(a => /^(W[A-Z]|GKF|J[0-9]|MPJF|23GS|AMHQL|WP[A-Z]|WPEK|WPFK|WPIK|WPJK|WPLK|WPRM|WPTK|WPUJ|WPVK|WPWF|WPXK|WPYK|WTGF)/.test(a)).slice(0, 30);
  document.getElementById('wmp-count').textContent = '(' + wmps.length + ' shown / ' + all.length + ' total)';
  if (wmps.length === 0) { el.innerHTML = '<tr><td colspan="4">No WMP assets found</td></tr>'; return; }

  // Fetch prices for each
  const rows = await Promise.all(wmps.map(async code => {
    try {
      const pr = await get('/api/market/prices?assets=' + encodeURIComponent(code) + '&start=2024-01-01&end=2026-06-05');
      if (pr.success && pr.data && pr.data.records && pr.data.records.length > 0) {
        const recs = pr.data.records;
        const last = recs[recs.length - 1];
        const first = recs[0];
        const price = last[code] || last.adj_close || last.close || '-';
        return '<tr><td>' + code + '</td><td>' + fmt(price, 4) + '</td><td>' + recs.length + '</td><td class="small">' + first.date + ' ~ ' + last.date + '</td></tr>';
      }
    } catch(e) {}
    return '<tr><td>' + code + '</td><td>-</td><td>-</td><td>-</td></tr>';
  }));
  el.innerHTML = rows.join('');
}

async function loadAll() {
  await Promise.all([loadPortfolio(), loadRegistry(), loadWMP()]);
}

loadAll();
</script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
def dashboard():
    return HTML
