/**
 * ExpressionJev — read-only visibility for the jev-observer agent plugin.
 *
 * Answers the two questions the config form cannot: "is it running?" and
 * "which turns did each contextual judgment actually carry?". Every number
 * comes from the plugin's own rows through `/api/plugins/jev-observer/*`;
 * this page never writes and never touches a conversation.
 */

import { Codicon, type PluginRestOptions, useQuery } from '@hermes/plugin-sdk'

import { ClearAll, Knobs, SessionActions, TestPanel } from './controls'

type Rest = <T>(path: string, opts?: PluginRestOptions) => Promise<T>

interface Summary {
  observer_version: string
  observations: Record<string, number>
  contextual: Record<string, number>
  last_capture: null | string
  last_ok: null | string
  last_error: null | { error?: string; observed_at?: string }
  last_context_error: null | { error?: string; observed_at?: string }
  provider: null | string
  settings: { contextual: boolean; context_window: number; open_corrections: number }
  recent_sessions: { session_id: string; observations: number; last: string }[]
}

interface SessionRow {
  session_id: string
  observations: number
  ok: number
  pending: number
  errors: number
  last: string
  contextual: number
}

interface Judgment {
  target?: string
  type?: string
  status: string
  result?: number | string
  scale_max?: number
  low_confidence?: boolean
  confidence?: number
  evidence?: { turn: string; role: string; turn_id: string; text: string }[]
}

interface Turn {
  row_id: number
  turn_id: string
  captured_at: string
  status: string
  error: null | string
  regenerated: boolean
  judgments: null | Record<string, Judgment>
  movement: null | { basis?: { turn_id: string }; changes?: Record<string, { from: unknown; to: unknown }> }
  patterns: null | { description: string; turn_ids: string[] }[]
  context: null | {
    window_turn_ids?: string[]
    correction_turn_ids?: string[]
    span_count?: number
    question_count?: number
    context_window?: number
    open_corrections?: number
    truncated?: boolean
  }
  latency_ms: null | number
  jev_model: null | string
}

const count = (map: Record<string, number> | undefined, key: string) => map?.[key] ?? 0

function when(iso: null | string | undefined): string {
  if (!iso) {return 'never'}

  const ms = Date.now() - new Date(iso).getTime()

  if (!Number.isFinite(ms) || ms < 0) {return iso}

  if (ms < 60_000) {return 'just now'}

  if (ms < 3_600_000) {return `${Math.floor(ms / 60_000)}m ago`}

  if (ms < 86_400_000) {return `${Math.floor(ms / 3_600_000)}h ago`}

  return `${Math.floor(ms / 86_400_000)}d ago`
}

function result(j: Judgment): string {
  if (j.status !== 'judged') {return j.status.replaceAll('_', ' ')}

  if (j.type === 'noul' && typeof j.result === 'number') {return `p=${j.result.toFixed(2)}`}

  if (j.type === 'score' && typeof j.result === 'number') {return `${j.result.toFixed(1)}/${j.scale_max ?? '?'}`}

  return String(j.result ?? '').replaceAll('_', ' ')
}

function Stat({ hint, label, value }: { hint?: string; label: string; value: string }) {
  return (
    <div className="rounded-md border border-(--ui-border) bg-(--ui-bg-secondary) px-3 py-2">
      <div className="text-[0.6875rem] uppercase tracking-wide text-(--ui-text-tertiary)">{label}</div>
      <div className="text-base font-medium tabular-nums text-foreground">{value}</div>
      {hint ? <div className="text-[0.6875rem] text-(--ui-text-tertiary)">{hint}</div> : null}
    </div>
  )
}

function Carried({ context }: { context: Turn['context'] }) {
  if (!context) {return null}

  const window = context.window_turn_ids ?? []
  const corrections = context.correction_turn_ids ?? []

  return (
    <div className="mt-2 rounded border border-(--ui-border) bg-(--ui-bg-secondary) px-2 py-1.5 text-[0.75rem]">
      <span className="text-(--ui-text-tertiary)">Carried: </span>
      <span className="text-(--ui-text-secondary)">
        {window.length} prior turn{window.length === 1 ? '' : 's'} · {corrections.length} earlier correction
        {corrections.length === 1 ? '' : 's'}
      </span>
      <span className="text-(--ui-text-tertiary)">
        {' '}
        (window {context.context_window ?? '?'}, corrections {context.open_corrections ?? '?'},{' '}
        {context.span_count ?? 0} messages{context.truncated ? ', truncated' : ''})
      </span>
      {window.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {window.map(id => (
            <span
              className="rounded bg-(--ui-bg-tertiary) px-1 py-0.5 font-mono text-[0.625rem] text-(--ui-text-secondary)"
              key={id}
            >
              {id.split(':').pop()}
            </span>
          ))}
        </div>
      ) : null}
      {corrections.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {corrections.map(id => (
            <span
              className="rounded bg-(--ui-bg-tertiary) px-1 py-0.5 font-mono text-[0.625rem] text-(--ui-text-tertiary)"
              key={id}
            >
              correction {id.split(':').pop()}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function TurnCard({ index, turn }: { index: number; turn: Turn }) {
  const judgments = Object.entries(turn.judgments ?? {})
  const changes = turn.movement?.changes ?? {}
  const basis = turn.movement?.basis?.turn_id

  return (
    <div className="rounded-md border border-(--ui-border) px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[0.75rem]">
          <span className="font-medium text-foreground">#{index}</span>
          <span className="font-mono text-(--ui-text-tertiary)">{turn.turn_id.split(':').pop()}</span>
          {turn.regenerated ? <span className="text-(--ui-text-tertiary)">· regenerated</span> : null}
        </div>
        <div className="text-[0.6875rem] text-(--ui-text-tertiary)">
          {when(turn.captured_at)} · {turn.latency_ms ?? '?'} ms · {turn.jev_model ?? 'unknown model'}
        </div>
      </div>

      {turn.status !== 'ok' ? (
        <div className="mt-1 text-[0.75rem] text-(--ui-text-secondary)">
          {turn.status}: {turn.error ?? 'awaiting observation'}
        </div>
      ) : null}

      <Carried context={turn.context} />

      {judgments.length > 0 ? (
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[0.75rem]">
          {judgments.map(([id, j]) => (
            <div className="min-w-0" key={id}>
              <span className="text-(--ui-text-secondary)">{id}</span>{' '}
              <span className="text-(--ui-text-tertiary)">({j.target ?? '?'})</span>{' '}
              <span className="text-foreground">{result(j)}</span>
              {j.low_confidence ? <span className="text-(--ui-text-tertiary)"> (low conf)</span> : null}
              {changes[id] ? (
                <span className="text-(--ui-text-tertiary)">
                  {' '}
                  · changed from {String(changes[id].from).replaceAll('_', ' ')}
                  {basis ? ` @ ${basis.split(':').pop()}` : ''}
                </span>
              ) : null}
              {j.evidence?.[0] ? (
                <div className="truncate text-[0.6875rem] text-(--ui-text-tertiary)">“{j.evidence[0].text}”</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {(turn.patterns ?? []).map(p => (
        <div className="mt-1 text-[0.75rem] text-(--ui-text-secondary)" key={p.description}>
          pattern: {p.description} <span className="text-(--ui-text-tertiary)">(turns {p.turn_ids.join(', ')})</span>
        </div>
      ))}
    </div>
  )
}

function Timeline({ rest, session }: { rest: Rest; session: string }) {
  const { data, error, isLoading } = useQuery({
    queryFn: () =>
      rest<{ error?: string; run?: string; turns: Turn[] }>(`/timeline?session=${encodeURIComponent(session)}`),
    queryKey: ['jev-observer', 'timeline', session]
  })

  if (isLoading) {return <div className="p-2 text-[0.75rem] text-(--ui-text-tertiary)">Loading observations…</div>}

  if (error) {return <div className="p-2 text-[0.75rem] text-(--ui-text-secondary)">Could not load: {String(error)}</div>}

  if (data?.error) {return <div className="p-2 text-[0.75rem] text-(--ui-text-secondary)">{data.error}</div>}

  if (!data?.turns?.length) {
    return <div className="p-2 text-[0.75rem] text-(--ui-text-tertiary)">No contextual observations for this conversation.</div>
  }

  return (
    <div className="mt-2 flex flex-col gap-2">
      <div className="text-[0.6875rem] text-(--ui-text-tertiary)">
        run <span className="font-mono">{data.run ?? 'live'}</span> · {data.turns.length} turn
        {data.turns.length === 1 ? '' : 's'} · observable-signal judgments, not feelings
      </div>
      {data.turns.map((turn, i) => (
        <TurnCard index={i + 1} key={turn.row_id} turn={turn} />
      ))}
    </div>
  )
}

export function JevObserverPage({ rest }: { rest: Rest }) {
  const summary = useQuery({ queryFn: () => rest<Summary>('/summary'), queryKey: ['jev-observer', 'summary'], refetchInterval: 15_000 })

  const sessions = useQuery({
    queryFn: () => rest<{ sessions: SessionRow[] }>('/sessions?limit=30'),
    queryKey: ['jev-observer', 'sessions'],
    refetchInterval: 15_000
  })

  if (summary.isLoading) {return <div className="text-[0.75rem] text-(--ui-text-tertiary)">Loading ExpressionJev…</div>}

  if (summary.error) {
    return (
      <div className="text-[0.75rem] text-(--ui-text-secondary)">
        Could not reach the jev-observer API: {String(summary.error)}. If the plugin was just updated, restart the app.
      </div>
    )
  }

  const s = summary.data
  const rows = sessions.data?.sessions ?? []
  const pending = count(s?.observations, 'pending')
  const errors = count(s?.observations, 'error')

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="flex items-center gap-2">
          <Codicon name="eye" />
          <h2 className="text-sm font-semibold text-foreground">ExpressionJev</h2>
          <span
            className="rounded-full border border-(--ui-border) px-2 py-0.5 text-[0.6875rem] text-(--ui-text-secondary)"
            title={s?.last_ok ? `last observation ${s.last_ok}` : 'no observations yet'}
          >
            {s?.provider ? `observing via ${s.provider}` : 'no Jev key configured'}
          </span>
        </div>
        <p className="mt-1 text-[0.75rem] text-(--ui-text-tertiary)">
          Passive scoring of completed exchanges — never alters prompts, replies or memory. Window size and rubric live
          under “Agent settings”; the provider key is in Settings ▸ Providers.
        </p>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <Stat
          hint={`${pending} pending · ${errors} failed`}
          label="Observations"
          value={String(count(s?.observations, 'ok'))}
        />
        <Stat hint={`${count(s?.contextual, 'pending')} pending`} label="Contextual" value={String(count(s?.contextual, 'ok'))} />
        <Stat
          hint={s?.settings?.contextual ? 'contextual on' : 'contextual off'}
          label="Window / corrections"
          value={`${s?.settings?.context_window ?? '?'} / ${s?.settings?.open_corrections ?? '?'}`}
        />
        <Stat
          hint={s?.last_capture ? s.last_capture.replace('T', ' ').slice(0, 19) : undefined}
          label="Last capture"
          value={when(s?.last_capture)}
        />
      </div>

      <Knobs rest={rest} settings={s?.settings ?? { context_window: 4, contextual: true, open_corrections: 3 }} />
      <TestPanel rest={rest} />

      {s?.last_error ? (
        <div className="rounded border border-(--ui-border) px-2 py-1.5 text-[0.75rem] text-(--ui-text-secondary)">
          Last failure ({when(s.last_error.observed_at)}): <span className="font-mono">{s.last_error.error}</span>
        </div>
      ) : null}

      <div>
        <div className="mb-1 text-[0.6875rem] uppercase tracking-wide text-(--ui-text-tertiary)">Conversations</div>
        {rows.length === 0 ? (
          <div className="text-[0.75rem] text-(--ui-text-tertiary)">No conversations observed yet.</div>
        ) : (
          <div className="max-h-80 overflow-auto rounded-md border border-(--ui-border)">
            {rows.map(row => (
              <details className="border-b border-(--ui-border) px-2 py-1.5 last:border-b-0" key={row.session_id}>
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[0.75rem]">
                  <span className="font-mono text-(--ui-text-secondary)">{row.session_id}</span>
                  <span className="text-(--ui-text-tertiary)">
                    {row.ok} observed · {row.contextual} contextual · {when(row.last)}
                    {row.errors ? ` · ${row.errors} failed` : ''}
                  </span>
                </summary>
                <SessionActions rest={rest} session={row.session_id} />
                <Timeline rest={rest} session={row.session_id} />
              </details>
            ))}
          </div>
        )}
      </div>

      <ClearAll rest={rest} />
    </div>
  )
}


