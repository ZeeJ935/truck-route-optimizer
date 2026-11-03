import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { makeResponse } from '../test/fixtures'
import type { ForecastData } from '../types/api'
import { ForecastSlider } from './ForecastSlider'

const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => from + i)

function forecastWith(available: number[], notice: string | null = null): ForecastData {
  return { ...makeResponse().forecast, available_hours: available, notice }
}

function Harness({ forecast, onHour }: { forecast: ForecastData; onHour?: (hour: number) => void }) {
  const [hour, setHour] = useState(forecast.available_hours[0] ?? 0)
  return (
    <ForecastSlider
      forecast={forecast}
      hour={hour}
      tripOffsetMinutes={300}
      onHourChange={(next) => {
        setHour(next)
        onHour?.(next)
      }}
    />
  )
}

const slider = () => screen.getByRole('slider', { name: 'Forecast hour after departure' })

describe('ForecastSlider', () => {
  it('selects the hour index and shows its time in the trip offset', () => {
    render(<Harness forecast={forecastWith(range(0, 48))} />)
    expect(slider()).toHaveValue('0')
    expect(screen.getByText('+0 h · Nov 3, 08:00 UTC+05:00')).toBeInTheDocument()
    fireEvent.change(slider(), { target: { value: '7' } })
    expect(slider()).toHaveValue('7')
    expect(slider()).toHaveAttribute('aria-valuetext', 'Hour +7: Nov 3, 15:00 UTC+05:00')
    expect(screen.getByText('+7 h · Nov 3, 15:00 UTC+05:00')).toBeInTheDocument()
  })

  it('steps hour by hour like the keyboard arrows and skips hours without data', () => {
    // jsdom has no native range keyboard handling; a browser turns ArrowRight/Left,
    // Home, and End into these same change events (verified live in the browser).
    const hours: number[] = []
    render(<Harness forecast={forecastWith([...range(0, 2), ...range(5, 35)])} onHour={(hour) => hours.push(hour)} />)
    const step = (delta: number) => fireEvent.change(slider(), { target: { value: String(Number(slider().getAttribute('value')) + delta) } })
    step(1)
    step(1)
    step(1)
    expect(hours).toEqual([1, 2, 5]) // 3 and 4 have no data
    step(-1)
    expect(slider()).toHaveValue('2') // stepping back skips the gap too
    fireEvent.change(slider(), { target: { value: '48' } }) // End
    expect(slider()).toHaveValue('35')
    fireEvent.change(slider(), { target: { value: '0' } }) // Home
    expect(slider()).toHaveValue('0')
  })

  it('is focusable for keyboard use', async () => {
    const user = userEvent.setup()
    render(<Harness forecast={forecastWith(range(0, 48))} />)
    await user.tab()
    expect(slider()).toHaveFocus()
  })

  it('cannot select a disabled hour', () => {
    const onHour = vi.fn()
    render(<Harness forecast={forecastWith(range(0, 35))} onHour={onHour} />)
    fireEvent.change(slider(), { target: { value: '42' } })
    expect(slider()).toHaveValue('35')
    expect(onHour).toHaveBeenCalledWith(35)
    expect(onHour).not.toHaveBeenCalledWith(42)
  })

  it('shows disabled hours and explains them with the backend notice', () => {
    const notice = 'No forecast is available for hours 36-48 after departure, so those slider positions are disabled.'
    const { container } = render(<Harness forecast={forecastWith(range(0, 35), notice)} />)
    expect(container.querySelectorAll('.hour-strip .hour-cell-missing')).toHaveLength(13)
    expect(screen.getByText(notice)).toBeInTheDocument()
  })

  it('labels the heatmap time view differently from the checkpoint ETAs', () => {
    render(<Harness forecast={forecastWith(range(0, 48))} />)
    expect(
      screen.getByText('Risk along the whole corridor at the selected time. Checkpoints show weather at each ETA instead.'),
    ).toBeInTheDocument()
  })

  it('is disabled when no hour has data', () => {
    render(<Harness forecast={forecastWith([], 'No corridor forecast is available.')} />)
    expect(slider()).toBeDisabled()
    expect(slider()).toHaveAttribute('aria-valuetext', 'No forecast data')
  })
})
