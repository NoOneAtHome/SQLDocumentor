import { Skeleton } from '@/components/ui/skeleton'

/** Shown by the router while a lazy route module loads on first render. */
export function RouteFallback() {
  return (
    <div className="space-y-4 p-6" aria-busy>
      <Skeleton className="h-5 w-56" />
      <Skeleton className="h-4 w-96" />
      <Skeleton className="h-64" />
    </div>
  )
}
