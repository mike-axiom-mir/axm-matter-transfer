import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { buildSummary, dependencyEdges, epistemicBand, filterOrgans, profileState, validateFocus, validateRegistry } from '../viewer/research-map-model.mjs';

const registry = JSON.parse(await readFile(new URL('../provenance/factual-space-pr2/data/matter_transfer_organ_registry_v0_1.json', import.meta.url), 'utf8'));
const focus = JSON.parse(await readFile(new URL('../data/current_focus_v0_2.json', import.meta.url), 'utf8'));

test('admits the preserved 25-organ research registry without strengthening it', () => {
  const admitted = validateRegistry(registry);
  assert.equal(admitted.organs.length, 25);
  assert.equal(admitted.status, 'research_draft');
  assert.match(admitted.canonical_claim_ceiling, /not established/i);
  assert.equal(admitted.truth_boundary.no_silent_claim_promotion, true);
});

test('admits the current speculative research focus and keeps disabled scope visible', () => {
  const admitted = validateFocus(focus);
  assert.equal(admitted.status, 'speculative_research');
  assert.match(admitted.claim_ceiling, /No physical macroscopic matter-transfer mechanism is established/i);
  assert.ok(admitted.disabled_scope.includes('biological subjects'));
  assert.ok(admitted.required_distinctions.includes('simulation success vs physical evidence'));
});

test('profiles select existing organs and the experimental bench stays disabled', () => {
  const notebook = profileState(registry, 'research_notebook');
  const observer = profileState(registry, 'observer_game_layer');
  const bench = profileState(registry, 'non_destructive_experimental_bench');
  assert.equal(notebook.organIds.size, 9);
  assert.equal(observer.organIds.size, 11);
  assert.equal(bench.enabled, false);
  assert.ok(bench.activationRequirements.length >= 4);
});

test('observer profile contains the representation organ but does not confuse it with authority', () => {
  const organs = filterOrgans(registry, { profileId: 'observer_game_layer' });
  const observer = organs.find((organ) => organ.id === 'MT-O43');
  assert.ok(observer);
  assert.equal(observer.layer, 'experience_optional');
  assert.equal(epistemicBand(observer.epistemic_class), 'representation');
  assert.match(observer.purpose, /without altering simulation truth/i);
});

test('dependency projection and search are deterministic and bounded to the selected profile', () => {
  const visible = filterOrgans(registry, { profileId: 'observer_game_layer', query: 'visual' });
  assert.ok(visible.length > 0);
  const observerIds = profileState(registry, 'observer_game_layer').organIds;
  for (const organ of visible) assert.ok(observerIds.has(organ.id));
  for (const edge of dependencyEdges(registry, observerIds)) {
    assert.ok(observerIds.has(edge.source));
    assert.ok(observerIds.has(edge.target));
  }
  const summary = buildSummary(registry, focus, 'observer_game_layer');
  assert.equal(summary.organCount, 11);
  assert.equal(summary.profileEnabled, true);
  assert.match(summary.claimCeiling, /^No .*established\.$/i);
});

test('malformed copies fail closed before presentation', () => {
  const forged = structuredClone(registry);
  forged.organs[1].depends_on.push('MT-O999');
  assert.throws(() => validateRegistry(forged), /unknown organ MT-O999/);
  const duplicate = structuredClone(registry);
  duplicate.organs[1].id = duplicate.organs[0].id;
  assert.throws(() => validateRegistry(duplicate), /duplicate organ id/);
});
