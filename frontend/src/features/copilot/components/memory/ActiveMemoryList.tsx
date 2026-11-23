/**
 * 已生效记忆的分组列表：自己的 → 团队 → 律所。
 *
 * 从 `MemoryDrawer` 拆出（后者单函数超软红线）。本组件只负责「按作用域分桶 + 空层
 * 不占位」；取数、增删与缓存失效仍留在外壳里，那是**同一份** mutation 的事——
 * 每层各建一套订阅就会多出 N 个 useQueryClient 订阅（SessionRow 踩过同型问题）。
 */

import type { AgentMemoryItem, MemoryScope } from '../../types'
import { MemoryGroup } from './MemoryGroup'

/** 已生效记忆的分组顺序：自己的 → 团队 → 律所（越往后越"别人的"） */
const ACTIVE_SCOPES: MemoryScope[] = ['lawyer', 'team', 'law_firm']

export function ActiveMemoryList({
  active,
  loading,
  onForget,
  forgetting,
}: {
  /** 已生效（`status === 'active'`）的记忆，未分桶 */
  active: readonly AgentMemoryItem[]
  /** 列表还在首屏加载：各层显示占位而不是「还没有记忆」 */
  loading: boolean
  onForget: (id: string) => void
  /** 删除在途（所有层共用同一个 mutation） */
  forgetting: boolean
}) {
  return (
    <>
      {ACTIVE_SCOPES.map((scope) => {
        const items = active.filter((memory) => memory.scope === scope)
        // 团队/律所层为空且无可策展权限时不占位
        if (items.length === 0 && scope !== 'lawyer') return null
        return (
          <MemoryGroup
            key={scope}
            scope={scope}
            items={items}
            loading={loading}
            onForget={onForget}
            forgetting={forgetting}
          />
        )
      })}
    </>
  )
}
