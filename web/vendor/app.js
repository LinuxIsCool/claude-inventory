'use strict';

const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));
const errHost = $('#err-host');

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Single chokepoint for HTML insertion. All callers MUST construct strings
// with escapeHtml() applied to every dynamic value. Future: swap to DOMPurify.
function setHtml(el, html) {
  if (!el) return;
  el.innerHTML = html;  // eslint-disable-line no-unsanitized/property
}

function fmtBytes(n) {
  if (n == null || isNaN(n)) return '';
  const units = ['B','KB','MB','GB','TB','PB'];
  let i = 0, v = Number(n);
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2) + ' ' + units[i];
}

function privacyBadge(cls) {
  if (!cls) return '';
  const safe = escapeHtml(cls);
  return `<span class="badge badge-${safe}">${safe}</span>`;
}

// Mode-B mount base: in standalone (Mode A) pathname is '/', base ''.
// When mounted at /inventory/ (Mode B) base becomes '/inventory' so
// root-absolute API paths keep the mount prefix instead of dropping it.
const API_BASE = location.pathname.replace(/\/(index\.html)?$/, '');

async function api(path) {
  try {
    const url = path.startsWith('/') ? API_BASE + path : path;
    const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  } catch (e) {
    setHtml(errHost, `<div class="err">API error on ${escapeHtml(path)}: ${escapeHtml(e.message)}</div>`);
    throw e;
  }
}

function debounce(fn, ms) {
  let t;
  return function() {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, arguments), ms);
  };
}

// ──────────────────────────── tab routing ────────────────────────────

const TAB_LOADED = new Set();

function showTab(name) {
  $$('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $$('.panel').forEach(p => p.classList.toggle('hidden', p.id !== `panel-${name}`));
  if (!TAB_LOADED.has(name)) {
    TAB_LOADED.add(name);
    loadTab(name);
  }
  window.location.hash = name;
}

async function loadTab(name) {
  switch (name) {
    case 'overview':      return loadOverview();
    case 'people':        return loadPeople();
    case 'organizations': return loadOrganizations();
    case 'ventures':      return loadVentures();
    case 'hardware':      return loadHardware();
    case 'links':         return loadLinks();
    case 'relationships': return loadRelationships();
  }
}

$('#tabs').addEventListener('click', e => {
  const btn = e.target.closest('button');
  if (btn) showTab(btn.dataset.tab);
});

// ──────────────────────────── header (global, tab-independent) ────────────────────────────
// Cached overview payload so we fetch it once on boot for the header,
// then reuse for the Overview tab if/when it's clicked.
let _overviewCache = null;

async function loadHeader() {
  if (_overviewCache) return _overviewCache;
  let data;
  try {
    data = await api('/api/overview');
  } catch (e) {
    $('#header-counts').textContent = 'overview unavailable';
    $('#header-schema').textContent = 'v?';
    throw e;
  }
  _overviewCache = data;
  const c = data.counts || {};
  const hwTotal = (c.drive||0)+(c.machine||0)+(c.mobile||0)+(c.network||0)+(c.venue||0)+(c.peripheral||0);
  // Header
  $('#header-counts').textContent = `${c.TOTAL||0} assets · ${c.identity_links||0} links`;
  $('#header-schema').textContent = `v${data.schema_version}`;
  // Sidebar pills — also tab-independent
  $('#pill-overview').textContent = c.TOTAL || 0;
  $('#pill-people').textContent = c.person || 0;
  $('#pill-orgs').textContent = c.organization || 0;
  $('#pill-ventures').textContent = c.venture || 0;
  $('#pill-hardware').textContent = hwTotal;
  $('#pill-links').textContent = c.identity_links || 0;
  $('#pill-rels').textContent = c.relationships || 0;
  return data;
}

// ──────────────────────────── overview ────────────────────────────

async function loadOverview() {
  const data = await loadHeader();
  const c = data.counts || {};
  const hwTotal = (c.drive||0)+(c.machine||0)+(c.mobile||0)+(c.network||0)+(c.venue||0)+(c.peripheral||0);
  const cards = [
    ['People',         c.person || 0,        `${c.identity_links || 0} identity links`,       'accent-blue'],
    ['Organizations',  c.organization || 0,  `${c.venture || 0} ventures backed`,             'accent-purple'],
    ['Ventures',       c.venture || 0,       'lifecycle stages',                              'accent-green'],
    ['Hardware',       hwTotal,              `${c.drive||0} drives · ${c.machine||0} machines`, 'accent-yellow'],
    ['Identity Links', c.identity_links || 0, '8 protocols',                                  'accent-pink'],
    ['Relationships',  c.relationships || 0,  'edges',                                        'accent-teal'],
    ['Total Assets',   c.TOTAL || 0,          'all classes',                                  'accent-blue'],
    ['Schema',         `v${data.schema_version}`, 'migration version',                        'accent-purple'],
  ];
  setHtml($('#overview-cards'), cards.map(([h, big, sub, color]) => `
    <div class="ui-card">
      <div class="font-mono text-[10px] text-gray-500 uppercase tracking-wider mb-2">${escapeHtml(h)}</div>
      <div class="font-pixel text-${color} text-xl">${escapeHtml(String(big))}</div>
      <div class="font-mono text-[11px] text-gray-500 mt-2">${escapeHtml(sub)}</div>
    </div>
  `).join(''));
  $('#overview-meta').textContent =
    `${c.TOTAL || 0} assets · ${c.identity_links || 0} links · ${c.relationships || 0} edges · schema v${data.schema_version}`;

  // Header + sidebar pills are now populated by loadHeader() (called above).
  // Keep this block intentionally empty — see loadHeader().

  // Privacy distribution
  const pb = data.privacy_breakdown || {};
  const total = Object.values(pb).reduce((a,b)=>a+b,0) || 1;
  setHtml($('#overview-privacy'), ['public','private','restricted','indigenous-sui-generis'].map(cls => {
    const n = pb[cls] || 0;
    const pct = (n/total*100).toFixed(0);
    const fillClass = cls === 'restricted' ? 'warn' : cls === 'indigenous-sui-generis' ? 'crit' : '';
    return `
      <div class="mb-2">
        <div class="flex items-center justify-between mb-1">
          <div class="flex items-center gap-2">
            ${privacyBadge(cls)}
            <span class="font-mono text-xs text-gray-300">${escapeHtml(String(n))}</span>
            <span class="font-mono text-[10px] text-gray-500">${escapeHtml(pct)}%</span>
          </div>
        </div>
        <div class="bar"><div class="bar-fill ${escapeHtml(fillClass)}" style="width:${escapeHtml(pct)}%"></div></div>
      </div>`;
  }).join(''));

  // Recent additions
  setHtml($('#overview-recent'), (data.recent_additions || []).map(r => `
    <div class="flex items-center justify-between py-1.5 border-b border-surface-border/40 last:border-0">
      <div class="flex items-center gap-2 min-w-0">
        <span class="pill">${escapeHtml(r.asset_type)}</span>
        <span class="font-mono text-xs text-gray-300 truncate">${escapeHtml(r.name)}</span>
      </div>
      <span class="font-mono text-[10px] text-gray-600 shrink-0 ml-2">${escapeHtml(r.updated_at || r.created_at || '')}</span>
    </div>
  `).join(''));
}

// ──────────────────────────── people ────────────────────────────

async function loadPeople(query='') {
  const data = await api('/api/people' + (query || ''));
  if (!loadPeople._orgsLoaded) {
    const orgsData = await api('/api/organizations');
    const orgsel = $('#people-org-filter');
    for (const o of (orgsData.organizations || []).sort((a,b)=>(a.legal_name||'').localeCompare(b.legal_name||''))) {
      const opt = document.createElement('option');
      opt.value = o.asset_id;
      opt.textContent = o.legal_name;
      orgsel.appendChild(opt);
    }
    loadPeople._orgsLoaded = true;
  }
  renderPeopleTable(data.people || []);
}

function renderPeopleTable(rows) {
  if (!rows.length) {
    setHtml($('#people-table-host'), `<div class="empty">No people match.<div class="hint">Try clearing filters.</div></div>`);
    return;
  }
  setHtml($('#people-table-host'), `
    <table class="ui-table">
      <thead><tr>
        <th>Name</th><th>Role</th><th>Primary Org</th><th>Class</th>
        <th class="num">Links</th><th>Privacy</th><th>Anchor</th>
      </tr></thead>
      <tbody>
        ${rows.map(p => `
          <tr class="clickable" data-asset-id="${escapeHtml(p.asset_id)}">
            <td>
              <div class="font-mono text-xs">${escapeHtml(p.full_name)}</div>
              ${p.preferred_name && p.preferred_name !== p.full_name
                ? `<div class="font-mono text-[10px] text-gray-500">${escapeHtml(p.preferred_name)}</div>`
                : ''}
            </td>
            <td class="text-gray-400">${escapeHtml(p.role || '')}</td>
            <td class="text-gray-400">${escapeHtml(p.primary_org_short || p.primary_org_name || '')}</td>
            <td><span class="pill">${escapeHtml(p.relationship_class || '')}</span></td>
            <td class="num text-accent-blue">${escapeHtml(String(p.link_count || 0))}</td>
            <td>${privacyBadge(p.privacy_class)}</td>
            <td>${p.anchor_persona_id ? `<span class="badge badge-anchor">${escapeHtml(p.anchor_persona_id)}</span>` : ''}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>`);
  $$('#people-table-host tr[data-asset-id]').forEach(tr => {
    tr.addEventListener('click', () => showPersonDetail(tr.dataset.assetId));
  });
}

function peopleQueryString() {
  const params = new URLSearchParams();
  const org = $('#people-org-filter').value;
  const cls = $('#people-class-filter').value;
  const priv = $('#people-privacy-filter').value;
  const q = $('#people-q').value.trim();
  if (org) params.set('org_id', org);
  if (cls) params.set('relationship_class', cls);
  if (priv) params.set('privacy_class', priv);
  if (q) params.set('q', q);
  const s = params.toString();
  return s ? '?' + s : '';
}

['people-org-filter','people-class-filter','people-privacy-filter'].forEach(id => {
  $('#' + id).addEventListener('change', () => loadPeople(peopleQueryString()));
});
$('#people-q').addEventListener('input', debounce(() => loadPeople(peopleQueryString()), 250));

async function showPersonDetail(asset_id) {
  const p = await api('/api/people/' + encodeURIComponent(asset_id));
  const linksByProto = {};
  for (const l of (p.identity_links || [])) {
    (linksByProto[l.protocol] = linksByProto[l.protocol] || []).push(l);
  }
  const linksHtml = Object.entries(linksByProto).map(([proto, list]) => `
    <div class="mb-3">
      <div class="font-pixel text-[9px] text-accent-blue tracking-wider mb-1.5">${escapeHtml(proto.toUpperCase())}</div>
      ${list.map(l => `
        <div class="ml-3 py-1 font-mono text-xs flex items-center gap-2 flex-wrap">
          ${l.is_primary ? '<span class="badge badge-primary">primary</span>' : ''}
          ${l._masked ? '<span class="badge badge-masked">masked</span>' : ''}
          <span class="text-gray-200">${escapeHtml(l.identifier)}</span>
          ${privacyBadge(l.privacy_class)}
          ${l.notes ? `<div class="w-full text-[10px] text-gray-500 ml-1 mt-0.5">${escapeHtml(l.notes)}</div>` : ''}
        </div>
      `).join('')}
    </div>
  `).join('');
  const relsHtml = (p.relationships || []).map(r => `
    <div class="py-2 border-b border-surface-border/40 last:border-0 font-mono text-xs">
      ${r.from_asset === asset_id
        ? `<span class="text-accent-green">→</span> <span class="text-gray-200">${escapeHtml(r.to_name || r.to_asset)}</span>`
        : `<span class="text-accent-yellow">←</span> <span class="text-gray-200">${escapeHtml(r.from_name || r.from_asset)}</span>`}
      <span class="pill mx-2">${escapeHtml(r.rel_type)}</span>
      <span class="text-gray-500 text-[10px]">strength=${escapeHtml(String(r.strength))}</span>
      ${r.notes ? `<div class="text-gray-500 text-[10px] mt-1 ml-4">${escapeHtml(r.notes)}</div>` : ''}
    </div>
  `).join('');
  const html = `
    <div class="font-pixel text-accent-purple text-xs tracking-wider mb-1">PERSON</div>
    <h2 class="font-pixel text-accent-green text-base tracking-wider mb-1">${escapeHtml(p.full_name).toUpperCase()}</h2>
    <div class="font-mono text-xs text-gray-400 mb-4">${escapeHtml(p.role || '')} ${p.primary_org_name ? '· ' + escapeHtml(p.primary_org_name) : ''}</div>
    <div class="kv">
      <div class="k">asset_id</div><div>${escapeHtml(p.asset_id)}</div>
      <div class="k">preferred</div><div>${escapeHtml(p.preferred_name || '—')}</div>
      <div class="k">privacy</div><div>${privacyBadge(p.privacy_class)}</div>
      <div class="k">class</div><div>${escapeHtml(p.relationship_class || '—')}</div>
      <div class="k">strength</div><div>${escapeHtml(String(p.relationship_strength ?? '—'))}</div>
      ${p.anchor_persona_id ? `<div class="k">anchor</div><div><span class="badge badge-anchor">${escapeHtml(p.anchor_persona_id)}</span></div>` : ''}
      ${p.spelling_lock ? `<div class="k">spelling</div><div class="text-accent-yellow text-[11px]">${escapeHtml(p.spelling_lock)}</div>` : ''}
    </div>
    ${p.notes ? `
      <div class="mt-5">
        <div class="font-pixel text-[9px] text-accent-purple tracking-wider mb-2">NOTES</div>
        <div class="font-mono text-xs text-gray-300 leading-relaxed">${escapeHtml(p.notes)}</div>
      </div>` : ''}
    <div class="mt-5">
      <div class="font-pixel text-[9px] text-accent-purple tracking-wider mb-2">IDENTITY LINKS (${escapeHtml(String(p.identity_links?.length || 0))})</div>
      ${linksHtml || '<div class="empty">no links yet.</div>'}
    </div>
    <div class="mt-5">
      <div class="font-pixel text-[9px] text-accent-purple tracking-wider mb-2">RELATIONSHIPS (${escapeHtml(String(p.relationships?.length || 0))})</div>
      ${relsHtml || '<div class="empty">no edges yet.</div>'}
    </div>
  `;
  setHtml($('#detail-content'), html);
  $('#detail-overlay').classList.add('open');
}

$('#detail-close').addEventListener('click', () => $('#detail-overlay').classList.remove('open'));
$('#detail-overlay').addEventListener('click', e => {
  if (e.target === $('#detail-overlay')) $('#detail-overlay').classList.remove('open');
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') $('#detail-overlay').classList.remove('open');
});

// ──────────────────────────── organizations ────────────────────────────

async function loadOrganizations() {
  const data = await api('/api/organizations' + orgQueryString());
  renderOrgsTable(data.organizations || []);
}
function orgQueryString() {
  const t = $('#org-type-filter').value;
  return t ? `?type=${encodeURIComponent(t)}` : '';
}
function renderOrgsTable(rows) {
  if (!rows.length) {
    setHtml($('#orgs-table-host'), `<div class="empty">No organizations match.</div>`);
    return;
  }
  setHtml($('#orgs-table-host'), `
    <table class="ui-table"><thead><tr>
      <th>Name</th><th>Type</th><th class="num">Members</th><th class="num">Ventures</th>
      <th>Headquarters</th><th>Website</th>
    </tr></thead><tbody>
      ${rows.map(o => `<tr>
        <td>
          <div class="font-mono text-xs">${escapeHtml(o.legal_name)}</div>
          ${o.short_name ? `<div class="font-mono text-[10px] text-gray-500">${escapeHtml(o.short_name)}</div>` : ''}
        </td>
        <td><span class="pill">${escapeHtml(o.org_type || '—')}</span></td>
        <td class="num text-accent-blue">${escapeHtml(String(o.member_count || 0))}</td>
        <td class="num text-accent-green">${escapeHtml(String(o.venture_count || 0))}</td>
        <td class="text-gray-400">${escapeHtml(o.headquarters || '')}</td>
        <td class="mono">${o.website ? `<a href="${escapeHtml(o.website)}" target="_blank" rel="noopener">${escapeHtml(o.website)}</a>` : ''}</td>
      </tr>`).join('')}
    </tbody></table>`);
}
$('#org-type-filter').addEventListener('change', () => loadOrganizations());

// ──────────────────────────── ventures ────────────────────────────

async function loadVentures() {
  const stage = $('#venture-stage-filter').value;
  const data = await api(`/api/ventures?stage=${encodeURIComponent(stage)}`);
  renderVenturesTable(data.ventures || []);
}
function renderVenturesTable(rows) {
  if (!rows.length) {
    setHtml($('#ventures-table-host'), `<div class="empty">No ventures match this stage.</div>`);
    return;
  }
  setHtml($('#ventures-table-host'), `
    <table class="ui-table"><thead><tr>
      <th>Name</th><th>Stage</th><th>Primary Org</th><th>Started</th><th>Last Milestone</th><th>Slug</th>
    </tr></thead><tbody>
      ${rows.map(v => `<tr>
        <td><div class="font-mono text-xs">${escapeHtml(v.name)}</div></td>
        <td><span class="badge badge-active">${escapeHtml(v.stage || '—')}</span></td>
        <td class="text-gray-400">${escapeHtml(v.primary_org_short || v.primary_org_name || '')}</td>
        <td class="mono">${escapeHtml(v.started_at || '')}</td>
        <td class="mono">${escapeHtml(v.last_milestone_at || '')}</td>
        <td class="mono text-gray-500">${escapeHtml(v.slug || '')}</td>
      </tr>`).join('')}
    </tbody></table>`);
}
$('#venture-stage-filter').addEventListener('change', () => loadVentures());

// ──────────────────────────── hardware ────────────────────────────

// Selected hardware row (drawer state). MUST be declared — it is read in
// loadHardware()'s row render (line ~409) before any selection happens.
// Under 'use strict' an undeclared read throws ReferenceError and aborts
// the whole render, leaving the Hardware tab blank.
let _hwSelectedAssetId = null;

async function loadHardware() {
  const t = $('#hw-type-filter').value;
  const data = await api('/api/hardware' + (t ? `?type=${encodeURIComponent(t)}` : ''));
  const grouped = data.grouped || {};
  const html = Object.entries(grouped).map(([type, rows]) => `
    <div class="ui-card !p-0 overflow-hidden">
      <div class="px-4 py-2 border-b border-surface-border bg-surface flex items-center justify-between">
        <div class="font-pixel text-[10px] text-accent-yellow tracking-wider">${escapeHtml(type.toUpperCase())}</div>
        <span class="pill">${escapeHtml(String(rows.length))}</span>
      </div>
      <table class="ui-table"><thead><tr>
        <th>Name</th><th>Manufacturer</th><th>Model</th><th>Status</th><th>Location</th>
        ${type === 'drive' ? '<th>Capacity</th>' : ''}
        <th>Last seen</th>
      </tr></thead><tbody>
        ${rows.map(h => `<tr class="clickable ${h.asset_id === _hwSelectedAssetId ? 'selected' : ''}" data-asset-id="${escapeHtml(h.asset_id)}">
          <td><div class="font-mono text-xs">${escapeHtml(h.name)}</div></td>
          <td class="text-gray-400">${escapeHtml(h.manufacturer || '')}</td>
          <td class="text-gray-400">${escapeHtml(h.model || '')}</td>
          <td>${renderStatusBadge(h.live_status || h.status)}</td>
          <td class="text-gray-400">${escapeHtml(h.location || '')}</td>
          ${type === 'drive' ? `<td>${renderDriveCapacity(h.capacity, h.connected)}</td>` : ''}
          <td class="mono">${escapeHtml(h.last_seen || '')}</td>
        </tr>`).join('')}
      </tbody></table>
    </div>
  `).join('');
  setHtml($('#hardware-host'), html || `<div class="empty">No hardware assets registered.</div>`);
}
function renderStatusBadge(status) {
  if (!status) return '<span class="badge badge-pending">pending</span>';
  let cls;
  if (status === 'connected')                        cls = 'connected';
  else if (status === 'active')                      cls = 'active';
  else if (status === 'retired' || status === 'wiped') cls = 'masked';
  else                                               cls = 'pending';
  return `<span class="badge badge-${cls}">${escapeHtml(status)}</span>`;
}
function renderDriveCapacity(c, connected) {
  if (!c) return '';
  const total = Number(c.total_bytes || c.size_bytes || 0);
  const used  = Number(c.used_bytes || 0);
  // free comes from live statvfs when connected; else fall back to total-used
  const free  = c.free_bytes != null ? Number(c.free_bytes)
              : total ? Math.max(0, total - used) : 0;
  const pctRaw = c.capacity_pct;
  const pct = pctRaw != null ? Number(pctRaw)
             : total ? Math.round(used/total*100) : 0;
  // Bar colour reflects pressure (used%). High used = warn/crit.
  let cls = pct >= 90 ? 'crit' : pct >= 75 ? 'warn' : '';
  // Live-data tag pulses the bar to signal "this is real-time"
  if (c.live) cls += ' live';
  // Display value = REMAINING space (the unfilled portion of the bar).
  const remaining = total ? fmtBytes(free) : '—';
  return `
    <div class="flex items-center gap-2">
      <div class="bar" title="${escapeHtml(String(pct))}% used"><div class="bar-fill ${escapeHtml(cls.trim())}" style="width:${escapeHtml(String(pct))}%"></div></div>
      <span class="font-mono text-[10px] ${connected ? 'text-accent-teal' : 'text-gray-500'}">${escapeHtml(remaining)}${total ? ' free' : ''}</span>
    </div>
    ${total ? `<div class="font-mono text-[10px] text-gray-500 mt-0.5">${escapeHtml(fmtBytes(used))} used / ${escapeHtml(fmtBytes(total))}</div>` : ''}`;
}
$('#hw-type-filter').addEventListener('change', () => loadHardware());
$('#hw-internality-filter').addEventListener('change', () => loadHardware());
$('#hw-status-filter').addEventListener('change', () => loadHardware());
$('#hw-location-filter').addEventListener('change', () => loadHardware());
$('#hw-q').addEventListener('input', debounce(() => loadHardware(), 250));
$('#hw-reset').addEventListener('click', () => {
  $('#hw-type-filter').value = '';
  $('#hw-internality-filter').value = '';
  $('#hw-status-filter').value = '';
  $('#hw-location-filter').value = '';
  $('#hw-q').value = '';
  loadHardware();
});
// Row click → open drawer with detail
$('#hardware-host').addEventListener('click', e => {
  const tr = e.target.closest('tr.clickable');
  if (!tr) return;
  const id = tr.dataset.assetId;
  if (id) showHardwareDetail(id);
});
$('#hw-drawer-close').addEventListener('click', () => {
  $('#hw-drawer').classList.remove('open');
  _hwSelectedAssetId = null;
  // re-render to drop the selected-row highlight (cheap: drop highlight w/o refetch)
  $$('#hardware-host tr.clickable.selected').forEach(r => r.classList.remove('selected'));
});
// Esc closes drawer
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && $('#hw-drawer').classList.contains('open')) {
    $('#hw-drawer-close').click();
  }
});

async function showHardwareDetail(assetId) {
  _hwSelectedAssetId = assetId;
  // Highlight clicked row
  $$('#hardware-host tr.clickable').forEach(r => {
    r.classList.toggle('selected', r.dataset.assetId === assetId);
  });
  $('#hw-drawer').classList.add('open');
  setHtml($('#hw-drawer-content'), `<div class="empty" style="padding: 1rem">Loading…</div>`);
  let d;
  try {
    d = await api('/api/hardware/' + encodeURIComponent(assetId));
  } catch (e) {
    setHtml($('#hw-drawer-content'), `<div class="err">Failed to load: ${escapeHtml(e.message)}</div>`);
    return;
  }
  setHtml($('#hw-drawer-content'), renderHardwareDetail(d));
}

function _kv(label, value, mono = false) {
  if (value == null || value === '') return '';
  return `<div class="k">${escapeHtml(label)}</div><div class="${mono ? 'mono' : ''}">${escapeHtml(String(value))}</div>`;
}

function renderHardwareDetail(d) {
  const cap = d.capacity || {};
  const total = Number(cap.total_bytes || cap.size_bytes || 0);
  const used  = Number(cap.used_bytes || 0);
  const free  = cap.free_bytes != null ? Number(cap.free_bytes) : (total ? Math.max(0, total - used) : 0);
  const pct   = cap.capacity_pct != null ? Number(cap.capacity_pct) : (total ? Math.round(used/total*100) : 0);
  const isDrive = d.asset_type === 'drive';
  return `
    <div class="mb-3">
      <div class="font-pixel text-[11px] text-accent-purple tracking-wider mb-1">${escapeHtml((d.asset_type || '').toUpperCase())}</div>
      <div class="font-mono text-sm text-white">${escapeHtml(d.name || '(unnamed)')}</div>
      <div class="mt-2 flex gap-2 flex-wrap">
        ${renderStatusBadge(d.live_status || d.status)}
        ${d.connected ? '<span class="badge badge-connected">live</span>' : ''}
        ${d.attached && !d.connected ? '<span class="badge badge-restricted">attached</span>' : ''}
        ${isDrive && d.internality ? `<span class="badge badge-pending">${escapeHtml(d.internality)}</span>` : ''}
      </div>
    </div>
    ${isDrive && total ? `
      <div class="ui-card !p-3 mb-3">
        <div class="font-pixel text-[9px] text-accent-purple tracking-wider mb-2">CAPACITY</div>
        <div class="flex items-center gap-2 mb-2">
          <div class="bar flex-1"><div class="bar-fill ${pct >= 90 ? 'crit' : pct >= 75 ? 'warn' : ''} ${cap.live ? 'live' : ''}" style="width:${escapeHtml(String(pct))}%"></div></div>
          <span class="font-mono text-xs text-accent-teal">${escapeHtml(fmtBytes(free))} free</span>
        </div>
        <div class="font-mono text-[11px] text-gray-400">
          ${escapeHtml(fmtBytes(used))} used / ${escapeHtml(fmtBytes(total))} total · ${escapeHtml(String(pct))}%
          ${cap.live ? ' · <span class="text-accent-teal">live</span>' : ''}
        </div>
      </div>` : ''}
    <div class="ui-card !p-3 mb-3">
      <div class="font-pixel text-[9px] text-accent-purple tracking-wider mb-2">METADATA</div>
      <div class="kv">
        ${_kv('asset_id', d.asset_id, true)}
        ${_kv('manufacturer', d.manufacturer)}
        ${_kv('model', d.model)}
        ${_kv('location', d.location)}
        ${_kv('last_seen', d.last_seen, true)}
        ${_kv('created_at', d.created_at, true)}
      </div>
    </div>
    ${isDrive ? `
      <div class="ui-card !p-3 mb-3">
        <div class="font-pixel text-[9px] text-accent-purple tracking-wider mb-2">DRIVE</div>
        <div class="kv">
          ${_kv('interface', d.interface)}
          ${_kv('form_factor', d.form_factor)}
          ${_kv('filesystem', d.filesystem)}
          ${_kv('mount_point', d.mount_point, true)}
          ${_kv('mount_uuid', d.mount_uuid, true)}
          ${_kv('usage_class', d.usage_class)}
          ${_kv('encryption', d.encryption)}
          ${_kv('smart_health', d.smart_health)}
          ${_kv('backup_status', d.backup_status)}
          ${_kv('backup_target', d.backup_target, true)}
        </div>
      </div>` : ''}
    ${d.notes ? `
      <div class="ui-card !p-3 mb-3">
        <div class="font-pixel text-[9px] text-accent-purple tracking-wider mb-2">NOTES</div>
        <div class="font-mono text-xs text-gray-300 whitespace-pre-wrap">${escapeHtml(d.notes)}</div>
      </div>` : ''}
    ${(d.observations && d.observations.length) ? `
      <div class="ui-card !p-3">
        <div class="font-pixel text-[9px] text-accent-purple tracking-wider mb-2">RECENT OBSERVATIONS (${d.observations.length})</div>
        <div class="font-mono text-[11px] space-y-1">
          ${d.observations.slice(0, 10).map(o => `
            <div class="flex justify-between gap-2">
              <span class="text-gray-500">${escapeHtml(o.ts || '')}</span>
              <span class="text-gray-300">${escapeHtml(o.metric)}</span>
              <span class="text-gray-400 text-right">${escapeHtml(String(o.value_num != null ? o.value_num : (o.value_text || '')))}</span>
            </div>`).join('')}
        </div>
      </div>` : ''}
  `;
}

// ──────────────────────────── identity links ────────────────────────────

async function loadLinks() {
  if (!loadLinks._protosLoaded) {
    const data = await api('/api/identity-protocols');
    const sel = $('#link-protocol-filter');
    for (const p of (data.protocols || [])) {
      const opt = document.createElement('option');
      opt.value = p.protocol;
      opt.textContent = `${p.protocol} (${p.n})`;
      sel.appendChild(opt);
    }
    loadLinks._protosLoaded = true;
  }
  const params = new URLSearchParams();
  const proto = $('#link-protocol-filter').value;
  const priv = $('#link-privacy-filter').value;
  const q = $('#link-q').value.trim();
  if (proto) params.set('protocol', proto);
  if (priv) params.set('privacy_class', priv);
  if (q) params.set('q', q);
  const data = await api('/api/identity-links' + (params.toString() ? '?' + params : ''));
  renderLinksTable(data.identity_links || []);
}
function renderLinksTable(rows) {
  if (!rows.length) {
    setHtml($('#links-table-host'), `<div class="empty">No identity links match.<div class="hint">Sui-generis rows are hard-rejected at the serializer.</div></div>`);
    return;
  }
  setHtml($('#links-table-host'), `
    <table class="ui-table"><thead><tr>
      <th>Asset</th><th>Protocol</th><th>Identifier</th><th>Primary</th>
      <th>Privacy</th><th>Verified</th><th class="num">Conf</th>
    </tr></thead><tbody>
      ${rows.map(l => `<tr class="${l.asset_id?.startsWith('person-') ? 'clickable' : ''}" data-asset-id="${escapeHtml(l.asset_id)}">
        <td><div class="font-mono text-xs">${escapeHtml(l.asset_name || l.asset_id)}</div></td>
        <td><span class="pill">${escapeHtml(l.protocol)}</span></td>
        <td class="mono">${escapeHtml(l.identifier)} ${l._masked ? '<span class="badge badge-masked ml-1">masked</span>' : ''}</td>
        <td>${l.is_primary ? '<span class="badge badge-primary">primary</span>' : ''}</td>
        <td>${privacyBadge(l.privacy_class)}</td>
        <td class="text-gray-400">${escapeHtml(l.verified_by || '')}</td>
        <td class="num text-accent-blue">${l.confidence != null ? escapeHtml(Number(l.confidence).toFixed(2)) : ''}</td>
      </tr>`).join('')}
    </tbody></table>`);
  $$('#links-table-host tr[data-asset-id]').forEach(tr => {
    if (tr.dataset.assetId.startsWith('person-')) {
      tr.addEventListener('click', () => showPersonDetail(tr.dataset.assetId));
    }
  });
}
['link-protocol-filter','link-privacy-filter'].forEach(id => {
  $('#' + id).addEventListener('change', () => loadLinks());
});
$('#link-q').addEventListener('input', debounce(() => loadLinks(), 250));

// ──────────────────────────── relationships ────────────────────────────

async function loadRelationships() {
  if (!loadRelationships._peopleLoaded) {
    const data = await api('/api/people');
    const sel = $('#rel-person-filter');
    for (const p of (data.people || [])) {
      const opt = document.createElement('option');
      opt.value = p.asset_id;
      opt.textContent = p.full_name;
      sel.appendChild(opt);
    }
    loadRelationships._peopleLoaded = true;
  }
  const person = $('#rel-person-filter').value;
  const data = await api('/api/relationships' + (person ? `?person=${encodeURIComponent(person)}` : ''));
  renderRelsTable(data.relationships || []);
}
function renderRelsTable(rows) {
  if (!rows.length) {
    setHtml($('#rels-table-host'), `<div class="empty">No relationships match.</div>`);
    return;
  }
  setHtml($('#rels-table-host'), `
    <table class="ui-table"><thead><tr>
      <th>From</th><th>Type</th><th>To</th>
      <th class="num">Strength</th><th class="num">Confidence</th>
      <th>Source</th><th>Notes</th>
    </tr></thead><tbody>
      ${rows.map(r => `<tr>
        <td><div class="font-mono text-xs">${escapeHtml(r.from_name || r.from_asset)}</div></td>
        <td><span class="pill">${escapeHtml(r.rel_type)}</span></td>
        <td><div class="font-mono text-xs">${escapeHtml(r.to_name || r.to_asset)}</div></td>
        <td class="num text-accent-green">${r.strength != null ? escapeHtml(Number(r.strength).toFixed(2)) : ''}</td>
        <td class="num text-accent-blue">${r.confidence != null ? escapeHtml(Number(r.confidence).toFixed(2)) : ''}</td>
        <td class="text-gray-500 text-[11px]">${escapeHtml(r.source || '')}</td>
        <td class="text-gray-400 text-[11px]">${escapeHtml(r.notes || '')}</td>
      </tr>`).join('')}
    </tbody></table>`);
}
$('#rel-person-filter').addEventListener('change', () => loadRelationships());

// ──────────────────────────── search ────────────────────────────

async function doSearch(q) {
  if (!q || q.length < 2) { $('#search-meta').textContent = ''; return; }
  const data = await api('/api/search?q=' + encodeURIComponent(q));
  $('#search-meta').textContent = `${data.total} matches`;
  const personHit = (data.results || []).find(r => r.kind === 'asset' && r.asset_type === 'person');
  if (personHit) showPersonDetail(personHit.asset_id);
}
$('#search-input').addEventListener('input', debounce(e => doSearch(e.target.value.trim()), 300));
$('#search-input').addEventListener('keydown', e => {
  if (e.key === 'Escape') { e.target.value = ''; $('#search-meta').textContent = ''; }
});

// ──────────────────────────── boot ────────────────────────────

function boot() {
  // Header + sidebar pills load regardless of initial tab — they're global.
  loadHeader().catch(err => console.error('loadHeader failed:', err));
  const initialTab = (window.location.hash || '#overview').slice(1);
  const valid = ['overview','people','organizations','ventures','hardware','links','relationships'];
  showTab(valid.includes(initialTab) ? initialTab : 'overview');
}
boot();
