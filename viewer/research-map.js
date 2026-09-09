import { buildSummary, epistemicBand, filterOrgans, layerOrder, profileState, validateFocus, validateRegistry } from './research-map-model.mjs';

const REGISTRY_URL = '../provenance/factual-space-pr2/data/matter_transfer_organ_registry_v0_1.json';
const FOCUS_URL = '../data/current_focus_v0_2.json';

const $ = (id) => document.getElementById(id);
const els = Object.fromEntries(['search','profile','layer','sourceState','profileBrief','layerGrid','empty','metrics','resultTitle','inspectTitle','inspectorBody','truthBoundary','truth-title','statusSummary','truthPills','registryIdentity','registryFile','focusFile'].map((id) => [id, $(id)]));
let registry = null;
let focus = null;
let selectedId = null;
let focusIndex = 0;

function titleCase(value) { return value.replaceAll('_',' ').replace(/\b\w/g, (c) => c.toUpperCase()); }
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }

function setSource(message, state = '') {
  els.sourceState.textContent = message;
  els.sourceState.className = `source-state ${state}`.trim();
}

function renderTruth() {
  const ceiling = focus?.claim_ceiling || registry?.canonical_claim_ceiling || 'Claim ceiling unavailable.';
  els['truth-title'].textContent = ceiling;
  if (focus) {
    els.statusSummary.textContent = `${titleCase(focus.status)} · ${focus.current_status?.summary?.replaceAll('_',' ') ?? 'status summary unavailable'}`;
    const status = focus.current_status || {};
    els.truthPills.innerHTML = Object.entries(status)
      .filter(([,value]) => typeof value === 'boolean')
      .slice(0,6)
      .map(([key,value]) => `<span class="pill ${value?'yes':'no'}">${escapeHtml(titleCase(key))}: ${value?'YES':'NO'}</span>`).join('');
  } else {
    els.statusSummary.textContent = 'Registry loaded. Current-focus file is unavailable; no current research status is inferred.';
    els.truthPills.innerHTML = '<span class="pill no">FOCUS: UNKNOWN</span>';
  }
  const boundary = registry?.truth_boundary ?? {};
  els.truthBoundary.innerHTML = Object.entries(boundary).map(([key,value]) => `<div class="floor-item">${escapeHtml(titleCase(key))}: <strong>${value === true ? 'required' : value === false ? 'forbidden' : escapeHtml(value)}</strong></div>`).join('');
}

function populateControls() {
  els.profile.innerHTML = '<option value="all">Complete research architecture</option>' + Object.entries(registry.assembly_profiles).map(([id,p]) => `<option value="${escapeHtml(id)}">${escapeHtml(titleCase(id))}${p.enabled===false?' · DISABLED':''}</option>`).join('');
  els.layer.innerHTML = '<option value="all">All layers</option>' + layerOrder(registry.organs).map((layer) => `<option value="${escapeHtml(layer)}">${escapeHtml(titleCase(layer))}</option>`).join('');
}

function currentVisible() {
  return filterOrgans(registry, { query: els.search.value, layer: els.layer.value, profileId: els.profile.value });
}

function renderInspector() {
  const organ = registry?.organs.find((item) => item.id === selectedId);
  if (!organ) {
    els.inspectTitle.textContent = 'Select an organ';
    els.inspectorBody.innerHTML = '<p class="muted">Choose a node to see its purpose, dependencies, hard gates, failure state and executable checks.</p>';
    return;
  }
  const band = epistemicBand(organ.epistemic_class);
  els.inspectTitle.textContent = `${organ.id} · ${titleCase(organ.name)}`;
  els.inspectorBody.innerHTML = `
    <span class="inspect-band">${escapeHtml(band)} · ${escapeHtml(organ.epistemic_class)}</span>
    <p class="inspect-purpose">${escapeHtml(organ.purpose)}</p>
    <div class="inspect-section"><h3>LAYER</h3><div>${escapeHtml(titleCase(organ.layer))}</div></div>
    <div class="inspect-section"><h3>DEPENDS ON</h3><div class="dep-chips">${organ.depends_on.length ? organ.depends_on.map((id)=>`<button class="dep-chip" data-dep="${escapeHtml(id)}">${escapeHtml(id)}</button>`).join('') : '<span class="muted">root organ</span>'}</div></div>
    <div class="inspect-section"><h3>HARD GATES</h3><ul>${organ.hard_gates.map((gate)=>`<li>${escapeHtml(gate)}</li>`).join('')}</ul></div>
    <div class="inspect-section"><h3>FAIL-CLOSED STATE</h3><span class="failure">${escapeHtml(organ.failure_state ?? 'UNSPECIFIED')}</span></div>
    <div class="inspect-section"><h3>CHECKS</h3><ul>${organ.tests.map((test)=>`<li>${escapeHtml(test)}</li>`).join('')}</ul></div>`;
  els.inspectorBody.querySelectorAll('[data-dep]').forEach((button) => button.addEventListener('click', () => selectOrgan(button.dataset.dep, true)));
}

function selectOrgan(id, reveal = false) {
  if (!registry.organs.some((organ) => organ.id === id)) return;
  selectedId = id;
  renderMap();
  renderInspector();
  if (reveal) document.querySelector(`[data-organ="${CSS.escape(id)}"]`)?.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
}

function renderMap() {
  const visible = currentVisible();
  const visibleIds = new Set(visible.map((organ) => organ.id));
  const summary = buildSummary(registry, focus, els.profile.value);
  const p = profileState(registry, els.profile.value);
  els.profileBrief.innerHTML = `<strong>${escapeHtml(p.label)}</strong> · ${escapeHtml(p.purpose)} ${p.enabled ? '' : '<span class="disabled">DISABLED — activation requirements remain unmet by default.</span>'}${p.activationRequirements?.length ? `<br><span class="muted">Activation requires: ${escapeHtml(p.activationRequirements.join(' · '))}</span>`:''}`;
  els.metrics.innerHTML = `<div class="metric"><b>${visible.length}</b><span>visible</span></div><div class="metric"><b>${summary.organCount}</b><span>profile</span></div><div class="metric"><b>${summary.dependencyCount}</b><span>links</span></div><div class="metric"><b>${summary.layerCount}</b><span>layers</span></div>`;
  els.resultTitle.textContent = els.search.value || els.layer.value !== 'all' ? 'Filtered research body' : 'Registered organs';
  els.empty.hidden = visible.length !== 0;
  const byLayer = new Map(layerOrder(registry.organs).map((layer) => [layer, []]));
  visible.forEach((organ) => { if (!byLayer.has(organ.layer)) byLayer.set(organ.layer, []); byLayer.get(organ.layer).push(organ); });
  els.layerGrid.innerHTML = [...byLayer.entries()].filter(([,organs])=>organs.length).map(([layer,organs]) => `<section class="layer"><div class="layer-title">${escapeHtml(titleCase(layer))} · ${organs.length}</div>${organs.map((organ)=>{
    const band = epistemicBand(organ.epistemic_class);
    const selected = organ.id === selectedId;
    const dependencyVisible = organ.depends_on.filter((id)=>visibleIds.has(id)).length;
    return `<button class="organ ${selected?'selected':''}" data-organ="${escapeHtml(organ.id)}" data-band="${band}" aria-pressed="${selected}"><span class="organ-id">${escapeHtml(organ.id)}</span><span class="organ-name">${escapeHtml(titleCase(organ.name))}</span><span class="organ-meta"><span>${escapeHtml(band)}</span><span>${dependencyVisible} visible deps</span></span></button>`;
  }).join('')}</section>`).join('');
  els.layerGrid.querySelectorAll('[data-organ]').forEach((button) => button.addEventListener('click', () => selectOrgan(button.dataset.organ)));
  const buttons = [...els.layerGrid.querySelectorAll('[data-organ]')];
  focusIndex = Math.max(0, Math.min(focusIndex, buttons.length - 1));
}

function renderAll() {
  if (!registry) return;
  renderTruth();
  renderMap();
  renderInspector();
  els.registryIdentity.textContent = `${registry.schema} · v${registry.registry_version ?? 'unknown'} · ${registry.organs.length} organs`;
}

async function loadJson(url) {
  const response = await fetch(url, {cache:'no-store'});
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function bootstrap() {
  try {
    const [registryValue, focusValue] = await Promise.all([loadJson(REGISTRY_URL), loadJson(FOCUS_URL)]);
    registry = validateRegistry(registryValue);
    focus = validateFocus(focusValue);
    populateControls(); renderAll();
    setSource(`READY · preserved registry + current focus · ${registry.organs.length} organs`, 'ready');
  } catch (error) {
    setSource(`HELD · local evidence not loaded · ${error.message}`, 'held');
    els['truth-title'].textContent = 'No research claims shown until preserved JSON is admitted.';
    els.statusSummary.textContent = 'Serve the repository locally or use the file-mode fallback. Nothing is uploaded.';
  }
}

async function readFile(input, validator) {
  const file = input.files?.[0];
  if (!file) return null;
  return validator(JSON.parse(await file.text()));
}

els.registryFile.addEventListener('change', async () => {
  try { registry = await readFile(els.registryFile, validateRegistry); populateControls(); renderAll(); setSource(`READY · local registry file · ${registry.organs.length} organs`, 'ready'); }
  catch (error) { setSource(`HELD · registry rejected · ${error.message}`, 'held'); }
});
els.focusFile.addEventListener('change', async () => {
  try { focus = await readFile(els.focusFile, validateFocus); renderAll(); setSource('READY · current focus admitted locally', 'ready'); }
  catch (error) { setSource(`HELD · focus rejected · ${error.message}`, 'held'); }
});
[els.search, els.profile, els.layer].forEach((el) => el.addEventListener(el === els.search ? 'input' : 'change', () => { selectedId = null; renderMap(); renderInspector(); }));
document.addEventListener('keydown', (event) => {
  const tag = event.target?.tagName;
  if (event.key === '/' && !['INPUT','SELECT','TEXTAREA'].includes(tag)) { event.preventDefault(); els.search.focus(); return; }
  if (!registry || ['INPUT','SELECT','TEXTAREA'].includes(tag)) return;
  const buttons = [...els.layerGrid.querySelectorAll('[data-organ]')];
  if (!buttons.length) return;
  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') { event.preventDefault(); focusIndex = (focusIndex + 1) % buttons.length; buttons[focusIndex].focus(); }
  if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') { event.preventDefault(); focusIndex = (focusIndex - 1 + buttons.length) % buttons.length; buttons[focusIndex].focus(); }
});

bootstrap();
