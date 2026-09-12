export const REGISTRY_SCHEMA = 'axm.matter-transfer-organ-registry.v1';
export const FOCUS_SCHEMA = 'axm.matter-transfer-current-focus.v1';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function object(value, label) {
  assert(value && typeof value === 'object' && !Array.isArray(value), `${label} must be an object`);
  return value;
}

function strings(value, label) {
  assert(Array.isArray(value) && value.every((item) => typeof item === 'string'), `${label} must be an array of strings`);
  return value;
}

export function validateRegistry(value) {
  const registry = object(value, 'registry');
  assert(registry.schema === REGISTRY_SCHEMA, `unsupported registry schema: ${registry.schema ?? 'missing'}`);
  assert(typeof registry.canonical_claim_ceiling === 'string' && registry.canonical_claim_ceiling.length > 0, 'registry claim ceiling is required');
  assert(Array.isArray(registry.organs) && registry.organs.length > 0, 'registry organs must be non-empty');
  object(registry.assembly_profiles, 'assembly_profiles');

  const ids = new Set();
  for (const organ of registry.organs) {
    object(organ, 'organ');
    assert(typeof organ.id === 'string' && /^MT-O\d+$/.test(organ.id), `invalid organ id: ${organ.id ?? 'missing'}`);
    assert(!ids.has(organ.id), `duplicate organ id: ${organ.id}`);
    ids.add(organ.id);
    assert(typeof organ.name === 'string' && organ.name.length > 0, `${organ.id} name is required`);
    assert(typeof organ.layer === 'string' && organ.layer.length > 0, `${organ.id} layer is required`);
    assert(typeof organ.epistemic_class === 'string' && organ.epistemic_class.length > 0, `${organ.id} epistemic_class is required`);
    assert(typeof organ.purpose === 'string' && organ.purpose.length > 0, `${organ.id} purpose is required`);
    strings(organ.depends_on, `${organ.id}.depends_on`);
    strings(organ.hard_gates, `${organ.id}.hard_gates`);
    strings(organ.tests, `${organ.id}.tests`);
  }

  for (const organ of registry.organs) {
    for (const dependency of organ.depends_on) {
      assert(ids.has(dependency), `${organ.id} depends on unknown organ ${dependency}`);
    }
  }

  for (const [profileId, profile] of Object.entries(registry.assembly_profiles)) {
    object(profile, `profile ${profileId}`);
    assert(typeof profile.purpose === 'string' && profile.purpose.length > 0, `${profileId} purpose is required`);
    strings(profile.required_organs, `${profileId}.required_organs`);
    assert(new Set(profile.required_organs).size === profile.required_organs.length, `${profileId} repeats an organ`);
    for (const organId of profile.required_organs) {
      assert(ids.has(organId), `${profileId} references unknown organ ${organId}`);
    }
  }

  return registry;
}

export function validateFocus(value) {
  const focus = object(value, 'focus');
  assert(focus.schema === FOCUS_SCHEMA, `unsupported focus schema: ${focus.schema ?? 'missing'}`);
  assert(typeof focus.status === 'string' && focus.status.length > 0, 'focus status is required');
  assert(typeof focus.claim_ceiling === 'string' && focus.claim_ceiling.length > 0, 'focus claim ceiling is required');
  object(focus.current_status, 'current_status');
  strings(focus.required_distinctions, 'required_distinctions');
  strings(focus.research_gates, 'research_gates');
  strings(focus.disabled_scope, 'disabled_scope');
  return focus;
}

export function epistemicBand(value = '') {
  const v = value.toLowerCase();
  if (v.includes('speculative')) return 'speculative';
  if (v.includes('unknown')) return 'unknown';
  if (v.includes('representation')) return 'representation';
  if (v.includes('model')) return 'modeling';
  return 'grounded';
}

export function layerOrder(organs) {
  const preferred = ['truth_intake', 'state_definition', 'transition_model', 'reconstruction', 'science_gate', 'experience_optional', 'governance'];
  const present = [...new Set(organs.map((organ) => organ.layer))];
  return [...preferred.filter((layer) => present.includes(layer)), ...present.filter((layer) => !preferred.includes(layer)).sort()];
}

export function profileState(registry, profileId) {
  if (!profileId || profileId === 'all') {
    return { id: 'all', label: 'Complete research architecture', enabled: true, purpose: 'Show every registered organ.', organIds: new Set(registry.organs.map((organ) => organ.id)) };
  }
  const profile = registry.assembly_profiles[profileId];
  assert(profile, `unknown profile: ${profileId}`);
  return {
    id: profileId,
    label: profileId.replaceAll('_', ' '),
    enabled: profile.enabled !== false,
    purpose: profile.purpose,
    organIds: new Set(profile.required_organs),
    activationRequirements: profile.activation_requirements ?? [],
  };
}

export function dependencyEdges(registry, visibleIds = null) {
  const allow = visibleIds ? new Set(visibleIds) : null;
  return registry.organs.flatMap((organ) => organ.depends_on
    .filter((source) => !allow || (allow.has(source) && allow.has(organ.id)))
    .map((source) => ({ source, target: organ.id })));
}

export function filterOrgans(registry, { query = '', layer = 'all', profileId = 'all' } = {}) {
  const profile = profileState(registry, profileId);
  const needle = query.trim().toLowerCase();
  return registry.organs.filter((organ) => {
    if (!profile.organIds.has(organ.id)) return false;
    if (layer !== 'all' && organ.layer !== layer) return false;
    if (!needle) return true;
    const haystack = [organ.id, organ.name, organ.layer, organ.epistemic_class, organ.purpose, organ.failure_state, ...(organ.hard_gates ?? []), ...(organ.tests ?? [])].join(' ').toLowerCase();
    return haystack.includes(needle);
  });
}

export function buildSummary(registry, focus, profileId = 'all') {
  const profile = profileState(registry, profileId);
  const organs = registry.organs.filter((organ) => profile.organIds.has(organ.id));
  const bands = organs.reduce((acc, organ) => {
    const band = epistemicBand(organ.epistemic_class);
    acc[band] = (acc[band] ?? 0) + 1;
    return acc;
  }, {});
  return {
    organCount: organs.length,
    dependencyCount: dependencyEdges(registry, profile.organIds).length,
    layerCount: new Set(organs.map((organ) => organ.layer)).size,
    bands,
    profileEnabled: profile.enabled,
    claimCeiling: focus?.claim_ceiling || registry.canonical_claim_ceiling,
  };
}
