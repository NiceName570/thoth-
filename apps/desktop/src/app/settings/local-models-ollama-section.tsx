import { type ReactElement, useState } from 'react'

import { Button } from '@/components/ui/button'
import { CheckCircle2, Loader2, Zap } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { setMainModelAssignment } from '@/store/model-assignment'
import { notify, notifyError } from '@/store/notifications'
import type { LocalOllama } from '@/types/hermes'

import { useLocalModelsActionScope } from './local-models-actions'
import { ListRow, Pill, SettingsSection } from './primitives'

// An Ollama the user already runs is offered as-is: one click points the main
// model at its OpenAI-compatible /v1 root instead of installing a second engine.
export function LocalModelsOllamaSection({ ollama }: { ollama: LocalOllama }): ReactElement {
  const { copy, owner } = useLocalModelsActionScope()
  const [busy, setBusy] = useState<boolean>(false)
  const [inUse, setInUse] = useState<boolean>(false)
  const model: string = ollama.models[0] ?? ''

  async function useOllama(): Promise<void> {
    setBusy(true)

    try {
      await setMainModelAssignment(
        { provider: 'custom', model, base_url: ollama.base_url },
        { connectionId: owner.connectionId, profile: owner.profile }
      )
      setInUse(true)
      notify({ durationMs: 3_000, kind: 'success', message: model, title: copy.ollamaInUse })
    } catch (err) {
      notifyError(err, copy.ollamaFailed)
    } finally {
      setBusy(false)
    }
  }

  return (
    <SettingsSection
      aside={inUse ? <Pill tone="primary">{copy.ollamaInUse}</Pill> : undefined}
      icon={Zap}
      title={copy.ollamaTitle}
    >
      <ListRow
        action={
          <Button
            className={cn(busy && '[&_svg]:animate-spin')}
            disabled={busy || inUse || !model}
            onClick={() => void useOllama()}
            size="sm"
          >
            {busy ? <Loader2 /> : inUse ? <CheckCircle2 /> : <Zap />}
            {inUse ? copy.ollamaInUse : copy.ollamaUse}
          </Button>
        }
        description={copy.ollamaDetail(ollama.base_url)}
        title={copy.ollamaDetected(ollama.models.length)}
      />
    </SettingsSection>
  )
}
