import { cn } from '@/lib/utils'

interface PageHeaderProps {
  eyebrow?: React.ReactNode
  title: React.ReactNode
  description?: React.ReactNode
  actions?: React.ReactNode
  className?: string
  children?: React.ReactNode
}

export function PageHeader({ eyebrow, title, description, actions, className, children }: PageHeaderProps) {
  return (
    <header className={cn('flex flex-col gap-3 border-b border-border px-6 pt-5 pb-4', className)}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          {eyebrow && <div className="mb-1 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">{eyebrow}</div>}
          <h1 className="truncate text-[17px] leading-6 font-semibold tracking-tight">{title}</h1>
          {description && <p className="mt-1 max-w-3xl text-[13px] text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  )
}
