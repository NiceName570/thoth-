/**
 * Interactive controls for the ExpressionJev page: the three knobs, a live
 * one-shot test call, per-conversation re-score, and clearing.
 *
 * All writes go through `/api/plugins/jev-observer/*`; the chat path is never
 * touched by any of them.
 */

import { type PluginRestOptions, queryClient } from '@hermes/plugin-sdk'
import { useState } from 'react'

type Rest = <T>(path: string, opts?: PluginRestOptions) => Promise<T>

const LABEL = 'text-[0.6875rem] uppercase tracking-wide text-(--ui-text-tertiary)'

const BTN =
  'inline-flex items-center gap-1 rounded border border-(--ui-border) px-2 py-1 text-[0.75rem] text-(--ui-text-secondary) hover:bg-(--chrome-action-hover) disabled:opacity-50'

const INPUT =
  'w-16 rounded border border-(--ui-border) bg-(--ui-bg-secondary) px-1.5 py-0.5 text-[0.75rem] text-foreground'

async function refresh() {
  await queryClient.invalidateQueries({ queryKey: ['jev-observer'] })
}

export function Knobs({
  rest,
  settings
}: {
  rest: Rest
  settings: { contextual: boolean; context_window: number; open_corrections: number }
}) {
  const [draft, setDraft] = useState(settings)
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [error, setError] = useState<null | string>(null)

  const dirty =
    draft.contextual !== settings.contextual ||
    draft.context_window !== settings.context_window ||
    draft.open_corrections !== settings.open_corrections

  const save = async () => {
    setState('saving')
    setError(null)

    try {
      await rest('/settings', { body: draft, method: 'POST' })
      await refresh()
      setState('saved')
    } catch (e) {
      setState('error')
      setError(String(e))
    }
  }

  return (
    <div className="rounded-md border border-(--ui-border) px-3 py-2">
      <div className={LABEL}>Observer knobs</div>
      <div className="mt-1 flex flex-wrap items-center gap-4 text-[0.75rem] text-(--ui-text-secondary)">
        <label className="flex items-center gap-2">
          <input
            checked={draft.contextual}
            onChange={e => setDraft({ ...draft, contextual: e.target.checked })}
            type="checkbox"
          />
          Contextual observer
        </label>
        <label className="flex items-center gap-2">
          Context window
          <input
            className={INPUT}
            max={12}
            min={0}
            onChange={e => setDraft({ ...draft, context_window: Number(e.target.value) })}
            type="number"
            value={draft.context_window}
          />
        </label>
        <label className="flex items-center gap-2">
          Earlier corrections
          <input
            className={INPUT}
            max={6}
            min={0}
            onChange={e => setDraft({ ...draft, open_corrections: Number(e.target.value) })}
            type="number"
            value={draft.open_corrections}
          />
        </label>
        <button className={BTN} disabled={!dirty || state === 'saving'} onClick={save} type="button">
          {state === 'saving' ? 'Saving…' : 'Save'}
        </button>
        {state === 'saved' && !dirty ? <span className="text-(--ui-text-tertiary)">saved</span> : null}
        {error ? <span className="text-(--ui-text-secondary)">{error}</span> : null}
      </div>
      <div className="mt-1 text-[0.6875rem] text-(--ui-text-tertiary)">
        These change what Jev is asked, never what the model replies. Apply them to an existing
        conversation with “Re-score” to compare judgments.
      </div>
    </div>
  )
}

export function TestPanel({ rest }: { rest: Rest }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<null | { ok: boolean; error?: string; provider?: string; observer?: string; ranked?: [string, number][]; count?: number }>(null)

  const run = async () => {
    setBusy(true)
    setResult(null)

    try {
      setResult(await rest('/test', { body: { text }, method: 'POST' }))
    } catch (e) {
      setResult({ error: String(e), ok: false })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-md border border-(--ui-border) px-3 py-2">
      <div className={LABEL}>Test a reply (one live call, nothing stored)</div>
      <textarea
        className="mt-1 h-16 w-full resize-y rounded border border-(--ui-border) bg-(--ui-bg-secondary) px-2 py-1 text-[0.75rem] text-foreground"
        onChange={e => setText(e.target.value)}
        placeholder="Paste an assistant reply to score…"
        value={text}
      />
      <div className="mt-1 flex items-center gap-2">
        <button className={BTN} disabled={busy || !text.trim()} onClick={run} type="button">
          {busy ? 'Scoring…' : 'Run test'}
        </button>
        {result?.ok ? (
          <span className="text-[0.6875rem] text-(--ui-text-tertiary)">
            {result.provider} · {result.observer} · {result.count} signals
          </span>
        ) : null}
        {result && !result.ok ? <span className="text-[0.75rem] text-(--ui-text-secondary)">{result.error}</span> : null}
      </div>
      {result?.ok && result.ranked?.length ? (
        <div className="mt-2 grid max-h-40 grid-cols-3 gap-x-3 gap-y-0.5 overflow-auto text-[0.6875rem]">
          {result.ranked.map(([name, p]) => (
            <div className="flex justify-between gap-2" key={name}>
              <span className="truncate text-(--ui-text-secondary)">{name}</span>
              <span className="tabular-nums text-foreground">{p.toFixed(2)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function SessionActions({ rest, session }: { rest: Rest; session: string }) {
  const [note, setNote] = useState<null | string>(null)
  const [busy, setBusy] = useState<null | 'rescore' | 'clear'>(null)

  const rescore = async () => {
    setBusy('rescore')
    setNote(null)

    try {
      const r = await rest<{ message: string; run: string }>('/rescore', { body: { session }, method: 'POST' })
      setNote(`${r.message} run ${r.run}`)
      await refresh()
    } catch (e) {
      setNote(String(e))
    } finally {
      setBusy(null)
    }
  }

  const clear = async () => {
    if (!window.confirm(`Delete all observations for ${session}?\n\nA database backup is written first.`)) {return}
    setBusy('clear')
    setNote(null)

    try {
      const r = await rest<{ backup: string; context_rows: number; observations: number }>('/clear', {
        body: { confirm: true, session },
        method: 'POST'
      })

      setNote(`cleared ${r.observations} observations (${r.context_rows} contextual) · backup ${r.backup}`)
      await refresh()
    } catch (e) {
      setNote(String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mt-1 flex flex-wrap items-center gap-2">
      <button className={BTN} disabled={busy !== null} onClick={rescore} type="button">
        {busy === 'rescore' ? 'Queuing…' : 'Re-score under current knobs'}
      </button>
      <button className={BTN} disabled={busy !== null} onClick={clear} type="button">
        {busy === 'clear' ? 'Clearing…' : 'Clear this conversation'}
      </button>
      {note ? <span className="text-[0.6875rem] text-(--ui-text-tertiary)">{note}</span> : null}
    </div>
  )
}

export function ClearAll({ rest }: { rest: Rest }) {
  const [note, setNote] = useState<null | string>(null)
  const [busy, setBusy] = useState(false)

  const clear = async () => {
    if (!window.confirm('Delete ALL Jev observations for every conversation?\n\nA database backup is written first.')) {return}
    setBusy(true)
    setNote(null)

    try {
      const r = await rest<{ backup: string; context_rows: number; observations: number }>('/clear', {
        body: { confirm: true },
        method: 'POST'
      })

      setNote(`cleared ${r.observations} observations (${r.context_rows} contextual) · backup ${r.backup}`)
      await refresh()
    } catch (e) {
      setNote(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-(--ui-border) pt-3">
      <button className={BTN} disabled={busy} onClick={clear} type="button">
        {busy ? 'Clearing…' : 'Clear all observations'}
      </button>
      <span className="text-[0.6875rem] text-(--ui-text-tertiary)">
        Writes a timestamped SQLite backup next to data.db first.
      </span>
      {note ? <span className="text-[0.6875rem] text-(--ui-text-tertiary)">{note}</span> : null}
    </div>
  )
}

