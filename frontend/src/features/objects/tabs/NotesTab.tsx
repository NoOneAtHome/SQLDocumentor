import type { ObjectDetail } from '@/api/types'
import { DescriptionEditor } from '@/features/annotations/DescriptionEditor'
import { NotesEditor } from '@/features/annotations/NotesEditor'
import { TagInput } from '@/features/annotations/TagInput'
import { formatDateTime } from '@/lib/format'

export function NotesTab({ scanId, detail, connection }: { scanId: number; detail: ObjectDetail; connection: string }) {
  const s = detail.summary
  const a = detail.annotation
  return (
    <div className="max-w-3xl space-y-6 p-6">
      <section className="space-y-1.5">
        <h2 className="text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Description</h2>
        <p className="text-[12px] text-muted-foreground">Overrides the catalog MS_Description in listings and search. Stored per object key, so it survives rescans.</p>
        <DescriptionEditor scanId={scanId} connection={connection} target={s} value={a?.description ?? null} fallback={detail.ms_description} />
      </section>
      <section className="space-y-1.5">
        <h2 className="text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Tags</h2>
        <TagInput scanId={scanId} connection={connection} target={s} tags={a?.tags ?? []} />
      </section>
      <section className="space-y-1.5">
        <h2 className="text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Notes</h2>
        <NotesEditor scanId={scanId} connection={connection} target={s} value={a?.notes ?? null} />
      </section>
      {a && <p className="text-[11.5px] text-muted-foreground">Last edited {formatDateTime(a.updated_at)}</p>}
    </div>
  )
}
