import { useEffect, useMemo } from 'react'
import { toast } from 'sonner'

import {
  buildDeadlines,
  buildStagePlan,
  contactGroups,
  moneyRows,
  nextStage,
  planCases,
} from './detail-domain'
import { useDealDetail } from './use-deal-detail'

/**
 * 争议解决 / 非诉两个详情页共用的数据组装层。
 *
 * 两页的右栏输入（期限 / 当事人 / 收费 / 收款）完全同构——都是合同层面的
 * 事实；此前各自维护一份 useMemo 编排，字段一变要改两处。诉讼特有的
 * 程序链（chainSteps / ambiguousStages）留在诉讼页内取。
 */
export function useDealDetailPage(rawId: string | undefined) {
  const contractId = Number(rawId)
  const valid = Number.isInteger(contractId) && contractId > 0
  const d = useDealDetail(valid ? contractId : null)
  const deal = d.deal

  const plan = useMemo(() => buildStagePlan(deal?.stages ?? [], d.cases), [deal?.stages, d.cases])
  const ordered = useMemo(() => planCases(plan), [plan])
  const deadlines = useMemo(
    () => buildDeadlines(d.contractReminders ?? [], ordered, d.caseReminders ?? [], d.today),
    [d.contractReminders, ordered, d.caseReminders, d.today],
  )
  const contacts = useMemo(() => contactGroups(ordered), [ordered])
  const money = useMemo(() => (deal ? moneyRows(deal, ordered) : []), [deal, ordered])

  return { contractId, valid, d, deal, plan, ordered, deadlines, contacts, money, next: nextStage(plan) }
}

/** 创建类动作占位（样式定稿后接表单）：记日志 / 新增期限 / 新建下一程序案件 / 记收款 */
export const soonToast = (what: string) => toast.info(what + '正在开发中')

/**
 * 详情页共用的助手上下文绑定：进页把全局助手绑到该委托（欢迎页变本委托
 * 专属文案、快捷任务带归属、新会话自动注入 contract_id 锚点），离页退出。
 * 非诉页此前只有 setPageHint 没绑上下文——助手在非诉详情页里当通用对话。
 */
export function useDealCopilotContext(
  deal: { id: number; client: string } | null | undefined,
  pageHintLabel: string,
) {
  useEffect(() => {
    if (!deal) return
    let cancelled = false
    void import('@/features/copilot/store').then((m) => {
      if (cancelled) return
      const st = m.useCopilot.getState()
      st.setPageHint(`${pageHintLabel} · ${deal.client}（contract_id=${deal.id}）`)
      void st.enterContext({ origin: 'contract', refId: deal.id, title: deal.client })
    })
    return () => {
      cancelled = true
      void import('@/features/copilot/store').then((m) => {
        const st = m.useCopilot.getState()
        // 只退出自己绑的那个委托（快速切换委托时新旧 effect 交错）
        if (st.context?.origin === 'contract' && st.context.refId === deal.id) void st.exitContext()
      })
    }
  }, [deal, pageHintLabel])
}
