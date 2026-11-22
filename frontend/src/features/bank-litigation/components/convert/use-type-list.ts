import { useEffect, useState } from 'react'

import { errMessage } from '@/lib/errors'

import type { MbidList } from '../../api'
import { listMbidTypes } from '../../api'

/**
 * 文书类型列表（只拉一次，页面内共享）。
 *
 * 挪出 `convert-utils.ts` 是为了按文件名能找到它：`convert-utils.ts` 放纯工具
 * （`saveBlob` / `fmtSize`），hook 一律 `use-xxx.ts`。
 * 重新拉取口径不变：`reload()` 只是把 nonce +1，依赖数组仍只有 `[nonce]`。
 */
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
