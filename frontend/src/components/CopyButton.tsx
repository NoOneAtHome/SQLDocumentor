import { Check, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn, copyToClipboard } from '@/lib/utils'

export function CopyButton({ value, label = 'Copy', className, size = 'icon-xs' }: { value: string; label?: string; className?: string; size?: 'icon-xs' | 'icon-sm' | 'xs' }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(t)
  }, [copied])
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size={size}
          className={cn('text-muted-foreground', className)}
          aria-label={label}
          onClick={async (e) => {
            e.stopPropagation()
            if (await copyToClipboard(value)) setCopied(true)
          }}
        >
          {copied ? <Check className="text-success" /> : <Copy />}
          {size === 'xs' && (copied ? 'Copied' : label)}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">{copied ? 'Copied' : label}</TooltipContent>
    </Tooltip>
  )
}
