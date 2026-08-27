import { Plus } from 'lucide-react'
import { useState } from 'react'
import { TagChip } from '@/components/ObjectBadge'
import { Input } from '@/components/ui/input'
import type { ObjectRefKey } from '@/features/objects/hooks/useObjectDetail'
import { useAnnotationMutation, useTags } from './useAnnotation'

export function TagInput({ scanId, connection, target, tags }: { scanId: number; connection: string; target: ObjectRefKey; tags: string[] }) {
  const [draft, setDraft] = useState('')
  const all = useTags()
  const mutation = useAnnotationMutation({ scanId, connection, ref: target })
  const colorOf = (t: string) => all.data?.find((x) => x.tag === t)?.color ?? null
  const add = (t: string) => {
    const tag = t.trim().toLowerCase()
    if (!tag || tags.includes(tag)) return
    mutation.mutate({ tags: [...tags, tag] })
    setDraft('')
  }
  const remove = (t: string) => mutation.mutate({ tags: tags.filter((x) => x !== t) })
  const suggestions = (all.data ?? []).filter((t) => !tags.includes(t.tag) && (!draft || t.tag.includes(draft.toLowerCase())))
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {tags.map((t) => (
          <TagChip key={t} tag={t} color={colorOf(t)} onRemove={() => remove(t)} />
        ))}
        <div className="relative">
          <Plus className="pointer-events-none absolute top-1/2 left-2 size-3 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="add tag"
            list="sqldoc-tags"
            className="h-6 w-32 pl-6 text-[12px]"
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault()
                add(draft)
              }
              if (e.key === 'Backspace' && !draft && tags.length) remove(tags[tags.length - 1]!)
            }}
          />
        </div>
      </div>
      {suggestions.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 text-[11.5px] text-muted-foreground">
          <span>Existing:</span>
          {suggestions.slice(0, 12).map((t) => (
            <button key={t.tag} type="button" onClick={() => add(t.tag)} className="rounded-sm border border-border px-1.5 hover:bg-muted">
              {t.tag} <span className="font-mono text-muted-foreground/70">{t.count}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
