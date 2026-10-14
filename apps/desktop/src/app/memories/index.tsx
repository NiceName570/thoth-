import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type ReactElement, useState } from 'react'

import { editMemoryEntry, getMemoryEntries } from '@/hermes'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Loader2, Pencil, Trash2 } from '@/lib/icons'
import { notifyError } from '@/store/notifications'
import type { MemoryEntriesResponse, MemoryFileEntries, MemoryTarget } from '@/types/hermes'

export const MEMORIES_ROUTE = '/memories'
export const MEMORIES_QUERY_KEY = ['memory-entries'] as const

const SECTIONS: Array<{ target: MemoryTarget; title: string; file: string; empty: string }> = [
  { target: 'memory', title: 'Memories', file: 'MEMORY.md', empty: 'Nothing saved yet.' },
  { target: 'user', title: 'About you', file: 'USER.md', empty: 'Nothing saved about you yet.' }
]

// The agent's built-in memory, editable in place. New chats read the files fresh;
// a chat already running keeps the snapshot it started with.
export function MemoriesPage(): ReactElement {
  const query = useQuery({ queryKey: MEMORIES_QUERY_KEY, queryFn: getMemoryEntries })

  return (
    <div className="h-full overflow-y-auto px-6 pb-10 pt-[calc(var(--titlebar-height)+1rem)]">
      <div className="mx-auto flex max-w-3xl flex-col gap-8">
        <header className="flex flex-col gap-1">
          <h1 className="text-lg font-semibold">Memories</h1>
          <p className="text-sm text-(--ui-text-secondary)">
            What Thoth remembers across chats. Edits apply to new chats.
          </p>
        </header>
        {query.isPending && <Loader2 className="size-4 animate-spin" />}
        {query.isError && <p className="text-sm text-destructive">Could not load memories.</p>}
        {query.data &&
          SECTIONS.map(section => (
            <MemorySection data={query.data[section.target]} key={section.target} {...section} />
          ))}
      </div>
    </div>
  )
}

interface MemorySectionProps {
  data: MemoryFileEntries
  empty: string
  file: string
  target: MemoryTarget
  title: string
}

function MemorySection({ data, empty, file, target, title }: MemorySectionProps): ReactElement {
  return (
    <section aria-label={title} className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">
          {title} <span className="font-normal text-(--ui-text-tertiary)">{file}</span>
        </h2>
        <span className="text-xs tabular-nums text-(--ui-text-tertiary)">
          {data.chars.toLocaleString()} / {data.limit.toLocaleString()} chars
        </span>
      </div>
      {data.entries.length === 0 ? (
        <p className="text-sm text-(--ui-text-tertiary)">{empty}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {data.entries.map(entry => (
            <MemoryEntryRow entry={entry} key={entry} target={target} />
          ))}
        </ul>
      )}
    </section>
  )
}

function MemoryEntryRow({ entry, target }: { entry: string; target: MemoryTarget }): ReactElement {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<null | string>(null)
  const [confirmingDelete, setConfirmingDelete] = useState<boolean>(false)
  const [busy, setBusy] = useState<boolean>(false)

  async function commit(content: null | string): Promise<void> {
    setBusy(true)

    try {
      const updated = await editMemoryEntry(target, entry, content)
      queryClient.setQueryData<MemoryEntriesResponse>(MEMORIES_QUERY_KEY, prev =>
        prev ? { ...prev, [target]: updated } : prev
      )
      setDraft(null)
    } catch (err) {
      notifyError(err, content === null ? 'Could not delete memory' : 'Could not save memory')
      await queryClient.invalidateQueries({ queryKey: MEMORIES_QUERY_KEY })
    } finally {
      setBusy(false)
      setConfirmingDelete(false)
    }
  }

  if (draft !== null) {
    return (
      <li className="flex flex-col gap-2 rounded-md border border-(--ui-stroke-tertiary) p-3">
        <Textarea aria-label="Edit memory" autoFocus onChange={e => setDraft(e.target.value)} rows={4} value={draft} />
        <div className="flex justify-end gap-2">
          <Button disabled={busy} onClick={() => setDraft(null)} size="sm" variant="ghost">
            Cancel
          </Button>
          <Button disabled={busy || !draft.trim()} onClick={() => void commit(draft)} size="sm">
            Save
          </Button>
        </div>
      </li>
    )
  }

  return (
    <li className="group flex items-start gap-3 rounded-md border border-(--ui-stroke-tertiary) p-3">
      <p className="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm">{entry}</p>
      <div className="flex shrink-0 gap-1">
        <Button aria-label="Edit" disabled={busy} onClick={() => setDraft(entry)} size="icon-sm" variant="ghost">
          <Pencil className="size-3.5" />
        </Button>
        {confirmingDelete ? (
          <Button disabled={busy} onClick={() => void commit(null)} size="sm" variant="destructive">
            Delete
          </Button>
        ) : (
          <Button aria-label="Delete" disabled={busy} onClick={() => setConfirmingDelete(true)} size="icon-sm" variant="ghost">
            <Trash2 className="size-3.5" />
          </Button>
        )}
      </div>
    </li>
  )
}
