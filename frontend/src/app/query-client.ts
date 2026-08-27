import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, err) => {
        const status = (err as { status?: number } | null)?.status
        if (status === 404 || status === 409) return false
        return count < 1
      },
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
})
