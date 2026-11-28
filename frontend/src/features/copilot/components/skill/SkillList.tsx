/**
 * 一个 tab 的技能列表（我的 / 所内 / 团队 / 系统共用本组件）。
 *
 * 空态不能是死路：有新建权限的 tab 都给「新建」入口（系统 tab 除外——内置技能随代码
 * 发布，想改只能先「复制为我的」）。没有入口的 tab 要写清「这一层怎么才会有条目」，
 * 否则律师看到的是一句「暂无数据」然后退出抽屉。
 *
 * 配额满了只禁用新建、不隐藏：律师得看见按钮和原因（原因由 `SkillQuotaBar` 显示，
 * 按钮的 `title` 复用同一句），才知道是「额度用完了」而不是「功能坏了」。
 *
 * 取数、加载态与错误态留在 `SkillDrawer`（那是同一份查询的三种形态），本组件只负责
 * 「有数据时长什么样」。
 */

import { Plus, Sparkles } from 'lucide-react'

import type { AgentSkill } from '../../types'
import { EmptyBlock } from '@/components/shared/AsyncState'
import { Button } from '@/components/ui/button'
import { SkillRow } from './SkillRow'
import { skillTabLabel, type SkillCreateScope, type SkillTabId, type SkillTabQuotaCell } from './skill-tabs'

/** 空态文案：说清「这一层是什么、怎么才会有条目」，不说「暂无数据」 */
const EMPTY_TEXT: Record<SkillTabId, string> = {
  mine: '还没有自己的技能——把你反复用的做法写成一段，之后用 /skill:名字 点名让 AI 照它做',
  firm: '所内还没有你能看到的技能。所内技能要提交审批、由管理员通过后才会生效',
  team: '团队还没有你能看到的技能。团队技能由团队成员提交、审批通过后生效',
  system: '系统技能清单为空（后端未挂载技能库）',
}

/** 新建按钮的文案按「建到哪一层」写：在「所内」里点「新建技能」会让人以为是个人技能 */
const CREATE_LABEL: Record<SkillCreateScope, string> = {
  lawyer: '新建技能',
  law_firm: '新建所内技能',
}

export function SkillList({
  tab,
  skills,
  busyKey,
  tabQuota,
  createScope,
  onCreate,
  onEdit,
  onDelete,
  onDuplicate,
  onToggle,
}: {
  tab: SkillTabId
  /** 已按 tab 过滤好的清单 */
  skills: AgentSkill[]
  /** 正在写的那一行（启停/删除/复制在途）：只有它置忙，别的行照常可点 */
  busyKey: string | null
  tabQuota: SkillTabQuotaCell | null
  /** `null` = 这一层不给新建入口（无权限 / 团队要选团队 / 系统技能随平台发布） */
  createScope: SkillCreateScope | null
  onCreate: () => void
  onEdit: (skill: AgentSkill) => void
  onDelete: (skill: AgentSkill) => void
  onDuplicate: (skill: AgentSkill) => void
  onToggle: (skill: AgentSkill, enabled: boolean) => void
}) {
  const blocked = tabQuota?.full === true
  const createButton =
    createScope === null ? null : (
      <Button
        size="sm"
        variant="outline"
        className="h-7 gap-1 px-2.5 text-[11px]"
        disabled={blocked}
        title={blocked ? tabQuota?.fullReason : undefined}
        onClick={onCreate}
      >
        <Plus className="h-3 w-3" />
        {CREATE_LABEL[createScope]}
      </Button>
    )

  if (skills.length === 0) {
    return (
      <EmptyBlock icon={<Sparkles className="size-6" />} action={createButton}>
        {EMPTY_TEXT[tab]}
      </EmptyBlock>
    )
  }

  return (
    <>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[11px] text-muted-foreground">
          {tab === 'system'
            ? '内置技能随平台发布，不可修改；可复制为我的再改'
            : `${skills.length} 条${skillTabLabel(tab)}技能`}
        </span>
        <span className="ml-auto">{createButton}</span>
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
