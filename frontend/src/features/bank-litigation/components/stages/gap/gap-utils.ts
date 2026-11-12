/**
 * ③ 缺件面板的纯工具：来源查表 + 清单派生数据。
 *
 * 面板里所有「按来源分组 / 统计某类缺几条 / 勾选里哪些还没补齐」的口径都收在这里，
 * 组件只负责渲染，保证列表、分组计数、批量操作三处用的是同一套算法。
 */
import { DEMO_GAP_NOTICES, DEMO_X2_GAP_SOURCES, type GapSource } from '../../demo-data'

/** 分组切换项：全部 + 四个来源 */
export const SOURCE_TABS: Array<'全部' | GapSource> = ['全部', '合同类', '催收类', '身份类', '担保类']

/** 缺件项 → 来源分组（查不到时按合同类处理） */
export function sourceOf(item: string): GapSource {
  return DEMO_X2_GAP_SOURCES.find((s) => s.item === item)?.source ?? '合同类'
}

/** 某个来源分组下的缺件条数（「全部」即全量） */
export function countBySource(tab: '全部' | GapSource): number {
  return tab === '全部' ? DEMO_GAP_NOTICES.length : DEMO_GAP_NOTICES.filter((g) => sourceOf(g.item) === tab).length
}

/** 按来源分组过滤后的可见缺件 */
export function visibleNotices(tab: '全部' | GapSource) {
  return tab === '全部' ? DEMO_GAP_NOTICES : DEMO_GAP_NOTICES.filter((g) => sourceOf(g.item) === tab)
}

/** 勾选里还没补齐的那些 —— 批量催办只该发给它们 */
export function openCheckedItems(checked: Set<string>): string[] {
  return [...checked].filter((k) => DEMO_GAP_NOTICES.some((g) => g.item === k && g.status !== 'received'))
}

/** 当前分组是否已全选 */
export function isAllChecked(visible: typeof DEMO_GAP_NOTICES, checked: Set<string>): boolean {
  return visible.length > 0 && visible.every((g) => checked.has(g.item))
}
