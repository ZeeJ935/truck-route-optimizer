import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { usePlaceSuggestions } from '../features/places/usePlaceSuggestions'

const TYPE_LABEL: Record<string, string> = {
  address: 'Address',
  street: 'Street',
  area: 'City or area',
}

interface PlaceInputProps {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  'aria-invalid'?: boolean
  'aria-describedby'?: string
}

/**
 * A text field with optional place suggestions (WAI-ARIA combobox pattern).
 * Works with mouse, touch, and keyboard (arrows, Enter, Escape). The user can
 * always ignore the suggestions and type any address.
 *
 * The list never covers the rest of the form once it has nothing to add: it stays
 * closed when the text already equals a suggestion, and it closes on submit, on
 * Escape, on blur, and on a click or tap outside the field.
 */
export function PlaceInput({ id, label, value, onChange, placeholder, ...aria }: PlaceInputProps) {
  const listId = useId()
  // Suggestions show only while the user is typing in this field.
  const [typing, setTyping] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const suggestions = usePlaceSuggestions(value, typing)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const typed = value.trim().toLowerCase()
  const alreadyChosen = suggestions.some((suggestion) => suggestion.label.toLowerCase() === typed)
  const open = typing && suggestions.length > 0 && !alreadyChosen
  const optionId = (index: number) => `${listId}-option-${index}`

  const close = () => {
    setTyping(false)
    setActiveIndex(-1)
  }
  // Close on a click or tap outside the field, and when the form is submitted.
  useEffect(() => {
    if (!open) return
    const form = inputRef.current?.form
    const closeList = () => {
      setTyping(false)
      setActiveIndex(-1)
    }
    const onPointerDown = (event: PointerEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) closeList()
    }
    document.addEventListener('pointerdown', onPointerDown)
    form?.addEventListener('submit', closeList)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      form?.removeEventListener('submit', closeList)
    }
  }, [open])

  const choose = (index: number) => {
    onChange(suggestions[index].label)
    close()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!open) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((index) => (index + 1) % suggestions.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => (index <= 0 ? suggestions.length - 1 : index - 1))
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault() // choose the suggestion instead of submitting the form
      choose(activeIndex)
    } else if (event.key === 'Enter') {
      close() // no option chosen: let Enter submit the form with the typed text
    } else if (event.key === 'Escape') {
      event.preventDefault()
      close()
    }
  }

  return (
    <div className="place-input" ref={wrapperRef}>
      <input
        {...aria}
        ref={inputRef}
        id={id}
        type="text"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && activeIndex >= 0 ? optionId(activeIndex) : undefined}
        autoComplete="off"
        placeholder={placeholder}
        value={value}
        onChange={(event) => {
          onChange(event.target.value)
          setTyping(true)
          setActiveIndex(-1)
        }}
        onKeyDown={handleKeyDown}
        onBlur={close}
      />
      <ul id={listId} role="listbox" aria-label={`${label} suggestions`} className="place-options" hidden={!open}>
        {open &&
          suggestions.map((suggestion, index) => (
            <li
              key={suggestion.label}
              id={optionId(index)}
              role="option"
              aria-selected={index === activeIndex}
              className={index === activeIndex ? 'place-option place-option-active' : 'place-option'}
              // Keep focus in the input so the list stays open until a choice is made.
              onPointerDown={(event) => event.preventDefault()}
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => choose(index)}
            >
              <span className="place-option-label">{suggestion.label}</span>
              <span className="place-option-type">{TYPE_LABEL[suggestion.type] ?? 'Place'}</span>
            </li>
          ))}
      </ul>
      <span className="visually-hidden" aria-live="polite">
        {open ? `${suggestions.length} suggestion${suggestions.length === 1 ? '' : 's'} available.` : ''}
      </span>
    </div>
  )
}
