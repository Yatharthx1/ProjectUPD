/**
 * BLUE — app.js
 * Backend-connected water quality analysis interface
 */

'use strict';

/* ════════════════════════════════════════════
   BACKEND CONFIG
   Update API_BASE to point to your FastAPI server.
════════════════════════════════════════════ */
const CONFIGURED_API_BASE = document.querySelector('meta[name="blue-api-base"]')?.content?.trim()
  || window.BLUE_API_BASE
  || window.BLUE_CONFIG?.apiBase
  || '';

const API_BASE = (() => {
  const candidate = CONFIGURED_API_BASE || window.location.origin;
  try {
    const url = new URL(candidate, window.location.origin);
    const isLocalhost = ['localhost', '127.0.0.1'].includes(url.hostname);
    if (window.location.protocol === 'https:' && url.protocol !== 'https:' && !isLocalhost) {
      throw new Error('Insecure API base configured');
    }
    return url.origin;
  } catch {
    return window.location.origin;
  }
})();

const MAX_CHAT_MESSAGE_LENGTH = 1500;
const MAX_CSV_SIZE_BYTES = 2 * 1024 * 1024;
const ALLOWED_CSV_TYPES = new Set(['text/csv', 'application/vnd.ms-excel', '']);

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
    { id: 'Coliform',        label: 'Coliform',          unit: 'MPN/100mL' },
    { id: 'Arsenic',         label: 'Arsenic',           unit: 'mg/L' },
    { id: 'Lead',            label: 'Lead',              unit: 'mg/L' },
    { id: 'Nitrates',        label: 'Nitrates',          unit: 'mg/L' },
    { id: 'pH',              label: 'pH',                unit: '' },
    { id: 'Turbidity',       label: 'Turbidity',         unit: 'NTU' },
    { id: 'TDS',             label: 'TDS',               unit: 'mg/L' },
    { id: 'Hardness',        label: 'Hardness',          unit: 'mg/L' },
    { id: 'Chlorides',       label: 'Chlorides',         unit: 'mg/L' },
    { id: 'Sulphate',        label: 'Sulphate',          unit: 'mg/L' },
    { id: 'Fluoride',        label: 'Fluoride',          unit: 'mg/L' },
    { id: 'Iron',            label: 'Iron',              unit: 'mg/L' },
    { id: 'DissolvedOxygen', label: 'Dissolved Oxygen',  unit: 'mg/L' },
    { id: 'BOD',             label: 'BOD',               unit: 'mg/L' },
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
  UNSAFE:      { color: '#f87171', bg: 'rgba(248,113,113,0.1)',border: 'rgba(248,113,113,0.25)' },
};

const ZONE_SEG_IDS = ['Ideal', 'Acceptable', 'Permissible', 'Breach', 'Deficient'];

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
    console.warn('[UPD] Analysis request failed:', err.message);
    return buildErrorResult(`Analysis request failed: ${err.message}`);
  }
}

/**
 * POST CSV file to /api/analyze/csv using FormData.
 * Falls back to mock batch result if backend is offline.
 */
async function fetchCsvAnalysis() {
  if (!state.csvFile) {
    return {
      score: 0, zone: 'ACCEPTABLE', params: [],
      flags: [{ type: 'warn', msg: 'No CSV file loaded. Drop a file first.' }],
    };
  }
  try {
    const form = new FormData();
    form.append('file', state.csvFile);
    const csvUrl = `${API_BASE}/api/analyze/csv?profile=${encodeURIComponent(state.profile)}`;
    const res = await fetch(csvUrl, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    // Show first result's details, summarise rest
    const first = data.results?.[0];
    if (!first) return buildErrorResult('CSV analysis returned no result rows.');
    if (data.results?.length > 1) {
      first.flags = [
        { type: 'ok', msg: `Batch: ${data.count} samples analysed. Showing first result (${first.sample_id ?? 'S001'}).` },
        ...(first.flags ?? []),
      ];
    }
    return first;
  } catch (err) {
    console.warn('[UPD] CSV analysis failed:', err.message);
    return buildErrorResult(`CSV analysis failed: ${err.message}`);
  }
}

/**
 * Build the payload for /api/analyze based on current mode.
 */
function buildErrorResult(message) {
  return {
    score: null,
    zone: 'DEFICIENT',
    status: 'ERROR',
    classification: 'Unavailable',
    params: [],
    flags: [{ type: 'bad', msg: message }],
  };
}

function createElem(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (typeof text === 'string') el.textContent = text;
  return el;
}

function appendTypingIndicator(id) {
  const wrapper = createElem('div', 'typing-indicator');
  wrapper.id = id;
  wrapper.append(createElem('span'), createElem('span'), createElem('span'));
  document.getElementById('chatWindow').appendChild(wrapper);
}

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

async function requestPdf(url, options, fallbackName) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const blob = await res.blob();
  const contentDisposition = res.headers.get('content-disposition') || '';
  const match = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
  const filename = match?.[1] ?? fallbackName;

  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
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
   CHAT — BLUE AI
════════════════════════════════════════════ */

function sendChat() {
  const input = document.getElementById('chatInput');
  const msg   = input.value.trim();
  if (!msg || state.busy) return;
  if (msg.length > MAX_CHAT_MESSAGE_LENGTH) {
    appendChatMsg('bot', `Please keep chat messages under ${MAX_CHAT_MESSAGE_LENGTH} characters.`);
    return;
  }

  input.value = '';
  appendChatMsg('user', msg);

  // Show typing indicator
  const typingId = `typing_${Date.now()}`;
  appendTypingIndicator(typingId);
  scrollChat();

  // Try backend chat extraction, else use fallback reply
  sendChatToBackend(msg).then(async (data) => {
    const el = document.getElementById(typingId);
    if (el) el.remove();
    appendChatMsg('bot', data.reply);

    if (data.report_ready) {
      try {
        const payload = buildPayload();
        payload.meta = {
          location: PROFILE_DISPLAY_NAMES[state.profile],
        };
        await requestPdf(
          `${API_BASE}/api/report`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          },
          `UPD_Report_${state.profile}_${Date.now()}.pdf`,
        );
        appendChatMsg('bot', 'PDF report downloaded successfully.');
      } catch (err) {
        appendChatMsg('bot', `I understood the report request, but the PDF download failed: ${err.message}`);
      }
    }
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
    return {
      reply: data.reply ?? data.message ?? 'Parameters noted. Run the analysis when ready.',
      report_ready: Boolean(data.report_ready),
      report_missing_data: Boolean(data.report_missing_data),
    };
  } catch (err) {
    return {
      reply: `Chat request failed: ${err.message}.`,
      report_ready: false,
      report_missing_data: false,
    };
  }
}

function appendChatMsg(role, text) {
  const win = document.getElementById('chatWindow');
  const bubble = createElem('div', `msg msg--${role === 'bot' ? 'bot' : 'user'}`);
  bubble.textContent = text;
  win.appendChild(bubble);
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
  const loaded = document.getElementById('csvLoaded');
  if (!file.name.toLowerCase().endsWith('.csv') || !ALLOWED_CSV_TYPES.has(file.type)) {
    state.csvFile = null;
    loaded.textContent = 'Only CSV files are allowed.';
    loaded.hidden = false;
    return;
  }
  if (file.size > MAX_CSV_SIZE_BYTES) {
    state.csvFile = null;
    loaded.textContent = `CSV file is too large. Maximum allowed size is ${Math.round(MAX_CSV_SIZE_BYTES / 1024 / 1024)} MB.`;
    loaded.hidden = false;
    return;
  }
  state.csvFile = file;
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

  let result;

  // CSV mode uses multipart/form-data endpoint
  if (state.mode === 'csv') {
    result = await fetchCsvAnalysis();
  } else {
    const payload = buildPayload();
    result = await fetchAnalysis(payload);
  }

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

  const displayZone =
    !(typeof result.score === 'number' && Number.isFinite(result.score)) && result.status === 'UNSAFE'
      ? 'UNSAFE'
      : result.zone;

  // Show the real engine WQI value; unsafe/pending states do not have one
  if (typeof result.score === 'number' && Number.isFinite(result.score)) {
    animateCounter('wqiNumber', result.score, 900);
  } else {
    document.getElementById('wqiNumber').textContent = 'N/A';
  }
  const denom = document.querySelector('.wqi-denom');
  if (denom) denom.textContent = typeof result.score === 'number' && Number.isFinite(result.score) ? '/ 100' : '';

  // Zone pill
  const zs   = ZONE_STYLE[displayZone] ?? ZONE_STYLE['ACCEPTABLE'];
  const pill = document.getElementById('zonePill');
  pill.textContent     = displayZone;
  pill.style.background = zs.bg;
  pill.style.color      = zs.color;
  pill.style.border     = `1px solid ${zs.border}`;

  // Zone spectrum bar — highlight active segment
  ZONE_SEG_IDS.forEach(z => {
    const seg = document.getElementById(`zs${z}`);
    const isActive = z.toUpperCase() === displayZone || (displayZone === 'UNSAFE' && z.toUpperCase() === 'DEFICIENT');
    seg.classList.toggle('active', isActive);
  });

  // Parameter breakdown
  const breakdown = document.getElementById('breakdown');
  breakdown.replaceChildren();
  for (const p of result.params ?? []) {
    const c = ZONE_STYLE[p.zone]?.color ?? '#6a8aaa';
    const row = createElem('div', 'param-row');
    const dot = createElem('div', 'pr-dot');
    dot.style.background = c;
    const name = createElem('div', 'pr-name', p.name ?? '');
    const value = createElem('div', 'pr-value', `${p.value ?? ''}${p.unit ? ` ${p.unit}` : ''}`);
    value.style.color = c;
    row.append(dot, name, value);
    breakdown.appendChild(row);
  }

  // Confidence details
  const confidence = result.confidence_details ?? {
    score: Number(result.confidence ?? 0),
    summary: 'Confidence details are unavailable.',
    reason: '',
    missing_params: [],
    provided_count: 0,
    expected_count: 0,
  };
  const confidenceWrap = document.getElementById('confidenceDetails');
  confidenceWrap.replaceChildren();
  confidenceWrap.appendChild(createElem('div', 'confidence-score', `Confidence: ${Math.round((confidence.score ?? 0) * 100)}%`));
  confidenceWrap.appendChild(createElem('div', 'confidence-summary', confidence.summary ?? ''));
  if (confidence.reason) {
    confidenceWrap.appendChild(createElem('div', 'confidence-reason', confidence.reason));
  }
  if (Array.isArray(confidence.missing_params) && confidence.missing_params.length) {
    confidenceWrap.appendChild(
      createElem('div', 'confidence-missing', `Missing parameters: ${confidence.missing_params.join(', ')}`),
    );
  }

  // Flags
  const ICONS = { ok: '✓', warn: '!', bad: '✗' };
  const flags = document.getElementById('flagsList');
  flags.replaceChildren();
  for (const f of result.flags ?? []) {
    const flag = createElem('div', `flag flag--${f.type}`);
    const icon = createElem('em', 'flag-icon', ICONS[f.type] ?? '·');
    const msg = createElem('span', '', f.msg ?? '');
    flag.append(icon, msg);
    flags.appendChild(flag);
  }
}

/* ════════════════════════════════════════════
   COUNTER ANIMATION
════════════════════════════════════════════ */
function animateCounter(elId, target, durationMs) {
  const el = document.getElementById(elId);
  if (!(typeof target === 'number' && Number.isFinite(target))) {
    el.textContent = 'N/A';
    return;
  }
  const start = performance.now();
  const current = Number.parseFloat(el.textContent) || 0;
  const decimals = Number.isInteger(target) ? 0 : 2;

  function tick(now) {
    const progress = Math.min((now - start) / durationMs, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const value = current + (target - current) * eased;
    el.textContent = decimals ? value.toFixed(decimals) : Math.round(value);
    if (progress < 1) requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}

/* ════════════════════════════════════════════
   DOWNLOAD REPORT
════════════════════════════════════════════ */
async function downloadReport() {
  if (!state.lastResult) return;

  try {
    if (state.mode === 'csv' && state.csvFile) {
      const form = new FormData();
      form.append('file', state.csvFile);
      await requestPdf(
        `${API_BASE}/api/report/csv?profile=${encodeURIComponent(state.profile)}`,
        { method: 'POST', body: form },
        `UPD_Batch_Report_${Date.now()}.pdf`,
      );
      return;
    }

    const payload = buildPayload();
    payload.meta = {
      sample_id: `WEB-${Date.now()}`,
      location: PROFILE_DISPLAY_NAMES[state.profile],
    };
    await requestPdf(
      `${API_BASE}/api/report`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      `UPD_Report_${state.profile}_${Date.now()}.pdf`,
    );
  } catch (err) {
    renderResults(buildErrorResult(`Report download failed: ${err.message}`));
  }
}

/* ════════════════════════════════════════════
   INIT
════════════════════════════════════════════ */
(function init() {
  // Build initial params grid
  buildParamsGrid('drinking');

  // Wire profile cards via event delegation (belt-and-suspenders alongside onclick attrs)
  const profileGrid = document.getElementById('profileGrid');
  if (profileGrid) {
    profileGrid.addEventListener('click', (e) => {
      const card = e.target.closest('.profile-card');
      if (!card) return;
      const profile = card.dataset.profile;
      if (profile && profile !== state.profile) selectProfile(card, profile);
    });
  }

  // Notify backend of initial profile on page load
  notifyProfileChange('drinking');

  // Log backend mode
  fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(2000) })
    .then(async (r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      console.info('[UPD] Backend online', data);
    })
    .catch((err) => console.warn('[UPD] Backend health check failed:', err.message));
})();
