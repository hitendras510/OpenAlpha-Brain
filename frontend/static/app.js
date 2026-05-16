/* ============================================================
   OpenBrain Alpha — Frontend Application Logic
   IQC 2026 Autonomous Alpha Engine
   ============================================================ */

// ── State ────────────────────────────────────────────────────
const state = {
  sessionId: null,
  alphas: [],
  currentFilter: 'all',
  alphaCount: 1,
  pipelineTimer: null,
};

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  state.sessionId = getOrCreateSessionId();
  document.getElementById('headerSession').textContent = 'SID: ' + state.sessionId.slice(0, 8);
  loadSession();
});

function getOrCreateSessionId() {
  let sid = sessionStorage.getItem('openbrain_session');
  if (!sid) {
    sid = 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    sessionStorage.setItem('openbrain_session', sid);
  }
  return sid;
}

// ── Session Load ─────────────────────────────────────────────
async function loadSession() {
  try {
    const res = await fetch(`/api/session/${state.sessionId}`);
    const data = await res.json();
    if (data.alphas && data.alphas.length > 0) {
      state.alphas = data.alphas;
      renderAllCards();
      updateStats();
      renderFingerprints(data.fingerprints || []);
      renderFamilyBars(data.family_distribution || {});
    }
  } catch (_) {}
}

// ── Controls ─────────────────────────────────────────────────
function adjustCount(delta) {
  state.alphaCount = Math.max(1, Math.min(5, state.alphaCount + delta));
  document.getElementById('countDisplay').textContent = state.alphaCount;
}

function toggleKey() {
  const inp = document.getElementById('apiKey');
  const icon = document.getElementById('eyeIcon');
  if (inp.type === 'password') {
    inp.type = 'text';
    icon.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>';
  } else {
    inp.type = 'password';
    icon.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>';
  }
}

// ── Generate ─────────────────────────────────────────────────
async function generateAlpha() {
  const apiKey = document.getElementById('apiKey').value.trim();
  if (!apiKey) { showToast('⚠️  Enter your OpenAI API key first', 'warn'); return; }

  const model = document.getElementById('modelSelect').value;
  const familyHint = document.getElementById('familyHint').value;
  const count = state.alphaCount;

  setGenerating(true);
  startPipelineAnimation();

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.sessionId, api_key: apiKey, model, family_hint: familyHint || null, count }),
    });

    const data = await res.json();

    if (!res.ok) {
      const msg = data.detail || 'Server error';
      showToast('❌  ' + msg, 'error');
      return;
    }

    stopPipelineAnimation();
    const newAlphas = data.alphas || [];
    state.alphas.unshift(...newAlphas.reverse());
    newAlphas.forEach(a => prependCard(a));
    updateStats();

    // Reload fingerprints from session
    const sess = await fetch(`/api/session/${state.sessionId}`).then(r => r.json());
    renderFingerprints(sess.fingerprints || []);
    renderFamilyBars(sess.family_distribution || {});

    const passing = newAlphas.filter(a => a.decision !== 'REJECT').length;
    showToast(`✅  Generated ${newAlphas.length} alpha(s) — ${passing} passed gates`, 'success');
  } catch (err) {
    showToast('❌  ' + err.message, 'error');
  } finally {
    setGenerating(false);
    stopPipelineAnimation();
  }
}

// ── Reset ─────────────────────────────────────────────────────
async function resetSession() {
  if (!confirm('Reset this session? All alphas and fingerprints will be cleared.')) return;
  await fetch('/api/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: state.sessionId }),
  });
  state.alphas = [];
  document.getElementById('alphaCards').innerHTML = '';
  document.getElementById('emptyState').style.display = 'block';
  document.getElementById('fingerprintList').innerHTML = '<div class="fp-empty">No fingerprints logged yet.</div>';
  document.getElementById('familyBlock').style.display = 'none';
  updateStats();
  showToast('🔄  Session reset', 'info');
}

// ── Rendering ────────────────────────────────────────────────
function renderAllCards() {
  const container = document.getElementById('alphaCards');
  container.innerHTML = '';
  document.getElementById('emptyState').style.display = 'none';
  [...state.alphas].reverse().forEach(a => {
    const el = buildCard(a);
    container.appendChild(el);
  });
}

function prependCard(alpha) {
  const container = document.getElementById('alphaCards');
  document.getElementById('emptyState').style.display = 'none';
  const el = buildCard(alpha);
  el.classList.add('fade-in');
  container.prepend(el);
  applyFilter();
}

function buildCard(alpha) {
  const div = document.createElement('div');
  const dec = (alpha.decision || '').toLowerCase().replace(/ /g, '-').replace('submit-candidate', 'submit').replace('advance-to-test', 'advance');
  div.className = `alpha-card decision-${dec}`;
  div.dataset.decision = alpha.decision || '';
  div.dataset.id = alpha.runtime_id || alpha.alpha_id || '';
  div.onclick = () => openModal(alpha);

  const metrics = alpha.estimated_metrics || {};
  const corrRisk = (metrics.corr_risk || '').split('—')[0].trim().toLowerCase();
  const corrClass = corrRisk === 'low' ? 'metric-corr-low' : corrRisk === 'medium' ? 'metric-corr-medium' : corrRisk === 'high' ? 'metric-corr-high' : '';

  div.innerHTML = `
    <div class="card-header">
      <div>
        <div class="card-title">${escHtml(alpha.alpha_id || 'ALPHA')}</div>
        <div class="card-id">${alpha.runtime_id || ''} · ${timeAgo(alpha.generated_at)}</div>
      </div>
      <div class="card-badges">
        ${decisionBadge(alpha.decision)}
        <span class="badge badge-family">${escHtml(alpha.family || 'Unknown')}</span>
      </div>
    </div>
    <div class="card-rationale">${escHtml(alpha.economic_rationale || '')}</div>
    <div class="card-expression">${escHtml(alpha.fast_expression || '')}</div>
    <div class="card-metrics">
      <div class="metric-item">
        <div class="metric-label">Sharpe</div>
        <div class="metric-value" style="color:var(--cyan)">${shortMetric(metrics.sharpe)}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Fitness</div>
        <div class="metric-value" style="color:var(--violet)">${shortMetric(metrics.fitness)}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Turnover</div>
        <div class="metric-value" style="color:var(--amber)">${shortMetric(metrics.turnover)}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Corr Risk</div>
        <div class="metric-value ${corrClass}">${corrRisk.toUpperCase() || '—'}</div>
      </div>
    </div>
  `;
  return div;
}

// ── Modal ─────────────────────────────────────────────────────
function openModal(alpha) {
  const m = alpha.estimated_metrics || {};
  const fp = alpha.structural_fingerprint || {};
  const rl = alpha.refinement_log || {};
  const mut = alpha.mutation_paths || [];

  document.getElementById('modalTitle').textContent = (alpha.alpha_id || 'ALPHA') + ' — ' + decisionLabel(alpha.decision);
  document.getElementById('modalFamily').textContent = '⬡ ' + (alpha.family || 'Unknown Family');

  document.getElementById('modalBody').innerHTML = `
    <div class="modal-section">
      <div class="modal-section-title">① Economic Rationale</div>
      <p class="modal-text">${escHtml(alpha.economic_rationale || '—')}</p>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">② Fast Expression</div>
      <div class="modal-expression" id="exprBlock">${escHtml(alpha.fast_expression || '')}</div>
      <button class="copy-btn" id="copyBtn" onclick="copyExpr('${escAttr(alpha.fast_expression || '')}')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        Copy Expression
      </button>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">③ Estimated Metrics</div>
      <div class="metrics-grid">
        <div class="metric-box"><div class="metric-box-label">Sharpe Ratio</div><div class="metric-box-value">${escHtml(m.sharpe || '—')}</div></div>
        <div class="metric-box"><div class="metric-box-label">Fitness</div><div class="metric-box-value">${escHtml(m.fitness || '—')}</div></div>
        <div class="metric-box"><div class="metric-box-label">Turnover</div><div class="metric-box-value">${escHtml(m.turnover || '—')}</div></div>
        <div class="metric-box"><div class="metric-box-label">Corr Risk</div><div class="metric-box-value">${escHtml(m.corr_risk || '—')}</div></div>
      </div>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">④ Structural Fingerprint</div>
      <table class="fp-table">
        <tr><td>Dataset</td><td>${escHtml(fp.dataset || '—')}</td></tr>
        <tr><td>Topology</td><td>${escHtml(fp.topology || '—')}</td></tr>
        <tr><td>Temporal</td><td>${escHtml(fp.temporal || '—')}</td></tr>
        <tr><td>Normalization</td><td>${escHtml(fp.normalization || '—')}</td></tr>
        <tr><td>Direction</td><td>${escHtml(fp.direction || '—')}</td></tr>
        <tr><td>Neutralization</td><td>${escHtml(fp.neutral || '—')}</td></tr>
      </table>
    </div>

    <div class="modal-section">
      <div class="modal-section-title">⑤ Refinement Log</div>
      <div class="metrics-grid">
        <div class="metric-box"><div class="metric-box-label">Original Idea</div><div class="metric-box-value" style="font-family:var(--font);font-size:12px;color:var(--text-dim)">${escHtml(rl.original_idea || '—')}</div></div>
        <div class="metric-box"><div class="metric-box-label">Failure Mode</div><div class="metric-box-value" style="font-family:var(--font);font-size:12px;color:var(--amber)">${escHtml(rl.failure_mode || '—')}</div></div>
      </div>
      <div class="metric-box" style="margin-top:10px"><div class="metric-box-label">Mutation Applied</div><div class="metric-box-value" style="font-family:var(--font);font-size:12px;color:var(--green)">${escHtml(rl.mutation_applied || '—')}</div></div>
    </div>

    ${mut.length ? `
    <div class="modal-section">
      <div class="modal-section-title">⑦ Mutation Paths</div>
      <ul class="mutation-list">
        ${mut.map(m => `<li>${escHtml(m)}</li>`).join('')}
      </ul>
    </div>` : ''}

    <div class="modal-section">
      <div class="modal-section-title">Log Real BRAIN Metrics</div>
      <p class="modal-text" style="margin-bottom:10px;font-size:12px">After submitting to BRAIN, log your actual results here to track real performance.</p>
      <div class="real-metrics-form">
        <input id="realSharpe" type="number" step="0.01" placeholder="Real Sharpe" />
        <input id="realFitness" type="number" step="0.01" placeholder="Real Fitness" />
        <input id="realTurnover" type="number" step="0.01" placeholder="Real Turnover %" />
        <input id="realCorr" type="text" placeholder="Real Corr (e.g. LOW)" />
        <button class="save-metrics-btn" onclick="saveRealMetrics('${escAttr(alpha.runtime_id || alpha.alpha_id || '')}')">Save Real Metrics</button>
      </div>
    </div>
  `;

  document.getElementById('modalOverlay').classList.add('open');
  document.getElementById('alphaModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
  document.getElementById('alphaModal').classList.remove('open');
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── Copy Expression ───────────────────────────────────────────
function copyExpr(expr) {
  navigator.clipboard.writeText(expr).then(() => {
    const btn = document.getElementById('copyBtn');
    if (btn) { btn.textContent = '✓ Copied!'; btn.classList.add('copied'); setTimeout(() => { btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy Expression'; btn.classList.remove('copied'); }, 2000); }
    showToast('📋  Expression copied to clipboard', 'success');
  });
}

// ── Save Real Metrics ─────────────────────────────────────────
async function saveRealMetrics(alphaId) {
  const payload = {
    session_id: state.sessionId,
    alpha_id: alphaId,
    real_sharpe: parseFloat(document.getElementById('realSharpe').value) || null,
    real_fitness: parseFloat(document.getElementById('realFitness').value) || null,
    real_turnover: parseFloat(document.getElementById('realTurnover').value) || null,
    real_corr: document.getElementById('realCorr').value || null,
  };
  try {
    await fetch('/api/update-metrics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    showToast('✅  Real metrics saved', 'success');
  } catch { showToast('❌  Failed to save metrics', 'error'); }
}

// ── Fingerprints ──────────────────────────────────────────────
function renderFingerprints(fingerprints) {
  const list = document.getElementById('fingerprintList');
  if (!fingerprints.length) { list.innerHTML = '<div class="fp-empty">No fingerprints logged yet.</div>'; return; }
  list.innerHTML = fingerprints.map((fp, i) => `
    <div class="fp-card">
      <div class="fp-id">FP-${String(i + 1).padStart(2, '0')}</div>
      ${Object.entries(fp).map(([k, v]) => `<div class="fp-row"><span>${k}</span><span>${escHtml(v || '—')}</span></div>`).join('')}
    </div>
  `).join('');
}

// ── Family Bars ───────────────────────────────────────────────
function renderFamilyBars(dist) {
  const block = document.getElementById('familyBlock');
  const container = document.getElementById('familyBars');
  const entries = Object.entries(dist);
  if (!entries.length) { block.style.display = 'none'; return; }
  block.style.display = 'block';
  const max = Math.max(...entries.map(e => e[1]));
  container.innerHTML = entries.map(([fam, count]) => `
    <div class="family-bar-row">
      <div class="family-bar-label"><span>${escHtml(fam)}</span><span>${count}</span></div>
      <div class="family-bar-track"><div class="family-bar-fill" style="width:${(count / max) * 100}%"></div></div>
    </div>
  `).join('');
}

// ── Stats Update ──────────────────────────────────────────────
function updateStats() {
  const alphas = state.alphas;
  document.getElementById('statGenerated').textContent = alphas.length;
  document.getElementById('statSubmit').textContent = alphas.filter(a => a.decision === 'SUBMIT CANDIDATE').length;
  document.getElementById('statAdvance').textContent = alphas.filter(a => a.decision === 'ADVANCE TO TEST').length;
  document.getElementById('statIterate').textContent = alphas.filter(a => a.decision === 'ITERATE').length;
  document.getElementById('statRejected').textContent = alphas.filter(a => a.decision === 'REJECT').length;
}

// ── Filter ────────────────────────────────────────────────────
function filterAlphas(filter) {
  state.currentFilter = filter;
  ['filterAll', 'filterSubmit', 'filterAdvance', 'filterIterate'].forEach(id => document.getElementById(id)?.classList.remove('active'));
  const btnMap = { all: 'filterAll', 'SUBMIT CANDIDATE': 'filterSubmit', 'ADVANCE TO TEST': 'filterAdvance', ITERATE: 'filterIterate' };
  if (btnMap[filter]) document.getElementById(btnMap[filter])?.classList.add('active');
  applyFilter();
}

function applyFilter() {
  document.querySelectorAll('.alpha-card').forEach(card => {
    const dec = card.dataset.decision || '';
    card.classList.toggle('hidden', state.currentFilter !== 'all' && dec !== state.currentFilter);
  });
}

// ── Pipeline Animation ────────────────────────────────────────
const PIPE_STEPS = ['pipeStep1','pipeStep2','pipeStep3','pipeStep4','pipeStep5','pipeStep6'];
let pipeStepIdx = 0;
let pipeInterval = null;

function startPipelineAnimation() {
  document.getElementById('loadingSkeleton').style.display = 'block';
  pipeStepIdx = 0;
  PIPE_STEPS.forEach(id => { const el = document.getElementById(id); if(el){el.classList.remove('active','done');} });
  document.getElementById(PIPE_STEPS[0])?.classList.add('active');
  pipeInterval = setInterval(() => {
    if (pipeStepIdx < PIPE_STEPS.length - 1) {
      document.getElementById(PIPE_STEPS[pipeStepIdx])?.classList.replace('active','done');
      pipeStepIdx++;
      document.getElementById(PIPE_STEPS[pipeStepIdx])?.classList.add('active');
    }
  }, 800);
}

function stopPipelineAnimation() {
  clearInterval(pipeInterval);
  PIPE_STEPS.forEach(id => { const el = document.getElementById(id); if(el){el.classList.remove('active'); el.classList.add('done');} });
  setTimeout(() => { document.getElementById('loadingSkeleton').style.display = 'none'; }, 600);
}

// ── UI Helpers ────────────────────────────────────────────────
function setGenerating(val) {
  const btn = document.getElementById('generateBtn');
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  btn.disabled = val;
  btn.innerHTML = val ? '<span class="btn-icon">⏳</span> Researching…' : '<span class="btn-icon">⚡</span> Generate Alpha';
  dot.className = 'status-dot' + (val ? ' active' : '');
  txt.textContent = val ? 'Running pipeline…' : 'Idle';
}

function decisionBadge(decision) {
  const map = {
    'SUBMIT CANDIDATE': ['badge-submit', 'SUBMIT ✓'],
    'ADVANCE TO TEST':  ['badge-advance', 'TEST ▶'],
    'ITERATE':          ['badge-iterate', 'ITERATE ↻'],
    'REJECT':           ['badge-reject', 'REJECT ✕'],
  };
  const [cls, label] = map[decision] || ['badge-iterate', decision || 'UNKNOWN'];
  return `<span class="badge ${cls}">${label}</span>`;
}

function decisionLabel(d) {
  return { 'SUBMIT CANDIDATE': '✓ Submit Candidate', 'ADVANCE TO TEST': '▶ Advance to Test', ITERATE: '↻ Iterate', REJECT: '✕ Rejected' }[d] || d || '';
}

function shortMetric(val) {
  if (!val) return '—';
  const s = String(val);
  const match = s.match(/[\d.]+/);
  return match ? match[0] : s.split(' ')[0] || '—';
}

function timeAgo(ts) {
  if (!ts) return '';
  const diff = Math.floor((Date.now() / 1000) - ts);
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  return Math.floor(diff / 3600) + 'h ago';
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function escAttr(s) {
  return String(s).replace(/'/g, '\\\'').replace(/"/g, '&quot;');
}

function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderColor = type === 'success' ? 'rgba(52,211,153,0.4)' : type === 'error' ? 'rgba(248,113,113,0.4)' : type === 'warn' ? 'rgba(251,191,36,0.4)' : 'var(--border-bright)';
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 3000);
}
