import { QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { queryClient } from '@/lib/query-client'
import type { MemoryEntriesResponse } from '@/types/hermes'

import { MemoriesPage } from './index'

vi.mock('@/hermes', () => ({ editMemoryEntry: vi.fn(), getMemoryEntries: vi.fn() }))

import * as hermes from '@/hermes'

const mocked = vi.mocked(hermes)

const DATA: MemoryEntriesResponse = {
  memory: { chars: 50, enabled: true, entries: ['Project lives in Desktop/Thoth', 'Use Ollama for quick chats'], limit: 2200 },
  user: { chars: 21, enabled: true, entries: ['Prefers terse answers'], limit: 1375 }
}

beforeEach((): void => {
  queryClient.clear()
  mocked.getMemoryEntries.mockResolvedValue(DATA)
})

afterEach((): void => {
  cleanup()
  vi.clearAllMocks()
})

function renderPage(): void {
  render(
    <QueryClientProvider client={queryClient}>
      <MemoriesPage />
    </QueryClientProvider>
  )
}

it('lists memories and facts about the user', async () => {
  renderPage()

  expect(await screen.findByText('Use Ollama for quick chats')).toBeTruthy()
  expect(screen.getByText('Prefers terse answers')).toBeTruthy()
})

it('saves an edited memory with the full original entry pinned', async () => {
  mocked.editMemoryEntry.mockResolvedValue({ ...DATA.memory, entries: ['Project lives in Desktop/Thoth', 'Use Codex'] })
  renderPage()
  const row = (await screen.findByText('Use Ollama for quick chats')).closest('li')!

  fireEvent.click(row.querySelector('[aria-label="Edit"]')!)
  fireEvent.change(screen.getByLabelText('Edit memory'), { target: { value: 'Use Codex' } })
  fireEvent.click(screen.getByText('Save'))

  await waitFor(() => expect(screen.getByText('Use Codex')).toBeTruthy())
  expect(mocked.editMemoryEntry).toHaveBeenCalledWith('memory', 'Use Ollama for quick chats', 'Use Codex')
})

it('deletes a memory only after the second click', async () => {
  mocked.editMemoryEntry.mockResolvedValue({ ...DATA.user, entries: [] })
  renderPage()
  const row = (await screen.findByText('Prefers terse answers')).closest('li')!

  fireEvent.click(row.querySelector('[aria-label="Delete"]')!)
  expect(mocked.editMemoryEntry).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('Delete'))

  await waitFor(() => expect(screen.queryByText('Prefers terse answers')).toBeNull())
  expect(mocked.editMemoryEntry).toHaveBeenCalledWith('user', 'Prefers terse answers', null)
})
