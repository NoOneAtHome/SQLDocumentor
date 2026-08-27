import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './msw/server'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
// With `globals: false` Testing Library cannot register its own afterEach cleanup.
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())
