import type { ModelOptionProvider } from '@hermes/shared'
import { QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { queryClient } from '@/lib/query-client'

import { providerMeters, UsageMeter } from './index'

vi.mock('@/hermes', () => ({ getGlobalModelOptions: vi.fn() }))

import * as hermes from '@/hermes'

const NOW = Date.parse('2026-10-10T12:00:00Z')
const LATER = '2099-01-01T00:00:00Z'

const CODEX: ModelOptionProvider = {
  slug: 'openai-codex',
  name: 'OpenAI Codex',
  usage: {
    windows: [
      { label: 'Session', used_percent: 18, resets_at: LATER, scope: 'account' },
      { label: 'Weekly', used_percent: 60, resets_at: LATER, scope: 'account' }
    ]
  }
}

const CLAUDE: ModelOptionProvider = {
  slug: 'anthropic',
  name: 'Anthropic',
  usage: { windows: [{ label: 'Current session', used_percent: 95, resets_at: LATER, scope: 'account' }] }
}

const NO_USAGE: ModelOptionProvider = { slug: 'cline', name: 'Cline' }

beforeEach((): void => {
  queryClient.clear()
})

afterEach((): void => {
  cleanup()
  vi.clearAllMocks()
})

it('reports the tightest window per plan and skips providers with no usage data', () => {
  const meters = providerMeters([CODEX, CLAUDE, NO_USAGE], NOW)

  expect(meters.map(m => [m.name, m.windows[0].label, m.windows[0].remaining])).toEqual([
    ['Codex', 'Weekly', 40],
    ['Claude', 'Current session', 5]
  ])
})

it('drops windows that already rolled over', () => {
  const stale: ModelOptionProvider = {
    ...CODEX,
    usage: { windows: [{ label: 'Session', used_percent: 99, resets_at: '2026-10-10T11:00:00Z', scope: 'account' }] }
  }

  expect(providerMeters([stale], NOW)).toEqual([])
})

it('shows each plan in the status bar', async () => {
  vi.mocked(hermes.getGlobalModelOptions).mockResolvedValue({ providers: [CODEX, CLAUDE, NO_USAGE] } as never)
  render(
    <QueryClientProvider client={queryClient}>
      <UsageMeter />
    </QueryClientProvider>
  )

  const meter = await screen.findByRole('status', { name: 'Plan usage' })
  expect(meter.textContent).toContain('Codex')
  expect(meter.textContent).toContain('Claude')
  expect(meter.textContent).not.toContain('Cline')
})
