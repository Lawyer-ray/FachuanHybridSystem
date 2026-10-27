import { useMemo } from 'react'
import { Link } from 'react-router'
import { FileText, FolderKanban } from 'lucide-react'

import { BADGE_TONE_CLS } from '@/components/shared/status-badge'
import { isLitigationType } from '@/lib/case-type'
import { cn } from '@/lib/utils'
import { groupProjects, projectRoute } from '../domain'
import type { Hit } from '../types'

/**
 * 项目类命中的分组渲染（GlobalSearch 结果区的 projects 段）。
 *
 * 与其余类别（当事人 / 收件箱 / …）的平铺渲染不同：合同（项目）作组头行、
 * 案件行挂在组头下缩进一级。合同没命中时组头只作分组上下文（不可点），
 * 案件本身仍可点跳所属项目页。
 */

/** 行底样式：命中光标高亮实底，其余悬停浅底；asButton 时补文字色（Link 继承父级） */
const rowCls = (active: boolean, asButton: boolean) =>
  cn(
    'flex w-full items-center gap-2.5 rounded-[7px] px-2 py-[7px] text-left transition-colors',
    active ? 'bg-secondary' : 'hover:bg-secondary/60',
    asButton && 'text-secondary-foreground',
  )

/**
 * 面板内小标签的共用形状：与 ProjectHits 的「非诉」、GlobalSearch 的「我方/对方」同款
 * （圆角 5px + 10px 字）。色由调用方给：实底=选中（ours）、描边=未选（非诉 / opposing）。
 */
export const PANEL_BADGE_CLS = 'flex-none rounded-[5px] px-[5px] py-px text-[10px] leading-[1.5] whitespace-nowrap'

/**
 * 非诉小标签：诉讼是常态不标，只让少数派跳出来。
 * 取 SideBadge 的**非选中态**（描边 + 灰字）——它逐字重复了那套样式，收敛到这里。
 */
function NonLitBadge() {
  return <span className={cn(PANEL_BADGE_CLS, BADGE_TONE_CLS.neutral)}>非诉</span>
}

export function ProjectHits({
  hits,
  flat,
  cursor,
  onOpenChange,
  pick,
}: {
  /** projects 类的全部命中（未重排） */
  hits: Hit[]
  /** 键盘导航用的全量平铺序（含其他类别），行光标按它在其中的下标点亮 */
  flat: Hit[]
  cursor: number
  onOpenChange: (v: boolean) => void
  pick: (hit: Hit) => void
}) {
  const { groups, orphans } = useMemo(() => groupProjects(hits), [hits])

  return (
    <div className="mb-1.5 last:mb-0">
      <div className="px-2 py-1 text-[10.5px] font-semibold text-muted-foreground">项目</div>
      {groups.map((g) => {
        const head = g.contractHit
        const headTo = head ? projectRoute(head) : undefined
        const headIdx = head ? flat.indexOf(head) : -1
        return (
          <div key={g.contractId}>
            {head ? (
              headTo ? (
                <Link
                  to={headTo}
                  onClick={() => onOpenChange(false)}
                  className={cn(rowCls(headIdx === cursor, false), 'text-secondary-foreground no-underline')}
                >
                  <FolderKanban className="h-3.5 w-3.5 flex-none text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-[12.5px]">{g.title}</span>
                  {!isLitigationType(g.case_type) && <NonLitBadge />}
                </Link>
              ) : (
                <button type="button" onClick={() => pick(head)} className={rowCls(headIdx === cursor, true)}>
                  <FolderKanban className="h-3.5 w-3.5 flex-none text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-[12.5px]">{g.title}</span>
                  {!isLitigationType(g.case_type) && <NonLitBadge />}
                </button>
              )
            ) : (
              /* 组头来自案件携带的合同信息（合同本身没命中）：只作分组上下文 */
              <div className="flex items-center gap-2.5 px-2 py-[5px] text-muted-foreground">
                <FolderKanban className="h-3.5 w-3.5 flex-none opacity-70" />
                <span className="min-w-0 flex-1 truncate text-[11.5px]">{g.title}</span>
                {!isLitigationType(g.case_type) && <NonLitBadge />}
              </div>
            )}
            {g.caseHits.map((h) => {
              const to = projectRoute(h)
              const idx = flat.indexOf(h)
              const row = (
                <>
                  <FileText className="h-3 w-3 flex-none text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-[12px]">{h.title}</span>
                  {h.subtitle && (
                    <span className="max-w-[140px] flex-none truncate text-[10.5px] text-muted-foreground tabular-nums">
                      {h.subtitle}
                    </span>
                  )}
                </>
              )
              return to ? (
                <Link
                  key={`case-${h.id}`}
                  to={to}
                  onClick={() => onOpenChange(false)}
                  className={cn(rowCls(idx === cursor, false), 'pl-7 text-secondary-foreground no-underline')}
                >
                  {row}
                </Link>
              ) : (
                <button
                  key={`case-${h.id}`}
                  type="button"
                  onClick={() => pick(h)}
                  className={cn(rowCls(idx === cursor, true), 'pl-7')}
                >
                  {row}
                  <span className="flex-none text-[10px] text-muted-foreground">未建页</span>
                </button>
              )
            })}
          </div>
        )
      })}
      {/* 无合同的案件（历史数据）：没有项目页可去，按未建页处理 */}
      {orphans.map((h) => {
        const idx = flat.indexOf(h)
        return (
          <button key={`orphan-${h.id}`} type="button" onClick={() => pick(h)} className={rowCls(idx === cursor, true)}>
            <FileText className="h-3.5 w-3.5 flex-none text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate text-[12.5px]">{h.title}</span>
            {h.subtitle && (
              <span className="max-w-[140px] flex-none truncate text-[10.5px] text-muted-foreground">{h.subtitle}</span>
            )}
            <span className="flex-none text-[10px] text-muted-foreground">未建页</span>
          </button>
        )
      })}
    </div>
  )
}
