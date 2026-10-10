vi.mock('@/store/profile', async (): Promise<object> => {
  const { atom } = await import('nanostores')

  return {
    $activeGatewayProfile: atom<string>('default'),
    $profiles: atom<Array<{ name: string; is_default?: boolean }>>([]),
    normalizeProfileKey: (profile: string | null): string => profile || 'default'
  }
})
vi.mock('@/store/session', async (): Promise<object> => {
  const { atom } = await import('nanostores')

  return { $connection: atom(null), $defaultReasoningEffort: atom<string>('') }
})

import { QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { OllamaStatus } from '@/hermes'
import { I18nProvider } from '@/i18n'
import { queryClient } from '@/lib/query-client'

import { LocalModelsSettings } from './local-models-settings'

// Mock the API layer — the pane's contract is what it RENDERS from these
// payloads, not transport.
vi.mock('@/hermes', () => ({
  getLocalCatalog: vi.fn(),
  getLocalModelsStatus: vi.fn(),
  getOllamaStatus: vi.fn(),
  // The page imports the profile store (settings-scope chip), whose module
  // body subscribes $activeGatewayProfile → setApiRequestProfile at load.
  getProfiles: vi.fn(async () => ({ profiles: [] })),
  setApiRequestProfile: vi.fn(),
  setModelAssignment: vi.fn()
}))

import * as hermes from '@/hermes'

const mocked = vi.mocked(hermes)

const NO_OLLAMA: OllamaStatus = {
  active_model: null,
  base_url: 'http://localhost:11434/v1',
  models: [],
  reachable: false
}

function renderPane() {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>
          <LocalModelsSettings />
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach((): void => {
  queryClient.clear()
  queryClient.setDefaultOptions({ queries: { ...queryClient.getDefaultOptions().queries, retry: false } })
  mocked.getOllamaStatus.mockResolvedValue(NO_OLLAMA)
})

afterEach((): void => {
  cleanup()
  queryClient.clear()
  vi.clearAllMocks()
})

describe('LocalModelsSettings', (): void => {
  it('lists the Ollama library and nothing from the managed runtime', async (): Promise<void> => {
    mocked.getOllamaStatus.mockResolvedValue({
      ...NO_OLLAMA,
      active_model: 'llama3.2:3b',
      models: ['llama3.2:3b', 'qwen3:8b'],
      reachable: true
    })
    renderPane()

    expect(await screen.findByText('qwen3:8b')).toBeTruthy()
    expect(screen.getByText('llama3.2:3b')).toBeTruthy()
    expect(screen.getByText('Default')).toBeTruthy()
    expect(screen.queryByText('Install the local runtime')).toBeNull()
    expect(screen.queryByText('Recommended')).toBeNull()
    expect(mocked.getLocalCatalog).not.toHaveBeenCalled()
    expect(mocked.getLocalModelsStatus).not.toHaveBeenCalled()
  })

  it('makes a library model the default through the custom endpoint', async (): Promise<void> => {
    mocked.getOllamaStatus.mockResolvedValue({ ...NO_OLLAMA, models: ['qwen3:8b'], reachable: true })
    mocked.setModelAssignment.mockResolvedValue({ ok: true, provider: 'custom', model: 'qwen3:8b' } as never)
    renderPane()

    fireEvent.click(await screen.findByRole('button', { name: 'Use' }))
    await waitFor((): void => {
      expect(mocked.setModelAssignment).toHaveBeenCalledWith(
        expect.objectContaining({
          base_url: 'http://localhost:11434/v1',
          model: 'qwen3:8b',
          provider: 'custom',
          scope: 'main'
        }),
        expect.anything()
      )
    })
  })

  it('says Ollama is not running and offers no runtime download instead', async (): Promise<void> => {
    renderPane()

    expect(await screen.findByText('Ollama not detected')).toBeTruthy()
    expect(screen.queryByText('Install the local runtime')).toBeNull()
    expect(screen.queryByRole('button', { name: /download/i })).toBeNull()
  })
})
