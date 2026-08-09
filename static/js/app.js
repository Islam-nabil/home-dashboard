// Shared vanilla-JS helpers. No framework, no CDN dependency, no build step.

function fmtEGP(v) {
  if (v === null || v === undefined) return '—';
  return Math.round(v).toLocaleString('en-US') + ' EGP';
}

async function apiFetch(url, options) {
  const opts = Object.assign({ headers: { 'Content-Type': 'application/json' } }, options || {});
  const resp = await fetch(url, opts);
  if (!resp.ok) {
    let msg = 'Request failed';
    try { const j = await resp.json(); msg = j.error || msg; } catch (e) {}
    throw new Error(msg);
  }
  return resp.status === 204 ? null : resp.json();
}

// ---------------- Sortable / filterable tables ----------------
// Usage: <table class="data-table" data-sortable> ... <th data-sort-key="price" data-sort-type="number">
document.addEventListener('click', function (e) {
  const th = e.target.closest('th[data-sort-key]');
  if (!th) return;
  const table = th.closest('table');
  const key = th.dataset.sortKey;
  const type = th.dataset.sortType || 'string';
  const tbody = table.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const asc = th.dataset.sortDir !== 'asc';
  table.querySelectorAll('th').forEach(h => { h.classList.remove('sorted'); delete h.dataset.sortDir; });
  th.classList.add('sorted');
  th.dataset.sortDir = asc ? 'asc' : 'desc';

  rows.sort((a, b) => {
    let va = a.querySelector(`[data-cell="${key}"]`)?.dataset.value ?? '';
    let vb = b.querySelector(`[data-cell="${key}"]`)?.dataset.value ?? '';
    if (type === 'number') {
      va = parseFloat(va) || -Infinity;
      vb = parseFloat(vb) || -Infinity;
      return asc ? va - vb : vb - va;
    }
    return asc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
  });
  rows.forEach(r => tbody.appendChild(r));
});

// ---------------- Generic text filter ----------------
// Usage: <input data-filter-target="#some-table tbody tr" data-filter-text>
document.addEventListener('input', function (e) {
  if (!e.target.matches('[data-filter-target]')) return;
  const target = e.target.dataset.filterTarget;
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll(target).forEach(row => {
    const text = row.dataset.searchText || row.textContent;
    row.style.display = text.toLowerCase().includes(q) ? '' : 'none';
  });
});

// ---------------- Select-based filter (e.g. status dropdown) ----------------
document.addEventListener('change', function (e) {
  if (!e.target.matches('[data-select-filter-target]')) return;
  const target = e.target.dataset.selectFilterTarget;
  const attr = e.target.dataset.selectFilterAttr || 'data-status';
  const val = e.target.value;
  document.querySelectorAll(target).forEach(row => {
    if (!val) { row.style.display = ''; return; }
    row.style.display = row.getAttribute(attr) === val ? '' : 'none';
  });
});

// ---------------- Assistant panel ----------------
(function () {
  const fab = document.getElementById('assistant-fab');
  const panel = document.getElementById('assistant-panel');
  const closeBtn = document.getElementById('assistant-close');
  const input = document.getElementById('assistant-input');
  const sendBtn = document.getElementById('assistant-send');
  const messages = document.getElementById('assistant-messages');
  if (!fab) return;

  fab.addEventListener('click', () => panel.classList.toggle('open'));
  closeBtn.addEventListener('click', () => panel.classList.remove('open'));

  function addMessage(text, cls) {
    const div = document.createElement('div');
    div.className = 'assistant-msg ' + cls;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  async function ask(question) {
    if (!question) return;
    addMessage(question, 'user');
    input.value = '';
    const thinking = document.createElement('div');
    thinking.className = 'assistant-msg bot';
    thinking.textContent = '...';
    messages.appendChild(thinking);
    messages.scrollTop = messages.scrollHeight;
    try {
      const result = await apiFetch('/api/assistant', { method: 'POST', body: JSON.stringify({ question }) });
      thinking.textContent = result.answer;
    } catch (err) {
      thinking.textContent = 'Sorry, something went wrong: ' + err.message;
    }
  }

  sendBtn.addEventListener('click', () => ask(input.value.trim()));
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask(input.value.trim()); });
  document.querySelectorAll('.suggestion').forEach(btn => {
    btn.addEventListener('click', () => { panel.classList.add('open'); ask(btn.textContent); });
  });
})();

// ---------------- Simple modal helper ----------------
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }
document.addEventListener('click', function (e) {
  if (e.target.matches('.modal-overlay')) e.target.classList.remove('open');
});

// ---------------- Tiny canvas sparkline / price history chart ----------------
// points: [{x: iso-string, y: number}], no external chart library needed.
function drawLineChart(canvas, points, opts) {
  opts = opts || {};
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (!points || points.length === 0) {
    ctx.fillStyle = '#626a7d'; ctx.font = '12px sans-serif';
    ctx.fillText('No price history yet', 10, h / 2);
    return;
  }
  const ys = points.map(p => p.y);
  let minY = Math.min(...ys), maxY = Math.max(...ys);
  if (minY === maxY) { minY -= 1; maxY += 1; }
  const pad = 10;
  const xStep = points.length > 1 ? (w - pad * 2) / (points.length - 1) : 0;

  function yPix(y) { return h - pad - ((y - minY) / (maxY - minY)) * (h - pad * 2); }

  // target price line
  if (opts.target) {
    ctx.strokeStyle = '#f5b942'; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad, yPix(opts.target)); ctx.lineTo(w - pad, yPix(opts.target)); ctx.stroke();
    ctx.setLineDash([]);
  }
  // low marker
  if (opts.low) {
    ctx.strokeStyle = '#33d6a6'; ctx.setLineDash([2, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad, yPix(opts.low)); ctx.lineTo(w - pad, yPix(opts.low)); ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.strokeStyle = opts.color || '#5b9dff';
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = pad + i * xStep, y = yPix(p.y);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = opts.color || '#5b9dff';
  points.forEach((p, i) => {
    const x = pad + i * xStep, y = yPix(p.y);
    ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill();
  });
}

// ---------------- "Who's this" identity switcher ----------------
// Just a display name for the Activity feed (not a login) — see
// templates/activity_page.html and README "Activity" notes.
document.addEventListener('DOMContentLoaded', function () {
  const btn = document.getElementById('whoami-btn');
  if (!btn) return;
  btn.addEventListener('click', async function () {
    const current = document.getElementById('whoami-label').textContent.trim();
    const name = prompt('Who is this? (shown on the Activity feed so you can tell who added/changed what)',
                         current === 'Who are you?' ? '' : current);
    if (name === null) return;
    const result = await apiFetch('/api/whoami', { method: 'POST', body: JSON.stringify({ actor_name: name.trim() }) });
    document.getElementById('whoami-label').textContent = result.actor_name || 'Who are you?';
  });
});
