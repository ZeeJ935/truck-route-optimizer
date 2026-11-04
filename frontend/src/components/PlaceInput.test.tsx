import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { suggestPlaces, type PlaceSuggestion } from '../api/places'
import { clearPlaceSuggestionCache, SUGGEST_DEBOUNCE_MS } from '../features/places/usePlaceSuggestions'
import { PlaceInput } from './PlaceInput'

const mockedSuggest = vi.mocked(suggestPlaces)

const DALLAS: PlaceSuggestion[] = [
  { label: 'Dallas, TX', type: 'area' },
  { label: 'Dallas, GA', type: 'area' },
  { label: '1600 Dallas Parkway, Plano, TX 75093', type: 'address' },
]

function Harness({ onValue }: { onValue?: (value: string) => void }) {
  const [value, setValue] = useState('')
  return (
    <>
      <label htmlFor="origin">Origin</label>
      <PlaceInput
        id="origin"
        label="Origin"
        value={value}
        onChange={(next) => {
          setValue(next)
          onValue?.(next)
        }}
      />
    </>
  )
}

const input = () => screen.getByRole('combobox', { name: 'Origin' })
const wait = (ms: number) => act(() => new Promise((resolve) => setTimeout(resolve, ms)))

beforeEach(() => {
  clearPlaceSuggestionCache()
  mockedSuggest.mockReset()
  mockedSuggest.mockResolvedValue(DALLAS)
})

describe('PlaceInput suggestions', () => {
  it('does not search before 3 characters', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(input(), 'Da')
    await wait(SUGGEST_DEBOUNCE_MS + 100)
    expect(mockedSuggest).not.toHaveBeenCalled()
    expect(input()).toHaveAttribute('aria-expanded', 'false')
  })

  it('debounces typing into one search for the latest text', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(input(), 'Dallas')
    await waitFor(() => expect(mockedSuggest).toHaveBeenCalledTimes(1))
    await wait(SUGGEST_DEBOUNCE_MS + 100)
    expect(mockedSuggest).toHaveBeenCalledTimes(1)
    expect(mockedSuggest.mock.calls[0][0]).toBe('Dallas')
  })

  it('cancels an outdated request when the text changes', async () => {
    const signals: AbortSignal[] = []
    mockedSuggest.mockImplementation((_query, signal) => {
      signals.push(signal!)
      return new Promise(() => {}) // never resolves
    })
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(input(), 'Dall')
    await waitFor(() => expect(signals).toHaveLength(1))
    await user.type(input(), 'as')
    expect(signals[0].aborted).toBe(true)
    await waitFor(() => expect(signals).toHaveLength(2))
  })

  it('answers a repeat search from the cache', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(input(), 'Dall')
    await screen.findByRole('option', { name: /Dallas, TX/ })
    await user.clear(input())
    await user.type(input(), 'dall')
    expect(await screen.findByRole('option', { name: /Dallas, TX/ })).toBeInTheDocument()
    expect(mockedSuggest).toHaveBeenCalledTimes(1)
  })

  it('is an accessible combobox with a labelled list of options', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(input(), 'Dall')
    const list = await screen.findByRole('listbox', { name: 'Origin suggestions' })
    expect(input()).toHaveAttribute('aria-expanded', 'true')
    expect(input()).toHaveAttribute('aria-controls', list.id)
    expect(input()).toHaveAttribute('aria-autocomplete', 'list')
    expect(screen.getAllByRole('option')).toHaveLength(3)
    expect(screen.getByText('3 suggestions available.')).toBeInTheDocument()
  })

  it('selects with the keyboard: arrows move, Enter chooses, Escape closes', async () => {
    const onValue = vi.fn()
    const user = userEvent.setup()
    render(<Harness onValue={onValue} />)
    await user.type(input(), 'Dall')
    await screen.findByRole('listbox')
    await user.keyboard('{ArrowDown}{ArrowDown}')
    const active = screen.getAllByRole('option')[1]
    expect(active).toHaveAttribute('aria-selected', 'true')
    expect(input()).toHaveAttribute('aria-activedescendant', active.id)
    await user.keyboard('{Enter}')
    expect(input()).toHaveValue('Dallas, GA')
    expect(input()).toHaveAttribute('aria-expanded', 'false')

    await user.type(input(), 'x')
    await screen.findByRole('listbox')
    await user.keyboard('{Escape}')
    expect(input()).toHaveAttribute('aria-expanded', 'false')
    expect(onValue).toHaveBeenLastCalledWith('Dallas, GAx')
  })

  it('selects with a mouse click', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(input(), 'Dall')
    await user.click(await screen.findByRole('option', { name: /1600 Dallas Parkway/ }))
    expect(input()).toHaveValue('1600 Dallas Parkway, Plano, TX 75093')
    expect(input()).toHaveFocus()
  })

  it('selects with a touch tap without losing focus first', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(input(), 'Dall')
    const option = await screen.findByRole('option', { name: /Dallas, TX/ })
    const pointerDown = fireEvent.pointerDown(option, { pointerType: 'touch' })
    expect(pointerDown).toBe(false) // default prevented, so the input keeps focus
    fireEvent.click(option)
    expect(input()).toHaveValue('Dallas, TX')
  })

  it('keeps free typing working when suggestions fail', async () => {
    mockedSuggest.mockRejectedValue(new Error('network down'))
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(input(), '742 Evergreen Terrace, Springfield')
    await waitFor(() => expect(mockedSuggest).toHaveBeenCalled())
    await wait(50)
    expect(input()).toHaveValue('742 Evergreen Terrace, Springfield')
    expect(input()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('option')).not.toBeInTheDocument()
  })
})
