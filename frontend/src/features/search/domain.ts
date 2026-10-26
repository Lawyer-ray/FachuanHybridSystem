import { isLitigationType } from '@/lib/case-type'

import type { Hit } from './types'

/**
 * 项目类命中的纯领域逻辑：分组与路由。
 *
 * projects 语义：项目 = 委托合同，案件挂在合同下。合同命中是项目行；
 * 案件命中按其所属合同归组，合同没命中也补一个组头（名称来自案件携带的
 * contract_name），案件才有处可挂、用户才知道它属于哪个项目。
 */

/** 一个项目分组：组头（合同）+ 挂在其下的案件命中 */
export interface ProjectGroup {
  contractId: number
  title: string
  case_type: string
  /** 合同本身的命中行（合同没命中时为 null，组头只作上下文不可点） */
  contractHit: Hit | null
  caseHits: Hit[]
}

/** 把 projects 类命中按合同归组；无合同的案件（历史数据 contract 为空）进 orphans */
export function groupProjects(hits: Hit[]): { groups: ProjectGroup[]; orphans: Hit[] } {
  const groups = new Map<number, ProjectGroup>()
  const orphans: Hit[] = []

  // 先按合同命中建组（保持后端顺序），案件命中再挂进去 / 补建组
  for (const h of hits) {
    if (h.kind !== 'contract') continue
    groups.set(h.id, { contractId: h.id, title: h.title, case_type: h.case_type ?? '', contractHit: h, caseHits: [] })
  }
  for (const h of hits) {
    if (h.kind !== 'case') continue
    if (h.contract_id == null) {
      orphans.push(h)
      continue
    }
    const g =
      groups.get(h.contract_id) ??
      {
        contractId: h.contract_id,
        title: h.contract_name || '（未命名合同）',
        case_type: h.case_type ?? '',
        contractHit: null,
        caseHits: [],
      }
    g.caseHits.push(h)
    groups.set(h.contract_id, g)
  }
  return { groups: [...groups.values()], orphans }
}

/** projects 段重排为「组头行 → 案件行」的视觉顺序（键盘 ↑↓ 与渲染共用同一序），其余类别原序垫后 */
export function orderProjectHits(hits: Hit[]): Hit[] {
  const projects = hits.filter((h) => h.category === 'projects')
  const rest = hits.filter((h) => h.category !== 'projects')
  const { groups, orphans } = groupProjects(projects)
  const ordered: Hit[] = []
  for (const g of groups) {
    if (g.contractHit) ordered.push(g.contractHit)
    ordered.push(...g.caseHits)
  }
  return [...ordered, ...orphans, ...rest]
}

/** 项目行 / 案件行的跳转目标；无合同的案件无处可去返回 undefined（按未建页处理） */
export function projectRoute(hit: Hit): string | undefined {
  if (hit.kind === 'contract') {
    return isLitigationType(hit.case_type) ? `/projects/${hit.id}` : `/projects/${hit.id}/nonlit`
  }
  if (hit.contract_id == null) return undefined
  if (!isLitigationType(hit.case_type)) return `/projects/${hit.contract_id}/nonlit`
  // 诉讼详情页案件节有 case-<id> 锚点（CaseSection），hash 让浏览器原生滚到该案
  return `/projects/${hit.contract_id}#case-${hit.id}`
}
