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
vi.mock('@/store/model-assignment', () => ({ setMainModelAssignment: vi.fn(async () => ({ ok: true })) }))

import { QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import { queryClient } from '@/lib/query-client'
import { localModelsKey, localModelsOwner, watchLocalRuntimeJobs } from '@/store/local-runtime-jobs'
import { setMainModelAssignment } from '@/store/model-assignment'
import type { LocalModelsStatus } from '@/types/hermes'

import { LocalModelsSettings } from './local-models-settings'

vi.mock('@/hermes', () => ({
  getLocalCatalog: vi.fn(),
  getLocalHardware: vi.fn(),
  getLocalModelsJobs: vi.fn(),
  getLocalModelsStatus: vi.fn(),
  getLocalOllama: vi.fn(),
  getProfiles: vi.fn(async () => ({ profiles: [] })),
  setApiRequestProfile: vi.fn()
}))

import * as hermes from '@/hermes'

const mocked = vi.mocked(hermes)

const STATUS: LocalModelsStatus = {
  enabled: false,
  tag: 'b11370',
  configured_tag: 'b11370',
  update_available: false,
  runtime_installed: false,
  runtime_backend: null,
  server_running: false,
  server_base_url: null,
  active_model_id: null,
  loaded_models: {},
  models: [],
  models_dir: 'C:/somewhere/models'
}

beforeEach((): void => {
  queryClient.clear()
  queryClient.setDefaultOptions({ queries: { ...queryClient.getDefaultOptions().queries, retry: false } })
  mocked.getLocalModelsStatus.mockResolvedValue(STATUS)
  mocked.getLocalHardware.mockResolvedValue({
    uma: true,
    vram_total_bytes: 63 * 2 ** 30,
    vram_usable_bytes: 60 * 2 ** 30,
    ram_total_bytes: 63 * 2 ** 30,
    ram_available_bytes: 50 * 2 ** 30,
    vram_label: '63.1 GB'
  })
  mocked.getLocalCatalog.mockResolvedValue({ models: [] })
  mocked.getLocalModelsJobs.mockResolvedValue({ jobs: [] })
  queryClient.setQueryData(localModelsKey(localModelsOwner(), 'jobs'), [])
})

afterEach(async () => {
  cleanup()
  queryClient.clear()
  await act(async () => {
    watchLocalRuntimeJobs()
  })
  vi.clearAllMocks()
})

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

it('offers a running Ollama and points the main model at it', async () => {
  mocked.getLocalOllama.mockResolvedValue({
    detected: true,
    base_url: 'http://127.0.0.1:11434/v1',
    models: ['qwen3:32b', 'llama3.3:70b']
  })
  renderPane()

  fireEvent.click(await screen.findByRole('button', { name: 'Use Ollama' }))

  await waitFor(() =>
    expect(setMainModelAssignment).toHaveBeenCalledWith(
      { provider: 'custom', model: 'qwen3:32b', base_url: 'http://127.0.0.1:11434/v1' },
      expect.anything()
    )
  )
  expect(await screen.findByRole('button', { name: 'Using Ollama' })).toBeTruthy()
})

it('shows no Ollama option when none is running', async () => {
  mocked.getLocalOllama.mockResolvedValue({ detected: false, base_url: 'http://127.0.0.1:11434/v1', models: [] })
  renderPane()

  await waitFor(() => expect(mocked.getLocalOllama).toHaveBeenCalled())
  expect(screen.queryByRole('button', { name: 'Use Ollama' })).toBeNull()
})
