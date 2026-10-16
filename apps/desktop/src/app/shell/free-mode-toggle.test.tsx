import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'

import { DropdownMenu, DropdownMenuContent } from '@/components/ui/dropdown-menu'

import { FreeModeToggle } from './free-mode-toggle'
import type { ModelMenuController } from './model-catalog-menu'

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.releasePointerCapture = vi.fn()
})

const getFreeMode = vi.fn()
const setFreeMode = vi.fn()

vi.mock('@/hermes', () => ({
  getFreeMode: (...args: unknown[]) => getFreeMode(...args),
  setFreeMode: (...args: unknown[]) => setFreeMode(...args)
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderToggle(onChanged = vi.fn()) {
  const controller: ModelMenuController = {
    applyPreset: vi.fn(),
    current: { effort: '', fast: false, model: 'claude-sonnet-5', provider: 'anthropic' },
    presetFor: () => ({}),
    select: vi.fn(async () => true),
    setOptions: vi.fn()
  }

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DropdownMenu open>
        <DropdownMenuContent>
          <FreeModeToggle className="" controller={controller} onChanged={onChanged} />
        </DropdownMenuContent>
      </DropdownMenu>
    </QueryClientProvider>
  )

  return controller
}

it('turning Free mode on moves the chat to the free model the backend picked', async () => {
  getFreeMode.mockResolvedValue({ enabled: false })
  setFreeMode.mockResolvedValue({ enabled: true, model: 'o/one:free', provider: 'openrouter' })
  const onChanged = vi.fn()
  const controller = renderToggle(onChanged)

  const item = await screen.findByRole('menuitemcheckbox', { name: 'Free mode' })
  await waitFor(() => expect(item.getAttribute('aria-disabled')).toBeNull())
  expect(item.getAttribute('aria-checked')).toBe('false')
  fireEvent.click(item)

  await waitFor(() => expect(controller.select).toHaveBeenCalledWith('o/one:free', 'openrouter'))
  expect(setFreeMode).toHaveBeenCalledWith(true, { connectionId: null, profile: null })
  expect(onChanged).toHaveBeenCalled()
  await waitFor(() => expect(item.getAttribute('aria-checked')).toBe('true'))
})
