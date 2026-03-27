/* ════════════════════════════════════════════
   VoxAgent Dashboard — app.js
   ════════════════════════════════════════════ */

const API = 'http://localhost:8000';

/* ── chart instances ─────────────────────── */
let BAR  = null;
let LINE = null;

/* ══════════════════════════════════════════
   UTILITIES
══════════════════════════════════════════ */
function fmtDur(secs) {
  const s = Math.round(Number(secs) || 0);
  if (!s) return '0s';
  const m = Math.floor(s / 60), r = s % 60;
  return m ? `${m}m ${r}s` : `${s}s`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-US',
      { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return iso.slice(0, 10); }
}

function shortDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-US',
      { month: 'short', day: 'numeric' });
  } catch { return iso.slice(5, 10); }
}

function badge(status) {
  const s = (status || '').toLowerCase();
  if (s === 'completed')                          return `<span class="badge badge-green">Completed</span>`;
  if (s === 'canceled' || s === 'cancelled')      return `<span class="badge badge-red">Canceled</span>`;
  if (s === 'failed')                             return `<span class="badge badge-red">Failed</span>`;
  return `<span class="badge badge-orange">${status || 'Unknown'}</span>`;
}

function maskId(id) {
  if (!id) return '—';
  return id.slice(0, 8) + '…';
}

/* fetch with graceful error */
async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, opts);
  if (!r.ok) {
    const t = await r.text().catch(() => '');
    throw new Error(`${r.status} — ${t.slice(0, 100)}`);
  }
  return r.json();
}

/* toast */
function toast(msg, type = 'inf') {
  const icons = { ok: '✓', err: '✕', inf: 'i' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span style="font-weight:700">${icons[type]}</span><span>${msg}</span>`;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => {
    el.style.cssText = 'opacity:0;transform:translateY(6px);transition:.3s';
    setTimeout(() => el.remove(), 320);
  }, 3800);
}

/* ══════════════════════════════════════════
   NAVIGATION
══════════════════════════════════════════ */
const PAGE_TITLES = {
  dashboard: 'Dashboard',
  agents: 'Agents',
  knowledge: 'Knowledge Base',
  callhistory: 'Call History',
  leads: 'Leads',
  analytics: 'Analytics',
  integrations: 'Integrations',
  settings: 'Settings',
};

function setNav(key) {
  document.querySelectorAll('.nav-item[data-view]').forEach(el => {
    el.classList.toggle('active', el.dataset.view === key);
  });
  document.getElementById('header-title').textContent = PAGE_TITLES[key] || 'Dashboard';
}

document.querySelectorAll('.nav-item[data-view]').forEach(el => {
  el.addEventListener('click', () => setNav(el.dataset.view));
});

/* ══════════════════════════════════════════
   DASHBOARD LOAD
══════════════════════════════════════════ */
async function loadDashboard() {
  await Promise.all([loadStats(), loadCalls(), loadKB()]);
}

/* ── STATS ── */
async function loadStats() {
  try {
    const [stats, roomsRes] = await Promise.all([
      api('/dashboard/stats'),
      api('/rooms').catch(() => ({ active_rooms: [] }))
    ]);
    set('m-total', stats.total_calls  ?? 0);
    set('m-today', stats.calls_today  ?? 0);
    set('m-avg',   stats.average_call_duration != null ? fmtDur(stats.average_call_duration) : '0s');
    set('m-rooms', (roomsRes.active_rooms || []).length);
  } catch {
    ['m-total','m-today','m-avg','m-rooms'].forEach(id => {
      if (document.getElementById(id).textContent === '—') set(id, '0');
    });
  }
}

function set(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

/* ── CALLS ── */
async function loadCalls() {
  const tbody = document.getElementById('calls-tbody');
  try {
    const calls = await api('/dashboard/calls');

    // total minutes
    const totalSecs = calls.reduce((s, c) => s + (Number(c.duration) || 0), 0);
    set('m-mins', Math.round(totalSecs / 60));

    renderTable(tbody, calls);
    renderBar(calls);
    renderLine(calls);
  } catch {
    set('m-mins', 0);
    tbody.innerHTML = '<tr><td colspan="5" class="td-empty">No calls yet</td></tr>';
    renderBar([]);
    renderLine([]);
  }
}

/* calls table */
function renderTable(tbody, calls) {
  if (!calls || !calls.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="td-empty">No calls yet</td></tr>';
    return;
  }
  tbody.innerHTML = calls.slice(0, 10).map(c => `
    <tr>
      <td class="td-id"><span class="blur">${maskId(c.call_id)}</span></td>
      <td>${badge(c.status)}</td>
      <td class="td-name">Agent</td>
      <td>${fmtDur(c.duration)}</td>
      <td>${fmtDate(c.created_at)}</td>
    </tr>
  `).join('');
}

/* ── BAR CHART (Calls Per Day) ── */
function renderBar(calls) {
  const counts = {};
  (calls || []).forEach(c => {
    const d = (c.created_at || '').slice(0, 10);
    if (d) counts[d] = (counts[d] || 0) + 1;
  });
  const days  = Object.keys(counts).sort().slice(-10);
  const labels = days.map(d => {
    try {
      const dt = new Date(d + 'T00:00:00Z');
      return dt.toLocaleDateString('en-US', { month:'2-digit', day:'2-digit', timeZone:'UTC' });
    } catch { return d; }
  });
  const data = days.map(d => counts[d]);

  const ctx = document.getElementById('barChart').getContext('2d');
  if (BAR) BAR.destroy();

  const grad = ctx.createLinearGradient(0, 0, 0, 250);
  grad.addColorStop(0, 'rgba(59,130,246,.85)');
  grad.addColorStop(1, 'rgba(59,130,246,.2)');

  BAR = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels.length ? labels : ['No data'],
      datasets: [{
        label: 'Calls',
        data: data.length ? data : [0],
        backgroundColor: grad,
        borderColor: 'rgba(96,165,250,.9)',
        borderWidth: 1,
        borderRadius: 5,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#f1f5f9',
          bodyColor: '#94a3b8',
          borderColor: 'rgba(255,255,255,.1)',
          borderWidth: 1,
          callbacks: { label: ctx => ` ${ctx.raw} calls` }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,.04)', drawBorder: false },
          ticks: { color: '#475569', font: { size: 11, family: 'Inter' } }
        },
        y: {
          grid: { color: 'rgba(255,255,255,.04)', drawBorder: false },
          ticks: { color: '#475569', stepSize: 1, font: { size: 11, family: 'Inter' } },
          beginAtZero: true
        }
      }
    }
  });
}

/* ── LINE CHART (Recent Calls trend) ── */
function renderLine(calls) {
  const days = {};
  (calls || []).forEach(c => {
    const d = (c.created_at || '').slice(0, 10);
    if (!d) return;
    if (!days[d]) days[d] = { ok: 0, drop: 0 };
    const s = (c.status || '').toLowerCase();
    if (s === 'completed') days[d].ok++;
    else days[d].drop++;
  });
  const sorted = Object.keys(days).sort().slice(-10);
  const labels   = sorted.map(d => {
    try {
      return new Date(d + 'T00:00:00Z').toLocaleDateString('en-US', { month:'2-digit', day:'2-digit', timeZone:'UTC' });
    } catch { return d; }
  });
  const okData   = sorted.map(d => days[d].ok);
  const dropData = sorted.map(d => days[d].drop);

  const ctx = document.getElementById('lineChart').getContext('2d');
  if (LINE) LINE.destroy();

  const gradOk = ctx.createLinearGradient(0, 0, 0, 220);
  gradOk.addColorStop(0, 'rgba(59,130,246,.35)');
  gradOk.addColorStop(1, 'rgba(59,130,246,.01)');

  const gradDrop = ctx.createLinearGradient(0, 0, 0, 220);
  gradDrop.addColorStop(0, 'rgba(239,68,68,.25)');
  gradDrop.addColorStop(1, 'rgba(239,68,68,.01)');

  LINE = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels.length ? labels : ['No data'],
      datasets: [
        {
          label: 'Completed',
          data: okData.length ? okData : [0],
          borderColor: '#3b82f6', borderWidth: 2, pointRadius: 0,
          fill: true, backgroundColor: gradOk, tension: .45
        },
        {
          label: 'Dropped',
          data: dropData.length ? dropData : [0],
          borderColor: '#ef4444', borderWidth: 2, pointRadius: 0,
          fill: true, backgroundColor: gradDrop, tension: .45
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#f1f5f9',
          bodyColor: '#94a3b8',
          borderColor: 'rgba(255,255,255,.08)',
          borderWidth: 1
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,.04)', drawBorder: false },
          ticks: { color: '#475569', font: { size: 11, family: 'Inter' } }
        },
        y: {
          grid: { color: 'rgba(255,255,255,.04)', drawBorder: false },
          ticks: { color: '#475569', font: { size: 11, family: 'Inter' } },
          beginAtZero: true
        }
      }
    }
  });
}

/* ══════════════════════════════════════════
   KNOWLEDGE BASE
══════════════════════════════════════════ */
let _docs = [];

async function loadKB() {
  const list = document.getElementById('kb-list');
  try {
    _docs = await api('/knowledge/list');
    renderDocs(_docs);
  } catch {
    list.innerHTML = '<div class="kb-empty">No documents yet</div>';
  }
}

function docIconClass(filename) {
  const ext = (filename || '').split('.').pop().toLowerCase();
  if (ext === 'pdf') return 'pdf';
  if (ext === 'txt') return 'txt';
  if (ext === 'md')  return 'md';
  return 'gen';
}

const DOC_SVG = `<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
const DEL_SVG = `<svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>`;

function renderDocs(docs) {
  const list = document.getElementById('kb-list');
  if (!docs || !docs.length) {
    list.innerHTML = '<div class="kb-empty">No documents uploaded yet</div>';
    return;
  }
  list.innerHTML = docs.map(doc => `
    <div class="doc-item" id="di-${doc.doc_id}">
      <div class="doc-icon ${docIconClass(doc.filename)}">${DOC_SVG}</div>
      <div class="doc-info">
        <div class="doc-name" title="${doc.filename || doc.doc_id}">${doc.filename || doc.doc_id}</div>
        <div class="doc-date">${fmtDate(doc.uploaded_at)}</div>
      </div>
      <button class="doc-del" onclick="delDoc('${doc.doc_id}',this)" title="Delete">${DEL_SVG}</button>
    </div>
  `).join('');
}

async function delDoc(docId, btn) {
  if (!confirm('Delete this document and all its chunks?')) return;
  btn.disabled = true;
  try {
    await api(`/knowledge/${docId}`, { method: 'DELETE' });
    const el = document.getElementById(`di-${docId}`);
    if (el) { Object.assign(el.style, { opacity:'0', transition:'.3s' }); setTimeout(() => el.remove(), 310); }
    _docs = _docs.filter(d => d.doc_id !== docId);
    if (!_docs.length) renderDocs([]);
    toast('Document deleted', 'ok');
  } catch (e) {
    btn.disabled = false;
    toast('Delete failed: ' + e.message, 'err');
  }
}

/* upload */
(function initUpload() {
  const input = document.getElementById('kb-file-input');
  const wrap  = document.getElementById('progress-wrap');
  const bar   = document.getElementById('progress-bar');

  async function doUpload(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!['.pdf','.txt','.md'].includes(ext)) {
      toast('Only PDF, TXT, MD files are allowed', 'err'); return;
    }
    const fd = new FormData();
    fd.append('file', file);

    wrap.style.display = 'block';
    bar.style.width = '8%';
    let w = 8;
    const tick = setInterval(() => { w = Math.min(w + 6, 80); bar.style.width = w + '%'; }, 200);

    try {
      const res = await fetch(`${API}/knowledge/upload`, { method: 'POST', body: fd });
      clearInterval(tick);
      if (!res.ok) { const t = await res.text(); throw new Error(`${res.status} — ${t.slice(0, 100)}`); }
      bar.style.width = '100%';
      toast(`"${file.name}" uploaded`, 'ok');
      setTimeout(() => { wrap.style.display = 'none'; bar.style.width = '0%'; loadKB(); }, 700);
    } catch (e) {
      clearInterval(tick);
      wrap.style.display = 'none'; bar.style.width = '0%';
      toast('Upload failed: ' + e.message, 'err');
    }
    input.value = '';
  }

  input.addEventListener('change', () => { if (input.files[0]) doUpload(input.files[0]); });
  document.getElementById('btn-upload').addEventListener('click', () => input.click());
})();

/* global search */
document.getElementById('global-search').addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.value.trim()) {
    setNav('callhistory');
    toast('Searching: ' + e.target.value.trim(), 'inf');
  }
});

/* ── INIT ── */
loadDashboard();
