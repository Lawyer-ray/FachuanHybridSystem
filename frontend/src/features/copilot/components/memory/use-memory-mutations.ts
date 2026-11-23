/**
 * 记忆抽屉的三个写入动作：新增 / 删除 / 确认（accept 布尔同时表达「确认」与「忽略」）。
 *
 * 从 `MemoryDrawer` 拆出（后者单函数超软红线）。三者共用同一个缓存失效口径
 * （`['copilot','memory']` 前缀一把清）——各写一遍迟早漏一条，表现是「删了还在」
 * 「确认了待确认区不消失」「新增后列表里看不到」。
 *
 * 读取面（列表 / 作用域两个查询）留在外壳里：它和待确认区、分组列表的排版读的是
 * 同一份 `isLoading`，拆到这里只会多一层转手。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'

import { confirmMemories, createMemory, forgetMemory } from '../../memory-api'
import type { MemoryKind } from '../../types'

/** 记忆相关的查询键前缀（列表 / 作用域 / 策展候选同属一块） */
const MEMORY_QUERY_KEY = ['copilot', 'memory']

export function useMemoryMutations({
  onCreated,
}: {
  /** 新增成功后的本地清理（清空草稿）：写入 hook 不该知道草稿 state 长什么样 */
  onCreated: () => void
}) {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: MEMORY_QUERY_KEY })
  }

  const createMutation = useMutation({
    mutationFn: (payload: { content: string; kind: MemoryKind }) => createMemory(payload.content, payload.kind),
    onSuccess: () => {
      onCreated()
      invalidate()
    },
  })

  const forgetMutation = useMutation({
    mutationFn: (id: string) => forgetMemory(id),
    onSuccess: invalidate,
  })

  const confirmMutation = useMutation({
    mutationFn: (payload: { ids: string[]; accept: boolean }) => confirmMemories(payload.ids, payload.accept),
    onSuccess: invalidate,
  })

  return {
    createMutation,
    forgetMutation,
    confirmMutation,
    /** 失效口径本体：策展提升成功等「写入不在本 hook 里」的场景也要用它，不能另写一份 */
    invalidate,
  }
}
