import { useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'

import {
  localModelsCatalogOptions,
  localModelsHardwareOptions,
  localModelsKey,
  localModelsOllamaOptions,
  type LocalModelsOwner,
  useLocalModelsOwner,
  useLocalModelsStatus,
  useLocalRuntimeJobs
} from '@/store/local-runtime-jobs'
import type { LocalRuntimeJob } from '@/types/hermes'

import { LocalModelsBrowseSection } from './local-models-browse'
import { LocalModelsHardwareSection } from './local-models-hardware-section'
import { LocalModelsModelsSection } from './local-models-models-section'
import { LocalModelsOllamaSection } from './local-models-ollama-section'
import { LocalModelsOwnerProvider, useScopedLocalModelsOwner } from './local-models-owner'
import { LocalModelsRuntimeSection } from './local-models-runtime-section'
import { SettingsContent, SettingsSkeleton } from './primitives'
import { ActiveProfileNote } from './profile-scope'

export function LocalModelsSettings(): ReactElement {
  const owner: LocalModelsOwner = useLocalModelsOwner()

  return (
    <LocalModelsOwnerProvider key={JSON.stringify(localModelsKey(owner))} value={owner}>
      <ScopedLocalModelsSettings />
    </LocalModelsOwnerProvider>
  )
}

function ScopedLocalModelsSettings(): ReactElement {
  const owner: LocalModelsOwner = useScopedLocalModelsOwner()
  const { data: status } = useLocalModelsStatus(owner, true, true)
  const { data: hardware } = useQuery(localModelsHardwareOptions(owner))
  const { data: catalog } = useQuery(localModelsCatalogOptions(owner))
  // An older backend without the route reads as 'no Ollama' rather than a stuck skeleton.
  const { data: ollama, isPending: ollamaPending } = useQuery(localModelsOllamaOptions(owner))

  const jobs: readonly LocalRuntimeJob[] = useLocalRuntimeJobs(
    owner,
    (value: readonly LocalRuntimeJob[]): readonly LocalRuntimeJob[] => value
  )

  if (!status || !catalog || ollamaPending) {
    return <SettingsSkeleton sections={[{ rows: 2 }, { rows: 4 }]} />
  }

  const lastError = jobs.find(j => j.status === 'error')

  // A reachable Ollama owns the pane: its library is the model list. The managed
  // llama.cpp runtime only shows when Ollama is not running here.
  if (ollama?.reachable) {
    return (
      <SettingsContent>
        <ActiveProfileNote className="mb-5" />
        <LocalModelsOllamaSection status={ollama} />
      </SettingsContent>
    )
  }

  return (
    <SettingsContent>
      <ActiveProfileNote className="mb-5" />
      {ollama && <LocalModelsOllamaSection status={ollama} />}
      <LocalModelsRuntimeSection jobs={jobs} lastError={lastError} status={status} />
      <LocalModelsHardwareSection hardware={hardware} />
      <LocalModelsModelsSection catalog={catalog} jobs={jobs} lastError={lastError} status={status} />
      <LocalModelsBrowseSection />
    </SettingsContent>
  )
}
