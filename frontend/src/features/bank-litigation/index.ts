/**
 * 银行批量诉讼（场景 2）feature 的对外出口。
 *
 * 只导出页面与必要类型；内部 hooks / api 不对外 —— 别的 feature 要用这些
 * 能力时应自己走 api 层，而不是顺手 import 这里的 hook（hook 绑定了本页的
 * 状态假设，跨 feature 复用会悄悄继承这些假设）。
 */
export { BankLitigationPage } from './components/BankLitigationPage'
export type { CaseRow, FilingType, FilingEngine, SlotStatus } from './types'
