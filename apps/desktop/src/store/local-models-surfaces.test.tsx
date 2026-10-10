import type { ModelOptionsResult } from '@hermes/shared'
import { QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, renderHook, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import type { HermesApiRequest, HermesConnection } from '@/global'
import type { LocalCatalogModel, LocalModelsStatus, LocalRuntimeJob } from '@/types/hermes'

vi.mock('@/hermes', async (): Promise<object> => ({
  ...(await import('@/api/local-models')),
  getHermesConfigRecord: async (): Promise<object> => ({}),
  getGlobalModelOptions: async (): Promise<ModelOptionsResult> => ({ providers: [] })
}))
vi.mock('@/store/profile', async (): Promise<object> => {
  const { atom } = await import('nanostores')

  // settings-scope compares the selected profile against the roster's default; 'work' IS the
  // default here so the settings surfaces render without the non-default warning.
  return {
    $activeGatewayProfile: atom<string>('work'),
    $profiles: atom([{ name: 'work', is_default: true }]),
    normalizeProfileKey: (name: string | null | undefined): string => (name ?? '').trim() || 'default'
  }
})
vi.mock('@/store/session', async (): Promise<object> => {
  const { atom } = await import('nanostores')

  return { $connection: atom<HermesConnection | null>(null), $defaultReasoningEffort: atom<string>('') }
})
vi.mock('@/store/notifications', (): object => ({ notify: vi.fn(), notifyError: vi.fn() }))

import { setApiRequestConnection, setApiRequestProfile } from '@/api/client'
import { ModelCatalogMenu, type ModelMenuController } from '@/app/shell/model-catalog-menu'
import { DropdownMenu, DropdownMenuContent } from '@/components/ui/dropdown-menu'
import { I18nProvider } from '@/i18n'
import { queryClient } from '@/lib/query-client'
import { $localModelsEnabled } from '@/store/local-models-flag'
import { notify, notifyError } from '@/store/notifications'
import { $activeGatewayProfile } from '@/store/profile'
import { $connection } from '@/store/session'
import { deferred } from '@/test/deferred'
import { stubMenuDomApis, stubResizeObserver } from '@/test/jsdom'

import {
  checkLocalRuntimeUpdate,
  localModelsKey,
  localModelsOwner,
  refreshLocalModels,
  useLocalModelsOwner,
  watchLocalRuntimeJobs
} from './local-runtime-jobs'

stubResizeObserver()
stubMenuDomApis()

const status: LocalModelsStatus = {
  enabled: true,
  tag: 'installed',
  configured_tag: 'installed',
  update_available: false,
  runtime_installed: true,
  runtime_backend: 'cpu',
  server_running: false,
  server_base_url: null,
  active_model_id: null,
  loaded_models: {},
  models: [],
  models_dir: '/models'
}

const running: LocalRuntimeJob = {
  job_id: 'same-id',
  kind: 'model-download',
  model_id: 'model',
  target: 'Download A',
  status: 'running',
  phase: 'downloading',
  detail: '',
  done_bytes: 1,
  total_bytes: 2,
  percent: 50,
  error: null
}

let jobs: LocalRuntimeJob[] = []
let catalog: LocalCatalogModel[] = []

const model: LocalCatalogModel = {
  id: 'model',
  display_name: 'Download A',
  description: '',
  size_bytes: 2,
  size_label: '2 B',
  native_context: 4096,
  native_context_label: '4K',
  recommended: true,
  downloaded: false,
  fits: true,
  mtp: false,
  fit_summary: 'fits'
}

const api = vi.fn(async (request: HermesApiRequest): Promise<unknown> => {
  if (request.path.endsWith('/status')) {
    return structuredClone(status)
  }

  if (request.path.endsWith('/catalog')) {
    return { models: catalog }
  }

  if (request.path.endsWith('/jobs')) {
    return { jobs: structuredClone(jobs) }
  }

  if (request.path.endsWith('/download/pause') || request.path.endsWith('/download/resume')) {
    expect(request).toMatchObject({ connectionId: 'A', profile: 'work', method: 'POST', body: { job_id: 'same-id' } })
    const paused: boolean = request.path.endsWith('/pause')
    jobs = jobs.map((job: LocalRuntimeJob): LocalRuntimeJob => ({
      ...job,
      status: paused ? 'paused' : 'running',
      can_pause: !paused,
      can_resume: paused
    }))

    return paused ? { ok: true, paused: true } : { ok: true, resumed: true }
  }

  if (request.path.endsWith('/hardware')) {
    return {}
  }

  throw new Error(`Unexpected request ${request.path}`)
})

const controller: ModelMenuController = {
  current: { model: '', provider: '', effort: '', fast: false },
  applyPreset: (): void => {},
  presetFor: (): object => ({}),
  select: (): void => {},
  setOptions: (): void => {}
}

beforeEach((): void => {
  vi.useFakeTimers()
  queryClient.clear()
  jobs = []
  catalog = []
  api.mockClear()
  $connection.set(null)
  vi.mocked(notify).mockClear()
  vi.mocked(notifyError).mockClear()
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: { api } })
  setApiRequestConnection('A')
  setApiRequestProfile('work')
  $activeGatewayProfile.set('work')
  $localModelsEnabled.set(true)
})
afterEach((): void => {
  cleanup()
  queryClient.clear()
  vi.useRealTimers()
})

async function tick(ms: number = 0): Promise<void> {
  await act(async (): Promise<void> => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

it('follows an authoritative route change even when its descriptor is unchanged', async (): Promise<void> => {
  const hook = renderHook(() => useLocalModelsOwner())
  expect(hook.result.current.connectionId).toBe('A')
  await act(async (): Promise<void> => {
    setApiRequestConnection('B')
    await vi.advanceTimersByTimeAsync(0)
  })
  expect(hook.result.current.connectionId).toBe('B')
})

it('discards late legacy completions and update notices without invalidating the new catalog', async (): Promise<void> => {
  setApiRequestConnection(null)

  const connection: HermesConnection = {
    baseUrl: 'http://A',
    token: '',
    wsUrl: '',
    logs: [],
    isFullscreen: false,
    nativeOverlayWidth: 0,
    windowButtonPosition: null
  }

  $connection.set(connection)
  const owner = localModelsOwner()
  jobs = [running]
  watchLocalRuntimeJobs(owner)
  await tick()

  const pendingJobs = deferred<{ jobs: LocalRuntimeJob[] }>()
  const pendingStatus = deferred<LocalModelsStatus>()
  api.mockReturnValueOnce(pendingJobs.promise)
  watchLocalRuntimeJobs(owner)
  api.mockReturnValueOnce(pendingStatus.promise)
  const update: Promise<void> = checkLocalRuntimeUpdate(owner)
  $connection.set({ ...connection, baseUrl: 'http://B' })
  const key: readonly string[] = ['model-options', 'work', 'global']
  queryClient.setQueryData(key, { providers: [] })
  pendingJobs.resolve({ jobs: [{ ...running, status: 'done' }] })
  pendingStatus.resolve({ ...status, update_available: true })
  await update
  await tick()
  expect(queryClient.getQueryData<readonly LocalRuntimeJob[]>(localModelsKey(owner, 'jobs'))).toEqual([running])
  expect(queryClient.getQueryData(localModelsKey(owner, 'status'))).toBeUndefined()
  // Mutation acknowledgments can refresh directly, without a jobs response.
  refreshLocalModels(owner)
  expect(queryClient.getQueryState(key)?.isInvalidated).toBe(false)
  expect(notify).not.toHaveBeenCalled()
})

it('keeps menu focus and its scalar selection stable across byte updates and outages', async (): Promise<void> => {
  jobs = [running]
  let reads: number = 0

  const menuController: ModelMenuController = {
    ...controller,
    get current() {
      reads += 1

      return controller.current
    }
  }

  render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <DropdownMenu open>
          <DropdownMenuContent>
            <ModelCatalogMenu controller={menuController} ownerConnectionId="A" profile="work" />
          </DropdownMenuContent>
        </DropdownMenu>
      </I18nProvider>
    </QueryClientProvider>
  )
  await tick(1)
  const input: HTMLElement = screen.getByRole('textbox', { name: 'Search models' })
  fireEvent.change(input, { target: { value: 'Download' } })
  input.focus()
  await tick(1)
  const before: number = reads
  jobs = [{ ...running, done_bytes: 2, percent: 75 }]
  await tick(700)
  expect(screen.getByText('75%')).toBeTruthy()
  expect(window.document.activeElement).toBe(input)
  expect(reads).toBe(before)
  const key = localModelsKey({ connectionId: 'A', profile: 'work' }, 'jobs')
  const snapshot = queryClient.getQueryData(key)
  api.mockRejectedValueOnce(new Error('offline'))
  await tick(700)
  expect(queryClient.getQueryData(key)).toBe(snapshot)
  expect(screen.getByText('75%')).toBeTruthy()
  expect(window.document.activeElement).toBe(input)
})
