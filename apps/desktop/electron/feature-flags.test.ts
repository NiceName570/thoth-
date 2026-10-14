// feature-flags.ts is the single resolver for which gated surfaces are on in
// this artifact. Thoth ships no local-models surfaces: Ollama and LM Studio are
// ordinary auto-detected providers instead.
import assert from 'node:assert/strict'

import { test } from 'vitest'

import { isCanaryTag, resolveFeatureFlags } from './feature-flags'

test('local models stay off on every channel, with or without --local', () => {
  for (const canary of [false, true]) {
    for (const argv of [[], ['Thoth.exe'], ['Thoth.exe', '--local']]) {
      assert.deepEqual(resolveFeatureFlags({ argv, canary }), { localModels: false })
    }
  }
})

test('isCanaryTag recognizes canary stamps and rejects stable/dev tags', () => {
  assert.equal(isCanaryTag('v0.28.0+canary.20260818T123456Z'), true)
  assert.equal(isCanaryTag('v0.28.0-canary.20260818'), false)
  assert.equal(isCanaryTag('v0.28.0+canary.20260818123456'), false)
  assert.equal(isCanaryTag('v0.28.0'), false)
  assert.equal(isCanaryTag(''), false)
  assert.equal(isCanaryTag(null), false)
  assert.equal(isCanaryTag(undefined), false)
})
