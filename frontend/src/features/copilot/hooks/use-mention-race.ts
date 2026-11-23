/**
 * `@` 菜单的查询竞态闸门：一次查询一个 AbortController + 一个 generation 号。
 *
 * 从 `use-mention-menu` 拆出（后者单 hook 超软红线）。机制本身「为什么不能省」写在
 * use-mention-menu.ts 的文件头（机制 1 / 机制 2），本文件只实现它们：
 *
 * - **迟到结果按 generation 丢弃**：查询词一变就 abort 上一轮、generation +1。
 *   没有这层，「@起」的慢响应会盖掉「@起诉状」的结果——菜单显示的是别的查询的行，
 *   律师按 Enter 就引用错对象。
 * - **一个源失败只静默掉这一组**：四类对象四个源，某一类 500 不该把另外三类一起
 *   带走（那看起来就是「@ 坏了」）。告警的去重与文案由调用方给（`onSourceFailed`）。
 * - **关闭即清空**：菜单关掉时把 generation 推进一格并清空分组，再次打开必须从
 *   pending 开始，不能先闪一眼上次的行。
 *
 * 源列表走 ref 而不进 effect 依赖：调用方传字面量数组（`sources: [mySource]`）时
 * 每次渲染都是新引用，依赖它就会「拉取 → setState → 重渲染 → 再拉取」无限循环
 * （实测会把 jsdom 进程跑到 OOM）。源在会话期间本来就不变，首帧同步一次即可。
 */

import { useEffect, useRef, useState } from 'react'

import type { MentionCandidate, MentionGroupLike, MentionSource } from '../domain'

/** 菜单组：源的结果 + 该组自己的状态（失败时整组消失） */
export interface MentionGroup extends MentionGroupLike {
  title: string
  status: 'pending' | 'ready'
  items: MentionCandidate[]
}

export interface UseMentionRaceOptions {
  /** 菜单是否展开（false = 本轮作废并清空分组） */
  open: boolean
  /** 当前查询词；null = 没有 token（同样作废） */
  query: string | null
  /** 本轮可用的源；顺序 = 分组顺序 */
  sources: readonly MentionSource[]
  /**
   * 换查询 / 关闭时回调一次（共享高亮要跟着作废——上一轮的行已经不存在了）。
   * 必须是稳定引用：它进 effect 依赖。
   */
  onReset: () => void
  /** 单个源失败（文案与去重口径由调用方决定）。必须是稳定引用 */
  onSourceFailed: (source: MentionSource, error: unknown) => void
}

/** 分组视图：按「一次查询一轮」重建，迟到的结果进不来 */
export function useMentionRace({
  open,
  query,
  sources,
  onReset,
  onSourceFailed,
}: UseMentionRaceOptions): MentionGroup[] {
  const [groups, setGroups] = useState<MentionGroup[]>([])
  /** 第几代查询：迟到结果按它丢弃（机制 1） */
  const generationRef = useRef(0)
  /** 源的当前值（不进 effect 依赖，见文件头） */
  const sourcesRef = useRef(sources)

  useEffect(() => {
    sourcesRef.current = sources
  }, [sources])

  useEffect(() => {
    if (!open || query === null) {
      // 关掉时清空：再次打开必须从 pending 开始，不能先闪一眼上次的行
      generationRef.current += 1
      setGroups([])
      onReset()
      return
    }
    const generation = generationRef.current + 1
    generationRef.current = generation
    const controller = new AbortController()
    const active = sourcesRef.current.filter((source) => source.trigger === '@')
    setGroups(active.map((source) => ({ key: source.key, title: source.title, status: 'pending', items: [] })))
    onReset()
    for (const source of active) {
      void source
        .load({ query, signal: controller.signal })
        .then((items) => {
          // 竞态闸门：这一轮已不是最新查询，结果直接丢弃（机制 1）
          if (generation !== generationRef.current) return
          setGroups((prev) => prev.map((g) => (g.key === source.key ? { ...g, status: 'ready', items } : g)))
        })
        .catch((error: unknown) => {
          if (generation !== generationRef.current) return
          // abort 是我们自己发起的（查询词变了 / 菜单关了），不是故障
          if (controller.signal.aborted) return
          // 机制 2：只静默掉这一组，其余组照常
          onSourceFailed(source, error)
          setGroups((prev) => prev.filter((g) => g.key !== source.key))
        })
    }
    return () => controller.abort()
  }, [open, query, onReset, onSourceFailed])

  return groups
}
