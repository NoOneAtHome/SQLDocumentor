import { CircleAlert, RefreshCw } from 'lucide-react'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { cn, errorMessage } from '@/lib/utils'

interface ErrorStateProps {
  error: unknown
  title?: string
  onRetry?: () => void
  retrying?: boolean
  className?: string
}

export function ErrorState({ error, title = 'Could not load', onRetry, retrying, className }: ErrorStateProps) {
  return (
    <Alert variant="destructive" className={cn('items-start', className)}>
      <CircleAlert />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{errorMessage(error)}</AlertDescription>
      {onRetry && (
        <AlertAction>
          <Button size="xs" variant="outline" onClick={onRetry} disabled={retrying}>
            <RefreshCw className={cn(retrying && 'animate-spin')} /> Retry
          </Button>
        </AlertAction>
      )}
    </Alert>
  )
}
