import { useEffect, useState } from 'react'

import { errMessage } from '@/lib/errors'

/** 通用「一次性拉取」状态：loading / error / data 三态，够用且不引 react-query */
export interface AsyncState<T> {
  loading: boolean
  error: string | null
  data: T | null
}

const INIT = { loading: true, error: null, data: null } as const

/**
 * 拉一次数据。本 feature 所有读取 hook 的骨架。
 *
 * 为什么不用 react-query：本 feature 的读取全是「进页面拉一次、动作后手动刷新」，
 * 没有共享缓存与失效传播的需求（每个案件的数据只这一个页面看）。手写 effect
 * 反而让「什么时候重新拉」看得见——react-query 的 staleTime 猜错了会静默给旧数据，
 * 而立案状态这种数据给旧的是会出事的。
 */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>(INIT)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((d) => {
        if (alive) setState({ loading: false, error: null, data: d })
      })
      .catch((e) => {
        if (alive) setState({ loading: false, error: errMessage(e, '加载失败'), data: null })
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  return { ...state, reload: () => setNonce((n) => n + 1) }
}
