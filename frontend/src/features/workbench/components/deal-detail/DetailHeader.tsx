import { Link } from 'react-router'
import { Sparkles } from 'lucide-react'

import type { WorkbenchDeal } from '../../types'
import { crumbName, headerMetaParts } from './detail-domain'
import { ActionButton, MetaLine } from './ui'

/**
 * 安静页头：面包屑（办案 / 短名）+ 合同名主标题 + meta 单行 + 两个创建动作。
 * 主标题即合同名（建档时的全称），领域身份不另造名称；标题不限宽——限宽会留下
 * 一大片「标题够不着、按钮够不着」的空白（长案名 3 行折行时尤其明显）。
 */
export function DetailHeader({
  deal,
  onAddDue,
  onAddLog,
  onOpenAi,
}: {
  deal: WorkbenchDeal
  onAddDue: () => void
  onAddLog: () => void
  /** 打开全局 AI 助手侧边栏（同一面板，自动带本委托上下文） */
  onOpenAi: () => void
}) {
  return (
    <>
      <nav className="mb-3.5 flex gap-[7px] text-[12.5px] text-muted-foreground">
        <Link to="/projects" className="transition-colors hover:text-foreground">
          办案
        </Link>
        <span>/</span>
        <span className="font-[550] text-foreground" title={deal.client}>
          {crumbName(deal.client)}
        </span>
      </nav>

      <div className="mb-4 flex flex-wrap items-start gap-[18px]">
        <div className="min-w-0 flex-1">
          <h1 className="text-[23px] leading-[1.4] font-[760] tracking-[-0.022em] break-all max-[680px]:text-[19px]">
            {deal.client}
          </h1>
          <MetaLine
            parts={headerMetaParts(deal)}
            className="mt-1.5 text-[13px] leading-[1.8] text-muted-foreground tabular-nums"
          />
        </div>
        <div className="ml-auto flex flex-wrap gap-2 pt-1.5 max-[680px]:ml-0 max-[680px]:pt-0">
          <ActionButton onClick={onOpenAi} title="打开 AI 助手（右侧面板，自动带本委托上下文，新会话自动带归属）">
            <Sparkles className="mr-0.5 inline h-3.5 w-3.5 align-[-2px]" />
            AI 助手
          </ActionButton>
          <ActionButton onClick={onAddDue}>＋ 新增期限</ActionButton>
          <ActionButton dark onClick={onAddLog}>
            ＋ 记办案日志
          </ActionButton>
        </div>
      </div>
    </>
  )
}
