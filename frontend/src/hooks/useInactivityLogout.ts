import { useEffect } from 'react'

const ACTIVITY_EVENTS: Array<keyof WindowEventMap> = [
  'mousemove',
  'mousedown',
  'keydown',
  'scroll',
  'touchstart',
  'click',
]

export function useInactivityLogout(
  enabled: boolean,
  timeoutMs: number,
  onTimeout: () => void
): void {
  useEffect(() => {
    if (!enabled) return

    let timerId: number | null = null

    const resetTimer = () => {
      if (timerId !== null) {
        globalThis.clearTimeout(timerId)
      }

      timerId = globalThis.setTimeout(() => {
        onTimeout()
      }, timeoutMs)
    }

    for (const eventName of ACTIVITY_EVENTS) {
      globalThis.addEventListener(eventName, resetTimer, { passive: true })
    }

    resetTimer()

    return () => {
      for (const eventName of ACTIVITY_EVENTS) {
        globalThis.removeEventListener(eventName, resetTimer)
      }

      if (timerId !== null) {
        globalThis.clearTimeout(timerId)
      }
    }
  }, [enabled, onTimeout, timeoutMs])
}
