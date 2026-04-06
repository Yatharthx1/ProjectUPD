/**
 * Project UPD — app.js
 * Backend-connected water quality analysis interface
 */

'use strict';

/* ════════════════════════════════════════════
   BACKEND CONFIG
   Update API_BASE to point to your FastAPI server.
════════════════════════════════════════════ */
const API_BASE = 'http://localhost:8000';   // ← change this in production

const API = {
  setProfile:  `${API_BASE}/api/profile`,
  analyze:     `${API_BASE}/api/analyze`,
  chatExtract: `${API_BASE}/api/chat/extract`,
};

/* ════════════════════════════════════════════
   PARAMETER DEFINITIONS PER PROFILE
════════════════════════════════════════════ */
const PROFILE_PARAMS = {
  drinking: [
    { id: 'pH',        label: 'pH',           unit: '' },
    { id: 'TDS',       label: 'TDS',          unit: 'mg/L' },
    { id: 'Turbidity', label: 'Turbidity',    unit: 'NTU' },
    { id: 'Hardness',  label: 'Hardness',     unit: 'mg/L' },
    { id: 'Chloride',  label: 'Chloride',     unit: 'mg/L' },
    { id: 'Sulfate',   label: 'Sulfate',      unit: 'mg/L' },
    { id: 'Nitrate',   label: 'Nitrate',      unit: 'mg/L' },
    { id: 'Fluoride',  label: 'Fluoride',     unit: 'mg/L' },
    { id: 'Iron',      label: 'Iron',         unit: 'mg/L' },
    { id: 'Arsenic',   label: 'Arsenic',      unit: 'μg/L' },
  ],
  agriculture: [
    { id: 'pH',          label: 'pH',          unit: '' },
    { id: 'EC',          label: 'EC',          unit: 'dS/m' },
    { id: 'TDS',         label: 'TDS',         unit: 'mg/L' },
    { id: 'SAR',         label: 'SAR',         unit: '' },
    { id: 'Sodium',      label: 'Sodium',      unit: 'meq/L' },
    { id: 'Chloride',    label: 'Chloride',    unit: 'meq/L' },
    { id: 'Boron',       label: 'Boron',       unit: 'mg/L' },
    { id: 'Bicarbonate', label: 'Bicarbonate', unit: 'meq/L' },
    { id: 'Nitrate',     label: 'Nitrate',     unit: 'mg/L' },
    { id: 'Iron',        label: 'Iron',        unit: 'mg/L' },
  ],
  industrial: [
    { id: 'pH',        label: 'pH',          unit: '' },
    { id: 'TDS',       label: 'TDS',         unit: 'mg/L' },
    { id: 'Turbidity', label: 'Turbidity',   unit: 'NTU' },
    { id: 'Hardness',  label: 'Hardness',    unit: 'mg/L' },
    { id: 'Chloride',  label: 'Chloride',    unit: 'mg/L' },
    { id: 'Sulfate',   label: 'Sulfate',     unit: 'mg/L' },
    { id: 'Silica',    label: 'Silica',      unit: 'mg/L' },
    { id: 'DO',        label: 'Dissolved O₂',unit: 'mg/L' },
    { id: 'COD',       label: 'COD',         unit: 'mg/L' },
    { id: 'BOD',       label: 'BOD',         unit: 'mg/L' },
  ],
  aquaculture: [
    { id: 'pH',          label: 'pH',          unit: '' },
    { id: 'DO',          label: 'Dissolved O₂',unit: 'mg/L' },
    { id: 'Temperature', label: 'Temperature', unit: '°C' },
    { id: 'Ammonia',     label: 'Ammonia',     unit: 'mg/L' },
    { id: 'Nitrite',     label: 'Nitrite',     unit: 'mg/L' },
    { id: 'Nitrate',     label: 'Nitrate',     unit: 'mg/L' },
    { id: 'Turbidity',   label: 'Turbidity',   unit: 'NTU' },
    { id: 'Hardness',    label: 'Hardness',    unit: 'mg/L' },
    { id: 'Alkalinity',  label: 'Alkalinity',  unit: 'mg/L' },
    { id: 'Salinity',    label: 'Salinity',    unit: 'ppt' },
  ],
};

const PROFILE_DISPLAY_NAMES = {
  drinking:    'Drinking Water',
  agriculture: 'Agriculture',
  industrial:  'Industrial',
  aquaculture: 'Aquaculture',
};

/* ════════════════════════════════════════════
   ZONE STYLING MAP
════════════════════════════════════════════ */
const ZONE_STYLE = {
  IDEAL:       { color: '#4ade80', bg: 'rgba(34,197,94,0.1)',  border: 'rgba(34,197,94,0.25)' },
  ACCEPTABLE:  { color: '#a3e635', bg: 'rgba(163,230,53,0.1)', border: 'rgba(163,230,53,0.25)' },
  PERMISSIBLE: { color: '#fbbf24', bg: 'rgba(251,191,36,0.1)', border: 'rgba(251,191,36,0.25)' },
  BREACH:      { color: '#fb923c', bg: 'rgba(251,146,60,0.1)', border: 'rgba(251,146,60,0.25)' },
  DEFICIENT:   { color: '#f87171', bg: 'rgba(248,113,113,0.1)',border: 'rgba(248,113,113,0.25)' },
};

const ZONE_SEG_IDS = ['Ideal', 'Acceptable', 'Permissible', 'Breach', 'Deficient'];

/* ════════════════════════════════════════════
   FALLBACK / MOCK DATA  (used when backend is offline)
   Remove or gate this once your API is live.
════════════════════════════════════════════ */
const MOCK_RESULTS = {
  drinking: {
    score: 72, zone: 'ACCEPTABLE',
    params: [
      { name: 'pH',        value: '7.4',  unit: '',     zone: 'IDEAL' },
      { name: 'TDS',       value: '480',  unit: 'mg/L', zone: 'ACCEPTABLE' },
      { name: 'Turbidity', value: '3.8',  unit: 'NTU',  zone: 'ACCEPTABLE' },
      { name: 'Hardness',  value: '340',  unit: 'mg/L', zone: 'PERMISSIBLE' },
      { name: 'Chloride',  value: '210',  unit: 'mg/L', zone: 'ACCEPTABLE' },
      { name: 'Nitrate',   value: '38',   unit: 'mg/L', zone: 'PERMISSIBLE' },
      { name: 'Fluoride',  value: '0.8',  unit: 'mg/L', zone: 'IDEAL' },
      { name: 'Iron',      value: '0.22', unit: 'mg/L', zone: 'BREACH' },
    ],
    flags: [
      { type: 'ok',   msg: 'pH within BIS IS:10500 ideal range (6.5 – 8.5)' },
      { type: 'warn', msg: 'Hardness 340 mg/L exceeds acceptable limit (300 mg/L) — passes under relaxed permissible conditions' },
      { type: 'warn', msg: 'Nitrate approaching permissible ceiling (45 mg/L) — routine monitoring recommended' },
      { type: 'bad',  msg: 'Iron at 0.22 mg/L exceeds acceptable limit (0.1 mg/L) — aesthetic concern; BREACH classification' },
    ],
  },
  agriculture: {
    score: 65, zone: 'ACCEPTABLE',
    params: [
      { name: 'pH',          value: '7.6', unit: '',      zone: 'IDEAL' },
      { name: 'EC',          value: '1.8', unit: 'dS/m',  zone: 'ACCEPTABLE' },
      { name: 'SAR',         value: '6.2', unit: '',       zone: 'ACCEPTABLE' },
      { name: 'Boron',       value: '0.9', unit: 'mg/L',  zone: 'IDEAL' },
      { name: 'Chloride',    value: '4.2', unit: 'meq/L', zone: 'PERMISSIBLE' },
      { name: 'Bicarbonate', value: '3.8', unit: 'meq/L', zone: 'PERMISSIBLE' },
    ],
    flags: [
      { type: 'ok',   msg: 'EC 1.8 dS/m — moderate restriction; suitable for salt-tolerant crops' },
      { type: 'warn', msg: 'SAR 6.2 — slight sodium accumulation risk on fine-textured soils' },
      { type: 'warn', msg: 'Elevated bicarbonate — potential scaling on drip irrigation emitters' },
    ],
  },
  industrial: {
    score: 52, zone: 'PERMISSIBLE',
    params: [
      { name: 'pH',       value: '6.4', unit: '',     zone: 'ACCEPTABLE' },
      { name: 'TDS',      value: '820', unit: 'mg/L', zone: 'PERMISSIBLE' },
      { name: 'Hardness', value: '580', unit: 'mg/L', zone: 'BREACH' },
      { name: 'Silica',   value: '28',  unit: 'mg/L', zone: 'PERMISSIBLE' },
      { name: 'COD',      value: '95',  unit: 'mg/L', zone: 'BREACH' },
      { name: 'BOD',      value: '22',  unit: 'mg/L', zone: 'PERMISSIBLE' },
    ],
    flags: [
      { type: 'bad',  msg: 'Hardness 580 mg/L — BREACH: severe scaling risk for boilers and heat exchangers' },
      { type: 'bad',  msg: 'COD 95 mg/L exceeds discharge ceiling — treatment required before use' },
      { type: 'warn', msg: 'Silica within permissible range; softening recommended for high-pressure systems' },
    ],
  },
  aquaculture: {
    score: 81, zone: 'ACCEPTABLE',
    params: [
      { name: 'pH',          value: '7.8',  unit: '',     zone: 'IDEAL' },
      { name: 'Dissolved O₂',value: '7.2',  unit: 'mg/L', zone: 'IDEAL' },
      { name: 'Ammonia',     value: '0.04', unit: 'mg/L', zone: 'IDEAL' },
      { name: 'Nitrite',     value: '0.12', unit: 'mg/L', zone: 'ACCEPTABLE' },
      { name: 'Alkalinity',  value: '140',  unit: 'mg/L', zone: 'ACCEPTABLE' },
      { name: 'Salinity',    value: '2.1',  unit: 'ppt',  zone: 'IDEAL' },
    ],
    flags: [
      { type: 'ok',   msg: 'DO 7.2 mg/L — excellent oxygen levels for finfish and shrimp culture' },
      { type: 'ok',   msg: 'Ammonia well within safe limits; no acute toxicity risk detected' },
      { type: 'warn', msg: 'Nitrite 0.12 mg/L — acceptable but trending upward; consider partial water exchange' },
    ],
  },
};

/* ════════════════════════════════════════════
   STATE
════════════════════════════════════════════ */
let state = {
  profile:    'drinking',
  mode:       'llm',       // 'llm' | 'manual' | 'csv'
  busy:       false,
  chatTurn:   0,
  csvFile:    null,
  lastResult: null,
};

/* ════════════════════════════════════════════
   BACKEND HELPERS
════════════════════════════════════════════ */

/**
 * POST the active profile to the backend.
 * Called every time the user switches profile.
 * The backend can use this to load the correct JSON profile.
 */
async function notifyProfileChange(profile) {
  try {
    const res = await fetch(API.setProfile, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ profile }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    console.info('[UPD] Profile confirmed by backend:', data);
  } catch (err) {
    // Backend offline — silently continue with mock mode
    console.warn('[UPD] Backend not reachable for profile update:', err.message);
  }
}

/**
 * POST analysis request to the backend.
 * Returns parsed result object, or falls back to mock data.
 *
 * Expected backend response shape:
 * {
 *   score:  number,          // 0–100
 *   zone:   string,          // IDEAL | ACCEPTABLE | PERMISSIBLE | BREACH | DEFICIENT
 *   params: [{ name, value, unit, zone }],
 *   flags:  [{ type, msg }]  // type: ok | warn | bad
 * }
 */
async function fetchAnalysis(payload) {
  try {
    const res = await fetch(API.analyze, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('[UPD] Backend unreachable, using mock data:', err.message);
    // Return mock data so the UI stays functional during development
    return MOCK_RESULTS[state.profile];
  }
}

/**
 * Build the payload for /api/analyze based on current mode.
 */
function buildPayload() {
  const base = { profile: state.profile, mode: state.mode };

  if (state.mode === 'manual') {
    const params = {};
    PROFILE_PARAMS[state.profile].forEach(({ id }) => {
      const el = document.getElementById(`field_${id}`);
      if (el && el.value !== '') params[id] = parseFloat(el.value);
    });
    return { ...base, params };
  }

  if (state.mode === 'csv') {
    // CSV sends FormData with the file; handled separately
    return { ...base, filename: state.csvFile?.name ?? null };
  }

  // LLM mode: backend reads from session / chat context
  return { ...base, chat_session: true };
}

/* ════════════════════════════════════════════
   PROFILE SELECTION
════════════════════════════════════════════ */
function selectProfile(el, profile) {
  if (state.busy) return;

  // Update card states
  document.querySelectorAll('.profile-card').forEach(c => {
    c.classList.remove('active');
    c.setAttribute('aria-pressed', 'false');
  });
  el.classList.add('active');
  el.setAttribute('aria-pressed', 'true');

  state.profile = profile;

  // Update header label
  document.getElementById('activeProfileLabel').textContent =
    PROFILE_DISPLAY_NAMES[profile];

  // Rebuild manual entry grid
  buildParamsGrid(profile);

  // Notify backend
  notifyProfileChange(profile);
}

/* ════════════════════════════════════════════
   MODE TABS
════════════════════════════════════════════ */
function switchTab(btn, tab) {
  document.querySelectorAll('.mode-tab').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
  });
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

  btn.classList.add('active');
  btn.setAttribute('aria-selected', 'true');
  document.getElementById(`tab-${tab}`).classList.add('active');
  state.mode = tab;
}

/* ════════════════════════════════════════════
   MANUAL PARAMS GRID
════════════════════════════════════════════ */
function buildParamsGrid(profile) {
  const grid = document.getElementById('paramsGrid');
  grid.innerHTML = PROFILE_PARAMS[profile].map(f => `
    <div class="param-field">
      <label class="param-label" for="field_${f.id}">
        <span>${f.label}</span>
        ${f.unit ? `<span class="param-unit">${f.unit}</span>` : ''}
      </label>
      <input
        class="param-input"
        type="number"
        step="any"
        placeholder="—"
        id="field_${f.id}"
        name="${f.id}"
        autocomplete="off"
      >
    </div>
  `).join('');
}

/* ════════════════════════════════════════════
   CHAT — AI ASSISTANT MODE
════════════════════════════════════════════ */
const FALLBACK_BOT_REPLIES = [
  'Understood. Detected pH ≈ 7.2, TDS ~480 mg/L, Turbidity ~4 NTU from your description. Do you have any readings for heavy metals such as iron or arsenic?',
  'Parameters extracted: Hardness ~220 mg/L, Chloride ~180 mg/L. Sodium and fluoride values would strengthen the analysis — are those available?',
  'Parameters are staged for the selected profile. Click Run Analysis to execute the WQI engine.',
];

function sendChat() {
  const input = document.getElementById('chatInput');
  const msg   = input.value.trim();
  if (!msg || state.busy) return;

  input.value = '';
  appendChatMsg('user', msg);

  // Show typing indicator
  const typingId = `typing_${Date.now()}`;
  document.getElementById('chatWindow').insertAdjacentHTML('beforeend', `
    <div class="typing-indicator" id="${typingId}">
      <span></span><span></span><span></span>
    </div>
  `);
  scrollChat();

  // Try backend chat extraction, else use fallback reply
  sendChatToBackend(msg).then(reply => {
    const el = document.getElementById(typingId);
    if (el) el.remove();
    appendChatMsg('bot', reply);
  });
}

async function sendChatToBackend(message) {
  try {
    const res = await fetch(API.chatExtract, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message, profile: state.profile }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.reply ?? data.message ?? FALLBACK_BOT_REPLIES[state.chatTurn % FALLBACK_BOT_REPLIES.length];
  } catch {
    const reply = FALLBACK_BOT_REPLIES[state.chatTurn % FALLBACK_BOT_REPLIES.length];
    state.chatTurn++;
    return reply;
  }
}

function appendChatMsg(role, text) {
  const win = document.getElementById('chatWindow');
  win.insertAdjacentHTML('beforeend', `
    <div class="msg msg--${role === 'bot' ? 'bot' : 'user'}">${text}</div>
  `);
  scrollChat();
}

function scrollChat() {
  const w = document.getElementById('chatWindow');
  w.scrollTop = w.scrollHeight;
}

/* ════════════════════════════════════════════
   CSV UPLOAD
════════════════════════════════════════════ */
function onDrop(event) {
  event.preventDefault();
  document.getElementById('dropzone').classList.remove('dropzone--over');
  onFile(event.dataTransfer.files[0]);
}

function onFile(file) {
  if (!file) return;
  state.csvFile = file;
  const loaded = document.getElementById('csvLoaded');
  loaded.textContent = `File loaded: ${file.name} — ${(file.size / 1024).toFixed(1)} KB`;
  loaded.hidden = false;
}

/* ════════════════════════════════════════════
   ANALYSIS — MAIN FLOW
════════════════════════════════════════════ */
async function runAnalysis() {
  if (state.busy) return;
  state.busy = true;
  setCtaLoading(true);

  const payload = buildPayload();
  const result  = await fetchAnalysis(payload);

  state.lastResult = result;
  renderResults(result);

  setCtaLoading(false);
  state.busy = false;

  // Scroll to results on mobile
  if (window.innerWidth <= 1024) {
    document.getElementById('rResults').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function setCtaLoading(loading) {
  document.querySelectorAll('.btn-analyze').forEach(btn => {
    btn.disabled = loading;
    if (loading) {
      btn.innerHTML = '<span class="spinner"></span> Analyzing...';
    } else {
      const isCsv = btn.id === 'cta-csv';
      btn.textContent = isCsv ? 'Run Batch Analysis' : 'Run Analysis';
    }
  });
}

/* ════════════════════════════════════════════
   RENDER RESULTS
════════════════════════════════════════════ */
function renderResults(result) {
  // Show results, hide placeholder
  document.getElementById('rPlaceholder').style.display = 'none';
  const rResults = document.getElementById('rResults');
  rResults.hidden = false;

  // Profile name
  document.getElementById('rProfileName').textContent =
    PROFILE_DISPLAY_NAMES[state.profile];

  // Animate WQI counter
  animateCounter('wqiNumber', result.score, 900);

  // Zone pill
  const zs   = ZONE_STYLE[result.zone] ?? ZONE_STYLE['ACCEPTABLE'];
  const pill = document.getElementById('zonePill');
  pill.textContent     = result.zone;
  pill.style.background = zs.bg;
  pill.style.color      = zs.color;
  pill.style.border     = `1px solid ${zs.border}`;

  // Zone spectrum bar — highlight active segment
  ZONE_SEG_IDS.forEach(z => {
    const seg = document.getElementById(`zs${z}`);
    const isActive = z.toUpperCase() === result.zone;
    seg.classList.toggle('active', isActive);
  });

  // Parameter breakdown
  const breakdown = document.getElementById('breakdown');
  breakdown.innerHTML = result.params.map(p => {
    const c = ZONE_STYLE[p.zone]?.color ?? '#6a8aaa';
    return `
      <div class="param-row">
        <div class="pr-dot" style="background:${c}"></div>
        <div class="pr-name">${p.name}</div>
        <div class="pr-value" style="color:${c}">${p.value}${p.unit ? ' ' + p.unit : ''}</div>
      </div>
    `;
  }).join('');

  // Flags
  const ICONS = { ok: '✓', warn: '!', bad: '✗' };
  const flags = document.getElementById('flagsList');
  flags.innerHTML = result.flags.map(f => `
    <div class="flag flag--${f.type}">
      <em class="flag-icon">${ICONS[f.type] ?? '·'}</em>
      <span>${f.msg}</span>
    </div>
  `).join('');
}

/* ════════════════════════════════════════════
   COUNTER ANIMATION
════════════════════════════════════════════ */
function animateCounter(elId, target, durationMs) {
  const el    = document.getElementById(elId);
  const start = performance.now();
  const from  = parseInt(el.textContent, 10) || 0;

  function tick(now) {
    const progress = Math.min((now - start) / durationMs, 1);
    const eased    = 1 - Math.pow(1 - progress, 3); // ease-out-cubic
    el.textContent = Math.round(from + (target - from) * eased);
    if (progress < 1) requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}

/* ════════════════════════════════════════════
   DOWNLOAD REPORT
════════════════════════════════════════════ */
function downloadReport() {
  if (!state.lastResult) return;

  const d   = state.lastResult;
  const now = new Date().toLocaleString('en-IN', { hour12: false });
  const pad = (s, n) => String(s).padEnd(n);

  const lines = [
    '══════════════════════════════════════════════════════',
    '  PROJECT UPD — WATER QUALITY ANALYSIS REPORT',
    '══════════════════════════════════════════════════════',
    `  Generated  : ${now}`,
    `  Profile    : ${PROFILE_DISPLAY_NAMES[state.profile]}`,
    `  WQI Score  : ${d.score} / 100`,
    `  Zone       : ${d.zone}`,
    '──────────────────────────────────────────────────────',
    '  PARAMETER BREAKDOWN',
    '──────────────────────────────────────────────────────',
    ...d.params.map(p =>
      `  ${pad(p.name, 20)} ${pad(p.value + (p.unit ? ' ' + p.unit : ''), 16)}  [${p.zone}]`
    ),
    '──────────────────────────────────────────────────────',
    '  FLAGS & WARNINGS',
    '──────────────────────────────────────────────────────',
    ...d.flags.map(f => `  [${f.type.toUpperCase().padEnd(4)}]  ${f.msg}`),
    '══════════════════════════════════════════════════════',
    '  This report is generated by Project UPD.',
    '  Consult a qualified water quality engineer before',
    '  making operational decisions.',
    '══════════════════════════════════════════════════════',
  ];

  const blob     = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
  const url      = URL.createObjectURL(blob);
  const anchor   = document.createElement('a');
  anchor.href    = url;
  anchor.download = `UPD_Report_${state.profile}_${Date.now()}.txt`;
  anchor.click();
  URL.revokeObjectURL(url);
}

/* ════════════════════════════════════════════
   INIT
════════════════════════════════════════════ */
(function init() {
  buildParamsGrid('drinking');

  // Notify backend of initial profile on page load
  notifyProfileChange('drinking');
})();
