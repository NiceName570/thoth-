import { useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'

import {
  localModelsKey,
  localModelsOllamaOptions,
  type LocalModelsOwner,
  useLocalModelsOwner
} from '@/store/local-runtime-jobs'

import { LocalModelsOllamaSection } from './local-models-ollama-section'
import { LocalModelsOwnerProvider, useScopedLocalModelsOwner } from './local-models-owner'
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

// Local models are the user's own Ollama library; the pane lists it and nothing else.
function ScopedLocalModelsSettings(): ReactElement {
  const owner: LocalModelsOwner = useScopedLocalModelsOwner()
  const { data: ollama, isPending } = useQuery(localModelsOllamaOptions(owner))

  if (isPending) {
    return <SettingsSkeleton sections={[{ rows: 3 }]} />
  }

  return (
    <SettingsContent>
      <ActiveProfileNote className="mb-5" />
      <LocalModelsOllamaSection
        status={ollama ?? { active_model: null, base_url: 'http://localhost:11434/v1', models: [], reachable: false }}
      />
    </SettingsContent>
  )
}
