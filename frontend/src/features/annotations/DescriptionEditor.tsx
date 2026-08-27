import { Check, Pencil, X } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { ObjectRefKey } from '@/features/objects/hooks/useObjectDetail'
import { cn } from '@/lib/utils'
import { useAnnotationMutation } from './useAnnotation'

interface Props {
  scanId: number
  connection: string
  target: ObjectRefKey
  column?: string
  /** User description (annotation). */
  value: string | null
  /** Catalog MS_Description shown greyed when no user description exists. */
  fallback?: string | null
  inline?: boolean
}

/** Click-to-edit description; saves on ⌘↵ / blur, Esc cancels, empty clears. */
export function DescriptionEditor({ scanId, connection, target, column, value, fallback, inline }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value ?? '')
  const [lastValue, setLastValue] = useState(value)
  if (value !== lastValue) {
    // Props changed (optimistic update / refetch): reset the draft during render.
    setLastValue(value)
    setDraft(value ?? '')
  }
  const mutation = useAnnotationMutation({ scanId, connection, ref: target, column })

  const save = () => {
    const next = draft.trim()
    if ((value ?? '') !== next) mutation.mutate({ description: next || null })
    setEditing(false)
  }

  if (editing) {
    return (
      <div className={cn('flex items-start gap-1.5', inline ? 'py-0.5' : '')}>
        <Textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={inline ? 1 : 3}
          placeholder={fallback ?? 'Describe this ' + (column ? 'column' : 'object') + '…'}
          className={cn('min-h-0 text-[12.5px]', inline && 'h-7 resize-none py-1')}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setDraft(value ?? '')
              setEditing(false)
            }
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey || inline)) {
              e.preventDefault()
              save()
            }
          }}
          onBlur={save}
        />
        <Button size="icon-xs" variant="ghost" onMouseDown={(e) => e.preventDefault()} onClick={save} aria-label="Save">
          <Check />
        </Button>
        <Button
          size="icon-xs"
          variant="ghost"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => {
            setDraft(value ?? '')
            setEditing(false)
          }}
          aria-label="Cancel"
        >
          <X />
        </Button>
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className={cn(
        'group/desc flex w-full min-w-0 items-start gap-1.5 rounded-md text-left text-[12.5px] hover:bg-muted/60',
        inline ? 'px-1 py-0.5' : 'border border-dashed border-border px-3 py-2',
      )}
      title="Click to edit"
    >
      <span className={cn('min-w-0 flex-1', inline && 'truncate', !value && 'text-muted-foreground italic')}>
        {value ?? fallback ?? (inline ? 'Add description' : 'No description yet — click to add one.')}
        {!value && fallback && <span className="ml-1 font-mono text-[10px] not-italic text-muted-foreground/70">(catalog)</span>}
      </span>
      <Pencil className="mt-0.5 size-3 shrink-0 text-muted-foreground opacity-0 group-hover/desc:opacity-100" />
    </button>
  )
}
