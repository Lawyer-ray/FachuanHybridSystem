import { useState } from 'react'
import { Link } from 'react-router'

import { projectEdit } from '@/app/paths'

import type { WorkbenchDeal } from '../../types'
import { crumbName, headerMetaParts } from './detail-domain'
import { ProjectMemoryDrawer } from './ProjectMemoryDrawer'
import { ActionButton, MetaLine } from './ui'

/**
 * 安静页头：面包屑（项目 / 短名）+ 合同名主标题 + meta 单行 + 动作区。
 * **对话**入口只在导航栏（全局侧边栏），页头不再放重复入口；动作区里的
 * 「AI 上下文」不是对话入口，而是本项目 AI 笔记的只读抽屉（见 ProjectMemoryDrawer）。
 * 主标题即合同名（建档时的全称），领域身份不另造名称；标题不限宽——限宽会留下
 * 一大片「标题够不着、按钮够不着」的空白（长案名 3 行折行时尤其明显）。
 */
export function DetailHeader({
  deal,
  onAddDue,
  onAddLog,
}: {
  deal: WorkbenchDeal
  onAddDue: () => void
  onAddLog: () => void
}) {
  /** 抽屉开关留在页头（谁渲染触发器谁持状态）：抽屉自身不碰导航，纯只读面板 */
  const [memoryOpen, setMemoryOpen] = useState(false)

  return (
    <>
      <nav className="mb-3.5 flex gap-[7px] text-[12.5px] text-muted-foreground">
        <Link to="/projects" className="transition-colors hover:text-foreground">
          项目
        </Link>
        <span>/</span>
        <span className="font-[550] text-foreground" title={deal.client}>
          {crumbName(deal.client)}
        </span>
      </nav>

      {/* 窄屏：标题与动作各占一整行。此前它是「标题 flex-1 + 动作 ml-auto」，
          手机上 flex 会先把标题压成一条窄柱去容纳四个按钮，标题于是折成七八行 */}
      <div className="mb-4 flex flex-wrap items-start gap-[18px]">
        <div className="min-w-0 flex-1 max-[680px]:basis-full">
          <h1 className="text-[23px] leading-[1.4] font-[760] tracking-[-0.022em] break-all max-[680px]:text-[19px]">
            {deal.client}
          </h1>
          <MetaLine
            parts={headerMetaParts(deal)}
            className="mt-1.5 text-[13px] leading-[1.8] text-muted-foreground tabular-nums"
          />
        </div>
        <div className="ml-auto flex flex-wrap gap-2 pt-1.5 max-[680px]:ml-0 max-[680px]:w-full max-[680px]:basis-full max-[680px]:pt-0">
          {/* 放在最左：它是一次**导航**，不是本页的创建动作——所以渲染成真锚点
              （可中键开新标签）。页头主按钮位留给真能完成的事，不再给占位动作 */}
          <ActionButton title="改项目名称 / 案型 / 状态 / 服务期 / 收费 / 代理阶段" to={projectEdit(deal.id)}>
            编辑
          </ActionButton>
          <ActionButton title="本项目所有 AI 笔记（同团队可见）" onClick={() => setMemoryOpen(true)}>
            AI 上下文
          </ActionButton>
          {/* 这两个动作后端还没上线：保留入口与点击后的解释，但不再用深色主按钮
              冒充「这里能做」——页头的主操作位应该留给真能完成的事 */}
          <ActionButton onClick={onAddDue} title="即将支持：新增期限的接口还没上线">
            ＋ 新增期限
          </ActionButton>
          <ActionButton onClick={onAddLog} title="即将支持：记项目日志的接口还没上线">
            ＋ 记项目日志
          </ActionButton>
        </div>
      </div>

      <ProjectMemoryDrawer open={memoryOpen} onOpenChange={setMemoryOpen} contractId={deal.id} />
    </>
  )
}
