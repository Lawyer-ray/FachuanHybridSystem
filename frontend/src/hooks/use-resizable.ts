import { useCallback, useRef, useState } from 'react'

interface ResizableOptions {
  minWidth?: number
  maxWidth?: number
  initialWidth?: number
}

export function useResizable({ minWidth = 400, maxWidth = 1200, initialWidth }: ResizableOptions = {}) {
  const [width, setWidth] = useState<number | undefined>(initialWidth)
  const startX = useRef(0)
  const startWidth = useRef(0)

  const onResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      startX.current = e.clientX
      startWidth.current = width ?? minWidth

      const onMouseMove = (ev: MouseEvent) => {
        const delta = ev.clientX - startX.current
        const next = Math.min(maxWidth, Math.max(minWidth, startWidth.current + delta))
        setWidth(next)
      }

      const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove)
        document.removeEventListener('mouseup', onMouseUp)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }

      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', onMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    },
    [width, minWidth, maxWidth],
  )

  return { width, onResizeStart }
}
