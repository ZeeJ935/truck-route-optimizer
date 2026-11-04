import { useId, useState, type FormEvent } from 'react'
import {
  SAMPLING_INTERVALS,
  validateForm,
  type FieldErrors,
  type FieldName,
  type FormValues,
} from '../features/analysis/validateForm'
import { browserOffsetMinutes, defaultDepartureInput, offsetLabel } from '../utils/time'
import { PlaceInput } from './PlaceInput'

interface AnalysisFormProps {
  busy: boolean
  serverErrors: Record<string, string>
  onSubmit: (values: FormValues) => void
  /** Called when the user changes a field or submits a form that fails validation. */
  onEdit: () => void
}

const INITIAL_VALUES: Omit<FormValues, 'departureLocal'> = {
  origin: '',
  destination: '',
  loadWeight: '40000',
  interval: '25',
}

export function AnalysisForm({ busy, serverErrors, onSubmit, onEdit }: AnalysisFormProps) {
  const [values, setValues] = useState<FormValues>(() => ({
    ...INITIAL_VALUES,
    departureLocal: defaultDepartureInput(),
  }))
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitted, setSubmitted] = useState(false)
  const id = useId()

  const update = (field: keyof FormValues) => (value: string) => {
    const next = { ...values, [field]: value }
    setValues(next)
    onEdit()
    if (submitted) setErrors(validateForm(next))
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const found = validateForm(values)
    setErrors(found)
    setSubmitted(true)
    if (Object.keys(found).length === 0) onSubmit(values)
    else onEdit()
  }

  // Client-side errors first; otherwise the backend's error for the field (cleared once the user edits).
  const errorFor = (field: FieldName) => errors[field] ?? serverErrors[field]
  const fieldProps = (field: FieldName) => {
    const message = errorFor(field)
    return {
      id: `${id}-${field}`,
      'aria-invalid': message ? true : undefined,
      'aria-describedby': message ? `${id}-${field}-error` : undefined,
    }
  }
  const errorText = (field: FieldName) => {
    const message = errorFor(field)
    return message ? (
      <p className="field-error" id={`${id}-${field}-error`}>
        {message}
      </p>
    ) : null
  }

  return (
    <form className="analysis-form" onSubmit={handleSubmit} noValidate aria-label="Trip details">
      <div className="field">
        <label htmlFor={`${id}-origin`}>Origin</label>
        <PlaceInput
          {...fieldProps('origin')}
          label="Origin"
          placeholder="City, state or address"
          value={values.origin}
          onChange={update('origin')}
        />
        {errorText('origin')}
      </div>

      <div className="field">
        <label htmlFor={`${id}-destination`}>Destination</label>
        <PlaceInput
          {...fieldProps('destination')}
          label="Destination"
          placeholder="City, state or address"
          value={values.destination}
          onChange={update('destination')}
        />
        {errorText('destination')}
      </div>

      <div className="field">
        <label htmlFor={`${id}-departure_time`}>Departure</label>
        <input
          {...fieldProps('departure_time')}
          type="datetime-local"
          value={values.departureLocal}
          onChange={(event) => update('departureLocal')(event.target.value)}
        />
        <p className="field-hint">
          Your time zone: {offsetLabel(browserOffsetMinutes(values.departureLocal))}. Trip times are shown in this
          offset.
        </p>
        {errorText('departure_time')}
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor={`${id}-load_weight_lb`}>Load weight (lb)</label>
          <input
            {...fieldProps('load_weight_lb')}
            type="number"
            inputMode="decimal"
            min="1"
            step="any"
            value={values.loadWeight}
            onChange={(event) => update('loadWeight')(event.target.value)}
          />
          {errorText('load_weight_lb')}
        </div>

        <div className="field">
          <label htmlFor={`${id}-sampling_interval_miles`}>Weather every</label>
          <select
            {...fieldProps('sampling_interval_miles')}
            value={values.interval}
            onChange={(event) => update('interval')(event.target.value)}
          >
            {SAMPLING_INTERVALS.map((interval) => (
              <option key={interval} value={interval}>
                {interval} miles
              </option>
            ))}
          </select>
          {errorText('sampling_interval_miles')}
        </div>
      </div>

      <button className="primary-button" type="submit" disabled={busy}>
        {busy ? 'Analyzing…' : 'Find the safest route'}
      </button>
    </form>
  )
}
