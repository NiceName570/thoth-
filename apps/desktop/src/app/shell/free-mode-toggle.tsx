import { useQuery, useQueryClient } from '@tanstack/react-query'

import { DropdownMenuCheckboxItem } from '@/components/ui/dropdown-menu'
import { getFreeMode, setFreeMode } from '@/hermes'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'

import type { ModelMenuController } from './model-catalog-menu'

interface FreeModeToggleProps {
  className: string
  controller: ModelMenuController
  onChanged: () => void
  ownerConnectionId?: string
  profile?: string
}

/** Model-menu switch for Free mode: on moves the chat to a free model and lists only free models;
 *  off returns to the model chosen before. The backend owns the setting (model.free_mode). */
export function FreeModeToggle({ className, controller, onChanged, ownerConnectionId, profile }: FreeModeToggleProps) {
  const { t } = useI18n()
  const copy = t.shell.modelMenu
  const queryClient = useQueryClient()
  const scope = { connectionId: ownerConnectionId ?? null, profile: profile ?? null }
  const queryKey = ['free-mode', ownerConnectionId ?? null, profile ?? null]
  const state = useQuery({ queryKey, queryFn: () => getFreeMode(scope) })
  const enabled = state.data?.enabled === true

  async function toggle(next: boolean) {
    try {
      const result = await setFreeMode(next, scope)
      queryClient.setQueryData(queryKey, { enabled: result.enabled })

      if (result.provider && result.model) {
        await controller.select(result.model, result.provider)
      }

      onChanged()
      notify({
        durationMs: 3_000,
        kind: 'success',
        message: next ? copy.freeModeOn(result.model ?? '') : copy.freeModeOff
      })
    } catch (err) {
      notifyError(err, copy.freeModeFailed)
    }
  }

  return (
    <DropdownMenuCheckboxItem
      checked={enabled}
      className={cn(className, 'text-(--ui-text-tertiary)', enabled && 'text-foreground')}
      disabled={state.isPending}
      onCheckedChange={checked => void toggle(checked === true)}
      onSelect={event => event.preventDefault()}
    >
      {copy.freeMode}
    </DropdownMenuCheckboxItem>
  )
}
