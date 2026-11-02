import type { MbidList } from '../../api'
import { listMbidTypes } from '../../api'
import { errMessage } from '@/lib/errors'
import { useEffect, useState } from 'react'

// ───────────────────────── 小工具 ─────────────────────────

/** 文书类型列表（只拉一次，页面内共享） */
export function useTypeList() {
  const [s, setS] = useState<{ loading: boolean; data: MbidList | null; error: string | null }>({
    loading: true,
    data: null,
    error: null,
  })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let alive = true
    setS((v) => ({ ...v, loading: true }))
    listMbidTypes()
      .then((d) => alive && setS({ loading: false, data: d, error: null }))
      .catch((e) => alive && setS({ loading: false, data: null, error: errMessage(e, '加载失败') }))
    return () => {
      alive = false
    }
  }, [nonce])

  return { ...s, reload: () => setNonce((n) => n + 1) }
}

/** 触发浏览器下载。文件名后端已按 content-disposition 给过，这里用调用方拼的名。 */
export function saveBlob(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  // 立刻 revoke 会让 Safari 偶发下载空文件
  setTimeout(() => URL.revokeObjectURL(href), 4000)
}

export function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}
