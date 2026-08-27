import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { ObjectRefKey } from '@/features/objects/hooks/useObjectDetail'
import { useAnnotationMutation } from './useAnnotation'

export function NotesEditor({ scanId, connection, target, value }: { scanId: number; connection: string; target: ObjectRefKey; value: string | null }) {
  const [draft, setDraft] = useState(value ?? '')
  const [lastValue, setLastValue] = useState(value)
  if (value !== lastValue) {
    // Props changed (optimistic update / refetch): reset the draft during render.
    setLastValue(value)
    setDraft(value ?? '')
  }
  const mutation = useAnnotationMutation({ scanId, connection, ref: target })
  const dirty = (value ?? '') !== draft
  const save = () => mutation.mutate({ notes: draft.trim() || null })
  return (
    <div className="space-y-2">
      <Textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={8}
        placeholder="Free-form notes: ownership, gotchas, retention, links…"
        className="font-mono text-[12.5px] leading-5"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && dirty) {
            e.preventDefault()
            save()
          }
        }}
      />
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={save} disabled={!dirty || mutation.isPending}>
          Save notes
        </Button>
        {dirty && (
          <Button size="sm" variant="ghost" onClick={() => setDraft(value ?? '')}>
            Discard
          </Button>
        )}
        <span className="text-[11.5px] text-muted-foreground">⌘↵ to save</span>
      </div>
    </div>
  )
}
