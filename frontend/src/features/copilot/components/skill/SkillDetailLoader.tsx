/**
 * 编辑态的取数三态：打开编辑器先拉一份详情再渲染表单。
 *
 * 为什么要单独拉：列表项（`GET agent/skills`）没有 `body`，而 `version` 要拿**最新**
 * 的做乐观锁——用列表里那份陈旧版本去 PUT，别人刚改过就会白写一次冲突。
 *
 * 只负责「怎么拿到详情」，拿到之后交给 `children` 渲染：草稿状态、校验与保存都是
 * 外壳 `SkillEditor` 的职责（它同时服务新建态，两态共用一套保存/放弃逻辑）。
 */

import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'

import { fetchAgentSkill } from '../../skill-api'
import type { AgentSkill, AgentSkillDetail } from '../../types'
import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { SKILLS_QUERY_KEY } from './use-skill-mutations'

export function SkillDetailLoader({
  skill,
  children,
}: {
  /** 列表里那一行（只用它的 `key` 取详情） */
  skill: AgentSkill
  /** 详情到手后渲染编辑器正文 */
  children: (detail: AgentSkillDetail) => ReactNode
}) {
  const detailQuery = useQuery({
    queryKey: [...SKILLS_QUERY_KEY, skill.key],
    queryFn: () => fetchAgentSkill(skill.key),
    staleTime: 0,
  })

  if (detailQuery.isLoading) return <LoadingBlock size="sm" text="正在打开技能…" />
  if (!detailQuery.data) {
    return <ErrorBlock error={detailQuery.error} fallback="技能正文加载失败" onRetry={() => void detailQuery.refetch()} />
  }
  return <>{children(detailQuery.data)}</>
}
