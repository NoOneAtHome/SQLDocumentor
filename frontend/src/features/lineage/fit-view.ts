/** Imperative "fit view" bridge so the controls bar / keyboard can reach the React Flow instance. */
export const fitRef: { current: null | (() => void) } = { current: null }

export function fitLineageView(): void {
  fitRef.current?.()
}
