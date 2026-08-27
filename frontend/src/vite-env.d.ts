/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Set to "1" to serve the app against the MSW mock API (`npm run dev:mock`). */
  readonly VITE_MOCK_API?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
