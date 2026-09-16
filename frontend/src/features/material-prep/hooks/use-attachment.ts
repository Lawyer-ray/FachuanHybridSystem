import { useEffect, useState } from 'react'
import { fetchAttachmentBytes } from '../api'

/** 拉附件字节（带鉴权）。返回 { data, objectUrl }。 */
export function useAttachmentBytes(messageId: number, partIndex: number) {
  const [bytes, setBytes] = useState<ArrayBuffer | null>(null)
  const [error, setError] = useState<null | string>(null)

  useEffect(() => {
    let alive = true
    setBytes(null)
    setError(null)
    fetchAttachmentBytes(messageId, partIndex)
      .then((d) => {
        if (alive) setBytes(d)
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : '加载失败')
      })
    return () => {
      alive = false
    }
  }, [messageId, partIndex])

  return { bytes, error }
}
