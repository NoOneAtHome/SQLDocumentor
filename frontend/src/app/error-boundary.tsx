import { CircleAlert, House, RefreshCw } from 'lucide-react'
import { Link, isRouteErrorResponse, useRouteError } from 'react-router'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/utils'
import { NotFoundPage } from './routes/not-found'

/** Route-level error boundary: 404s render the friendly page, anything else a retry card. */
export function RouteErrorBoundary() {
  const error = useRouteError()
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFoundPage />
  const message = isRouteErrorResponse(error) ? `${error.status} ${error.statusText}` : errorMessage(error)
  return (
    <div className="flex h-full min-h-[60vh] items-center justify-center p-6">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6">
        <div className="mb-3 flex items-center gap-2 text-destructive">
          <CircleAlert className="size-4" />
          <h1 className="text-[15px] font-semibold">Something went wrong</h1>
        </div>
        <p className="mb-4 font-mono text-[12.5px] break-words text-muted-foreground">{message}</p>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => window.location.reload()}>
            <RefreshCw /> Reload
          </Button>
          <Button size="sm" variant="outline" asChild>
            <Link to="/">
              <House /> Home
            </Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
