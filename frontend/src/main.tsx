import '@/index.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from '@/app/providers'

async function bootstrap() {
  if (import.meta.env.VITE_MOCK_API === '1') {
    const { enableMocking } = await import('@/test/msw/browser')
    await enableMocking()
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void bootstrap()
