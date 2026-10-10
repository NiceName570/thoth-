import type { ModelOptionProvider } from '@hermes/shared'
import { useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'

import { Tip } from '@/components/ui/tooltip'
import { getGlobalModelOptions } from '@/hermes'
import {
  formatReset,
  poolUsage,
  USAGE_NOTICE_PERCENT,
  USAGE_WARN_PERCENT,
  type UsageWindowView,
  usageWindows
} from '@/lib/provider-limit'
import { cn } from '@/lib/utils'

// Plan names people know them by; anything else keeps its catalog name.
const SHORT_NAMES: Record<string, string> = { anthropic: 'Claude', 'openai-codex': 'Codex', openrouter: 'OpenRouter' }

// The backend serves usage from cache and refreshes it in the background, so polling is cheap.
const REFRESH_MS = 60_000

export interface ProviderMeter {
  name: string
  slug: string
  /** Every live window, tightest first; the first is what the bar shows. */
  windows: UsageWindowView[]
}

/** Signed-in providers that report plan usage, with their live windows. A multi-account pool
 *  shows its best account, since that is where the next request can still go. */
export function providerMeters(providers: readonly ModelOptionProvider[], nowMs = Date.now()): ProviderMeter[] {
  return providers.flatMap(provider => {
    const pool = poolUsage(provider, nowMs)

    const windows = pool
      ? (pool.accounts
          .filter(account => account.state === 'ready' && account.windows.length > 0)
          .map(account => account.windows)
          .sort((a, b) => b[0].remaining - a[0].remaining)[0] ?? [])
      : (usageWindows(provider, nowMs) ?? [])

    return windows.length > 0 ? [{ name: SHORT_NAMES[provider.slug] ?? provider.name, slug: provider.slug, windows }] : []
  })
}

function tone(remaining: number): string {
  return remaining <= USAGE_WARN_PERCENT
    ? 'text-destructive'
    : remaining <= USAGE_NOTICE_PERCENT
      ? 'text-amber-500'
      : 'text-(--ui-text-tertiary)'
}

function MeterTip({ meters }: { meters: ProviderMeter[] }): ReactElement {
  return (
    <span className="grid w-56 gap-2 py-0.5">
      {meters.map(meter => (
        <span className="grid gap-1" key={meter.slug}>
          <span className="font-medium">{meter.name}</span>
          {meter.windows.map(window => {
            const reset = window.resetMs === null ? null : formatReset(window.resetMs)

            return (
              <span className="flex justify-between gap-3 tabular-nums" key={window.label}>
                <span>{window.label}</span>
                <span>
                  {window.remaining}% left{reset ? `, resets ${reset}` : ''}
                </span>
              </span>
            )
          })}
        </span>
      ))}
    </span>
  )
}

/** Status-bar meter: how much of each plan is left (the tightest window), without leaving Thoth. */
export function UsageMeter(): null | ReactElement {
  const query = useQuery({
    queryKey: ['usage-meter'],
    queryFn: () => getGlobalModelOptions(),
    refetchInterval: REFRESH_MS
  })

  const meters = providerMeters(query.data?.providers ?? [])

  if (meters.length === 0) {
    return null
  }

  return (
    <Tip label={<MeterTip meters={meters} />}>
      <span
        aria-label="Plan usage"
        className="inline-flex h-full items-center gap-2 px-1.5 text-[0.6875rem] tabular-nums"
        role="status"
      >
        {meters.map(meter => (
          <span className={cn('inline-flex gap-1', tone(meter.windows[0].remaining))} key={meter.slug}>
            <span>{meter.name}</span>
            <span>{meter.windows[0].remaining}%</span>
          </span>
        ))}
      </span>
    </Tip>
  )
}
