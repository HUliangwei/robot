import assert from 'node:assert/strict'
import test from 'node:test'

import { buildProviderDoctorPath, providerArchitectureRows } from '../src/providers.ts'

test('provider doctor path keeps provider and runtime selection in the API request', () => {
  assert.equal(
    buildProviderDoctorPath('starvla', 'vla dev', 'D:/Providers/star VLA'),
    '/providers/starvla/doctor?environment=vla+dev&provider_root=D%3A%2FProviders%2Fstar+VLA',
  )
})

test('provider architecture projection remains provider-owned display data', () => {
  const rows = providerArchitectureRows({
    name: 'starvla',
    capabilities: {
      frameworks: [{ id: 'qwen_oft', native_name: 'QwenOFT', backbone: 'Qwen-VL', action_head: 'OFT', fusion: 'hidden states' }],
    },
  } as any)

  assert.deepEqual(rows, [{ framework: 'qwen_oft / QwenOFT', backbone: 'Qwen-VL', actionHead: 'OFT', fusion: 'hidden states' }])
})
