import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { $api, fetchClient, unwrap } from '@/api/client'
import type { Annotation, AnnotationUpsert, ObjectDetail } from '@/api/types'
import { detailQueryKeys, type ObjectRefKey } from '@/features/objects/hooks/useObjectDetail'
import { errorMessage } from '@/lib/utils'

export interface AnnotationTarget {
  scanId: number
  connection: string
  ref: ObjectRefKey
  column?: string | null
}

export type AnnotationPatch = Partial<Pick<AnnotationUpsert, 'description' | 'notes' | 'tags'>>

export function useTags() {
  return $api.useQuery('get', '/api/tags', undefined, { staleTime: 60_000 })
}

function applyPatch(existing: Annotation | null, patch: AnnotationPatch, key: string, column: boolean): Annotation {
  return {
    target_kind: column ? 'column' : 'object',
    target_key: key,
    description: patch.description !== undefined ? (patch.description ?? null) : (existing?.description ?? null),
    notes: patch.notes !== undefined ? (patch.notes ?? null) : (existing?.notes ?? null),
    tags: patch.tags !== undefined ? (patch.tags ?? []) : (existing?.tags ?? []),
    updated_at: new Date().toISOString(),
  }
}

function patchDetail(previous: ObjectDetail, patch: AnnotationPatch, column: string | null | undefined): ObjectDetail {
  const targetKey = `${previous.summary.object_key}${column ? `|${column}` : ''}`
  if (column) {
    return { ...previous, column_annotations: { ...previous.column_annotations, [column]: applyPatch(previous.column_annotations?.[column] ?? null, patch, targetKey, true) } }
  }
  const annotation = applyPatch(previous.annotation ?? null, patch, targetKey, false)
  return { ...previous, annotation, summary: { ...previous.summary, annotation_description: annotation.description, tags: annotation.tags } }
}

/**
 * Upsert / clear annotations with an optimistic update of the composite object detail,
 * then invalidate `/api/tags` (and the detail) once the server answers.
 *
 * The detail can be cached under the name lookup and/or the id lookup (the detail page is
 * reachable by either), so every candidate key is patched, restored and invalidated.
 */
export function useAnnotationMutation({ scanId, connection, ref, column }: AnnotationTarget) {
  const qc = useQueryClient()
  const keys = detailQueryKeys(scanId, ref)

  return useMutation({
    mutationFn: async (patch: AnnotationPatch) => {
      const body: AnnotationUpsert = { connection, db: ref.db ?? '', schema: ref.schema ?? '', name: ref.name, column: column ?? null, ...patch }
      return unwrap(fetchClient.PUT('/api/annotations', { body }))
    },
    onMutate: async (patch: AnnotationPatch) => {
      await Promise.all(keys.map((key) => qc.cancelQueries({ queryKey: key })))
      const previous = keys.map((key) => [key, qc.getQueryData<ObjectDetail>(key)] as const)
      for (const [key, prev] of previous) {
        if (prev) qc.setQueryData<ObjectDetail>(key, patchDetail(prev, patch, column))
      }
      return { previous }
    },
    onError: (err, _patch, ctx) => {
      for (const [key, prev] of ctx?.previous ?? []) {
        if (prev) qc.setQueryData(key, prev)
      }
      toast.error('Could not save annotation', { description: errorMessage(err) })
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['get', '/api/tags'] })
      for (const key of keys) void qc.invalidateQueries({ queryKey: key })
      void qc.invalidateQueries({ queryKey: ['get', '/api/scans/{scan_id}/objects'] })
    },
  })
}
