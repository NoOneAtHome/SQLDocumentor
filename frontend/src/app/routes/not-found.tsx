import { House, SearchX } from 'lucide-react'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <div className="flex h-full min-h-[60vh] items-center justify-center p-8">
      <EmptyState
        icon={<SearchX />}
        title="Page not found"
        description="That URL doesn't match anything in SQL Documentor."
        action={
          <Button size="sm" asChild>
            <Link to="/">
              <House /> Home
            </Link>
          </Button>
        }
      />
    </div>
  )
}

export default NotFoundPage
