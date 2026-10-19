import { useState } from 'react'
import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query'

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

/** UseQueryResult 是辨析联合类型（interface 不能 extends），用交叉类型扩展 */
export type TypeaheadSearch<T> = UseQueryResult<T, Error> & {
  /** 输入框的 raw 值（即时响应，未防抖） */
  keyword: string
  setKeyword: React.Dispatch<React.SetStateAction<string>>
  /** trim + 防抖后的关键词（进 queryKey 的那个值） */
  debounced: string
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
  return { keyword, setKeyword, debounced, ...query }
}
