import { type ReactElement, useState } from 'react'

import { Button } from '@/components/ui/button'
import type { OllamaStatus } from '@/hermes'
import { Cpu, Loader2 } from '@/lib/icons'
import {
  isCurrentLocalModelsOwner,
  localModelsKey,
  localModelsNotificationTitle,
  localModelsRequestScope
} from '@/store/local-runtime-jobs'
import { setMainModelAssignment } from '@/store/model-assignment'
import { notify, notifyError } from '@/store/notifications'

import { type LocalModelsActionScope, useLocalModelsActionScope } from './local-models-actions'
import { ListRow, Pill, SettingsSection } from './primitives'

export interface LocalModelsOllamaSectionProps {
  status: OllamaStatus
}

async function assignOllamaModel({ owner, client, copy }: LocalModelsActionScope, status: OllamaStatus, model: string) {
  try {
    await setMainModelAssignment(
      { provider: 'custom', model, base_url: status.base_url },
      localModelsRequestScope(owner)
    )
    notify({
      durationMs: 3_000,
      kind: 'success',
      message: copy.ollamaUsing(model),
      title: localModelsNotificationTitle(owner)
    })
    await client.invalidateQueries({ queryKey: localModelsKey(owner, 'ollama') })
  } catch (err) {
    if (isCurrentLocalModelsOwner(owner)) {
      notifyError(err, copy.ollamaUseFailed(model))
    }
  }
}

// The user's own Ollama install leads the pane: its library is the model list,
// and "Use" points new chats at Ollama's OpenAI-compatible endpoint.
export function LocalModelsOllamaSection({ status }: LocalModelsOllamaSectionProps): ReactElement {
  const scope: LocalModelsActionScope = useLocalModelsActionScope()
  const { copy } = scope
  const [busy, setBusy] = useState<null | string>(null)
  const root: string = status.base_url.replace(/\/v1$/, '')

  if (!status.reachable) {
    return (
      <SettingsSection icon={Cpu} title={copy.ollamaTitle}>
        <ListRow description={copy.ollamaNotFoundDetail(root)} title={copy.ollamaNotFoundTitle} />
      </SettingsSection>
    )
  }

  async function handleUse(model: string): Promise<void> {
    setBusy(model)

    try {
      await assignOllamaModel(scope, status, model)
    } finally {
      setBusy(null)
    }
  }

  return (
    <SettingsSection icon={Cpu} meta={`${status.models.length}`} title={copy.ollamaTitle}>
      <p className="text-[0.75rem] text-muted-foreground">{copy.ollamaDetected(root)}</p>
      {status.models.length === 0 && <ListRow title={copy.ollamaEmpty} />}
      <div className="grid gap-1">
        {status.models.map(model => (
          <ListRow
            action={
              model === status.active_model ? (
                <Pill tone="success">{copy.activePill}</Pill>
              ) : (
                <Button disabled={busy !== null} onClick={() => void handleUse(model)} size="sm">
                  {busy === model && <Loader2 className="animate-spin" />}
                  {copy.useAction}
                </Button>
              )
            }
            key={model}
            title={model}
          />
        ))}
      </div>
    </SettingsSection>
  )
}
