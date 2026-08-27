import type { HighlighterCore } from 'shiki/core'

let highlighterPromise: Promise<HighlighterCore> | null = null

/**
 * Lazily creates a single shiki highlighter with the JS regex engine, the `sql` grammar
 * (there is no T-SQL grammar) and the github light/dark dual theme. Everything is dynamically
 * imported so the ~300 KB grammar/theme payload only loads on the Definition tab.
 */
export function getSqlHighlighter(): Promise<HighlighterCore> {
  highlighterPromise ??= (async () => {
    const [{ createHighlighterCore }, { createJavaScriptRegexEngine }, sql, light, dark] =
      await Promise.all([
        import('shiki/core'),
        import('shiki/engine/javascript'),
        import('@shikijs/langs/sql'),
        import('@shikijs/themes/github-light'),
        import('@shikijs/themes/github-dark'),
      ])
    return createHighlighterCore({
      langs: [sql.default],
      themes: [light.default, dark.default],
      engine: createJavaScriptRegexEngine({ forgiving: true }),
    })
  })()
  return highlighterPromise
}

export async function highlightSql(code: string): Promise<string> {
  const highlighter = await getSqlHighlighter()
  return highlighter.codeToHtml(code, {
    lang: 'sql',
    themes: { light: 'github-light', dark: 'github-dark' },
    defaultColor: false,
  })
}
