import type { LocalCatalogModel, LocalHardware, LocalModelsStatus, LocalRuntimeJob } from '@/types/hermes'

import { hermesApi, profileScoped } from './client'

export interface LocalModelsScope {
  connectionId: string | null
  profile: string
}

// Reads behind the local-models surfaces: the managed runtime's status, catalog
// and jobs (picker, model menu) and the user's own Ollama library (settings pane).

export function getLocalModelsStatus(scope?: LocalModelsScope): Promise<LocalModelsStatus> {
  return hermesApi<LocalModelsStatus>({
    ...(scope ?? profileScoped()),
    path: '/api/local-models/status'
  })
}

// The user's own Ollama install: its library, served at base_url (OpenAI-compatible /v1).
export interface OllamaStatus {
  active_model: null | string
  base_url: string
  models: string[]
  reachable: boolean
}

export function getOllamaStatus(scope?: LocalModelsScope): Promise<OllamaStatus> {
  return hermesApi<OllamaStatus>({
    ...(scope ?? profileScoped()),
    path: '/api/local-models/ollama'
  })
}

export function getLocalHardware(scope?: LocalModelsScope): Promise<LocalHardware> {
  return hermesApi<LocalHardware>({
    ...(scope ?? profileScoped()),
    path: '/api/local-models/hardware'
  })
}

export function getLocalCatalog(scope?: LocalModelsScope): Promise<{ models: LocalCatalogModel[] }> {
  return hermesApi<{ models: LocalCatalogModel[] }>({
    ...(scope ?? profileScoped()),
    path: '/api/local-models/catalog'
  })
}

export function installLocalRuntime(
  backend?: string,
  scope?: LocalModelsScope
): Promise<{ backend: string; job_id: string; tag: string }> {
  return hermesApi<{ backend: string; job_id: string; tag: string }>({
    ...(scope ?? profileScoped()),
    body: { backend: backend ?? null },
    method: 'POST',
    path: '/api/local-models/runtime/install'
  })
}

export function getLocalModelsJobs(scope?: LocalModelsScope): Promise<{ jobs: LocalRuntimeJob[] }> {
  return hermesApi<{ jobs: LocalRuntimeJob[] }>({
    ...(scope ?? profileScoped()),
    path: '/api/local-models/jobs'
  })
}
