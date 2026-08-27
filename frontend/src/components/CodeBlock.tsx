import { WrapText } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Toggle } from '@/components/ui/toggle'
import { MAX_DEFINITION_HIGHLIGHT_BYTES } from '@/lib/constants'
import { highlightSql } from '@/lib/shiki'
import { cn } from '@/lib/utils'
import { CopyButton } from './CopyButton'

interface CodeBlockProps {
  code: string
  language?: 'sql'
  className?: string
  /** Skip highlighting (e.g. > 200 KB) and render a plain `<pre>`. */
  plain?: boolean
  maxHeight?: number | string
  toolbar?: boolean
}

/** SQL code viewer: shiki dual-theme highlighting, lazy-loaded; plain <pre> fallback. */
export function CodeBlock({ code, className, plain, maxHeight, toolbar = true }: CodeBlockProps) {
  const tooBig = code.length > MAX_DEFINITION_HIGHLIGHT_BYTES
  const [highlighted, setHighlighted] = useState<{ code: string; html: string } | null>(null)
  const html = highlighted?.code === code ? highlighted.html : null
  const [wrap, setWrap] = useState(false)

  useEffect(() => {
    if (plain || tooBig) return
    let cancelled = false
    highlightSql(code)
      .then((h) => {
        if (!cancelled) setHighlighted({ code, html: h })
      })
      .catch(() => {
        /* fall back to the plain <pre> */
      })
    return () => {
      cancelled = true
    }
  }, [code, plain, tooBig])

  return (
    <div className={cn('group/code relative min-w-0 rounded-lg border border-border bg-(--shiki-bg)', className)}>
      {toolbar && (
        <div className="absolute top-1.5 right-1.5 z-10 flex items-center gap-1 rounded-md bg-card/80 opacity-0 backdrop-blur transition-opacity group-hover/code:opacity-100 focus-within:opacity-100">
          <Toggle size="sm" pressed={wrap} onPressedChange={setWrap} aria-label="Wrap lines" className="h-6 w-6 p-0">
            <WrapText className="size-3.5" />
          </Toggle>
          <CopyButton value={code} label="Copy SQL" />
        </div>
      )}
      <div
        className={cn('overflow-auto px-3 py-3 font-mono text-[12.5px] leading-[1.4] [&_pre]:m-0 [&_pre]:bg-transparent!', wrap && '[&_.line]:whitespace-pre-wrap [&_pre]:whitespace-pre-wrap')}
        style={{ maxHeight }}
      >
        {html && !plain && !tooBig ? (
          <div dangerouslySetInnerHTML={{ __html: html }} />
        ) : (
          <pre className={cn('text-foreground/90', wrap ? 'whitespace-pre-wrap' : 'whitespace-pre')}>
            <code>{code}</code>
          </pre>
        )}
      </div>
      {tooBig && (
        <div className="border-t border-border px-3 py-1.5 text-[11.5px] text-muted-foreground">
          Definition is larger than 200 KB — syntax highlighting disabled.
        </div>
      )}
    </div>
  )
}
