import createFetchClient, { type Middleware } from 'openapi-fetch'
import createClient from 'openapi-react-query'
import type { paths } from './schema'

/**
 * Typed fetch client + TanStack Query bindings for the whole API.
 *
 * Under vitest (jsdom) `fetch` needs an absolute URL, so the base points at the jsdom origin;
 * in the browser it is relative so the Vite proxy (dev) or same-origin FastAPI (prod) serves it.
 */
export const fetchClient = createFetchClient<paths>({
  baseUrl: import.meta.env.MODE === 'test' ? 'http://localhost:3000' : '',
})

/**
 * openapi-react-query throws the parsed error body (`{ detail }`) as the query error. Stamp the
 * HTTP status onto it so the UI can tell a 404 ("not in this scan") from a real failure.
 */
const statusMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return response
    const text = await response.clone().text()
    let body: Record<string, unknown>
    try {
      const parsed: unknown = text ? JSON.parse(text) : {}
      body = typeof parsed === 'object' && parsed ? (parsed as Record<string, unknown>) : { detail: String(parsed) }
    } catch {
      body = { detail: text || response.statusText }
    }
    return new Response(JSON.stringify({ ...body, status: response.status }), {
      status: response.status,
      statusText: response.statusText,
      headers: { 'content-type': 'application/json' },
    })
  },
}
fetchClient.use(statusMiddleware)

export const $api = createClient(fetchClient)

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? (typeof detail === 'object' && detail && 'detail' in detail && typeof (detail as { detail: unknown }).detail === 'string'
      ? (detail as { detail: string }).detail
      : `Request failed (${status})`))
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** Unwrap an imperative `fetchClient.GET/POST/...` call into data-or-throw. */
export async function unwrap<R extends { data?: unknown; error?: unknown; response: Response }>(
  promise: Promise<R>,
): Promise<NonNullable<R['data']>> {
  const result = await promise
  if (result.error !== undefined || !result.response.ok) {
    throw new ApiError(result.response.status, result.error)
  }
  return result.data as NonNullable<R['data']>
}

/** Path params for a scan-scoped endpoint (`/api/scans/{scan_id}/...`). */
export function scanPath(scanId: number | string) {
  return { scan_id: Number(scanId) }
}
