import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { useDebouncedValue } from './use-debounced-value'

/**
 * typeahead 检索的标准姿势（跨 feature 通用：home / document-recognition /
 * material-prep 五处搜索选择器收敛而来）。
 *
 * 「useState(kw) → trim → useDebouncedValue(250) → useQuery({ queryKey:[…, 防抖词],
 * queryFn:({signal})…, staleTime: 30s, placeholderData: keepPreviousData })」
 * 的同构模式：raw 值喂输入框（UI 即时响应），防抖值进 queryKey（输入停顿后才真正
 * 打后端）；上一请求由 query 的 signal 自动中止，无响应竞态；翻词保留上一屏候选。
 *
 * 各调用方的差异通过 options 收口：queryKey 结构（前缀 / 附加维度）、最短触发长度、
 * 附加启用条件（弹窗开关、tab 等）、防抖毫秒。本 hook 与业务无关，不认识「案件」
 * 或「当事人」——检索函数由调用方注入。
 */

export interface UseTypeaheadSearchOptions<T> {
  /** 完整 queryKey：接收防抖后的关键词，调用方保持自己的 key 结构（前缀 + 附加维度） */
  queryKey: (keyword: string) => readonly unknown[]
  /** 检索函数：keyword 是 trim + 防抖后的值；signal 用于中止上一请求 */
  queryFn: (args: { keyword: string; signal: AbortSignal }) => Promise<T>
  /** 附加启用条件（与 minLength 一起取与），默认 true */
  enabled?: boolean
  /** 最短触发长度（trim 后字符数），默认 1 = 空关键词不发请求；
   *  传 0 允许空词请求（挂载即拉初始候选列表的场景） */
  minLength?: number
  /** 防抖毫秒，默认 250 */
  debounceMs?: number
  /** staleTime，默认 30_000 */
  staleTime?: number
}

/**
 * 对外只暴露被消费的 query 字段：返回值靠 useMemo 稳引用，无法把 useQuery 的整个
 * 结果（trackResult 的 Proxy，每次渲染新建）摊进来，所以不 extends UseQueryResult
 * ——那会要求这里把 20 多个派生字段逐个补齐。缺的字段由调用方用这三个基本量派生。
 */
export interface TypeaheadSearch<T> {
  /** 检索结果（placeholderData 期间是上一屏数据） */
  data: T | undefined
  error: Error | null
  /** data 是上一屏的占位数据（真结果还没回来） */
  isPlaceholderData: boolean
  /** 输入框的 raw 值（即时响应，未防抖） */
  keyword: string
  setKeyword: React.Dispatch<React.SetStateAction<string>>
  /** trim + 防抖后的关键词（进 queryKey 的那个值） */
  debounced: string
  /**
   * 「正在检索」的展示信号，**用它而不是 isFetching**。
   *
   * 本 hook 开了 placeholderData: keepPreviousData：翻词时上一份数据被当作
   * placeholder 交付，此时 isPlaceholderData 恒为真、isFetching 也恒为真，
   * 直接拿 isFetching 当 loading 会让「搜索中…」永远挂着（条件渲染里表现为
   * 候选列表永远出不来）。扣掉 placeholder 那一帧才是用户真正在等的请求。
   */
  isSearching: boolean
}

export function useTypeaheadSearch<T>(opts: UseTypeaheadSearchOptions<T>): TypeaheadSearch<T> {
  const [keyword, setKeyword] = useState('')
  const kwTrim = keyword.trim()
  const debounced = useDebouncedValue(kwTrim, opts.debounceMs ?? 250)
  const query = useQuery<T>({
    queryKey: opts.queryKey(debounced),
    queryFn: ({ signal }) => opts.queryFn({ keyword: debounced, signal }),
    enabled: (opts.enabled ?? true) && debounced.length >= (opts.minLength ?? 1),
    staleTime: opts.staleTime ?? 30_000,
    placeholderData: keepPreviousData,
  })
  const { data, error, isPlaceholderData, isFetching } = query

  // 引用稳定：每次渲染新建对象字面量会让返回值恒变，调用方一旦把它放进
  // useEffect / useMemo 依赖就会每次重跑。
  //
  // 依赖刻意只列解构出来的基本量（data / error / 两个布尔 + hook 自己的 state），
  // 不列 query 本身：useQuery 返回的是 trackResult 的 Proxy，每个渲染基本都是新对象，
  // 拿它当依赖会让 useMemo 每次失效，稳引用白做。下面拼的对象也只放被消费的字段，
  // 不再 `...query` 展开（那会把 Proxy 上的字段重新摊进来，同样失去稳定性）。
  // 缺失的 query 字段（isPending / isLoading / isError 等）由调用方自行派生。
  return useMemo(
    () => ({
      data,
      error,
      isPlaceholderData,
      isSearching: isFetching && !isPlaceholderData,
      keyword,
      setKeyword,
      debounced,
    }),
    // setKeyword 来自 useState，引用恒定，不必列进依赖；其余都是返回值实际读到的值
    [data, error, isPlaceholderData, isFetching, keyword, debounced],
  )
}
