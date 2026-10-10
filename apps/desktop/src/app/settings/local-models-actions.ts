import { type QueryClient, useQueryClient } from '@tanstack/react-query'

import { useI18n } from '@/i18n'
import type { Translations } from '@/i18n/types'
import { type LocalModelsOwner } from '@/store/local-runtime-jobs'

import { useScopedLocalModelsOwner } from './local-models-owner'

export type LocalModelsCopy = Translations['settings']['localModels']

export interface LocalModelsActionScope {
  owner: LocalModelsOwner
  client: QueryClient
  copy: LocalModelsCopy
}

export function useLocalModelsActionScope(): LocalModelsActionScope {
  const owner: LocalModelsOwner = useScopedLocalModelsOwner()
  const client: QueryClient = useQueryClient()
  const { t } = useI18n()

  return { owner, client, copy: t.settings.localModels }
}
