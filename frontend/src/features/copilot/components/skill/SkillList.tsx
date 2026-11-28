/**
 * 一个 tab 的技能列表（「我的」/「系统」共用本组件）。
 *
 * 空态不能是死路：两个 tab 都给「新建技能」——系统技能为空（后端未挂载技能库）
 * 时律师照样可以自己写一个，而不是看到「暂无数据」被迫退出抽屉。
 *
 * 取数、加载态与错误态留在 `SkillDrawer`（那是同一份查询的三种形态），
 * 本组件只负责「有数据时长什么样」。
 */

import { Plus, Sparkles } from 'lucide-react'

import type { AgentSkill } from '../../types'
import { EmptyBlock } from '@/components/shared/AsyncState'
import { Button } from '@/components/ui/button'
import { SkillRow } from './SkillRow'

/** 抽屉的两个 tab：我的（`source=user`）/ 系统（`source=builtin`） */
export type SkillTab = 'mine' | 'system'

export function SkillList({
  tab,
  skills,
  busyKey,
  onCreate,
  onEdit,
  onDelete,
  onDuplicate,
  onToggle,
}: {
  tab: SkillTab
  /** 已按 tab 过滤好的清单 */
  skills: AgentSkill[]
  /** 正在写的那一行（启停/删除/复制在途）：只有它置忙，别的行照常可点 */
  busyKey: string | null
  onCreate: () => void
  onEdit: (skill: AgentSkill) => void
  onDelete: (skill: AgentSkill) => void
  onDuplicate: (skill: AgentSkill) => void
  onToggle: (skill: AgentSkill, enabled: boolean) => void
}) {
  if (skills.length === 0) {
    return (
      <EmptyBlock
        icon={<Sparkles className="size-6" />}
        action={
          <Button size="sm" variant="outline" className="h-7 gap-1 px-2.5 text-[11px]" onClick={onCreate}>
            <Plus className="h-3 w-3" />
            新建技能
          </Button>
        }
      >
        {tab === 'mine'
          ? '还没有自己的技能——把你反复用的做法写成一段，之后用 /skill:名字 点名让 AI 照它做'
          : '系统技能清单为空（后端未挂载技能库），也可以自己新建一个'}
      </EmptyBlock>
    )
  }

  return (
    <>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[11px] text-muted-foreground">
          {tab === 'mine' ? `${skills.length} 个技能` : '内置技能随平台发布，不可修改；可复制为我的再改'}
        </span>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto h-7 gap-1 px-2.5 text-[11px]"
          onClick={onCreate}
        >
          <Plus className="h-3 w-3" />
          新建技能
        </Button>
      </div>
      <div className="space-y-1.5">
        {skills.map((skill) => (
          <SkillRow
            key={skill.key}
            skill={skill}
            busy={busyKey === skill.key}
            onEdit={onEdit}
            onDelete={onDelete}
            onDuplicate={onDuplicate}
            onToggle={onToggle}
          />
        ))}
      </div>
    </>
  )
}
