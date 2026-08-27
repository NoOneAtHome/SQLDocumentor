import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

export const worker = setupWorker(...handlers)

/** Start the mock service worker when `VITE_MOCK_API=1` (see `npm run dev:mock`). */
export async function enableMocking(): Promise<void> {
  await worker.start({
    onUnhandledRequest: (req, print) => {
      if (new URL(req.url).pathname.startsWith('/api/')) print.warning()
    },
    quiet: false,
  })
}
