/**
 * 状态 → 颜色的单一来源：语义色档位（Tone）与徽章样式表。
 *
 * 为什么放 lib/ 而不是 components/shared/StatusBadge.tsx：Tone 是「状态 → 语义色」
 * 的跨层词汇——UI 层（StatusBadge、全局检索的行内标签）与领域层（如 copilot 的
 * 审批卡 tone 映射）都要用。留在组件文件里会逼领域层反向 import components
 * （E6 层级倒挂），所以类型与常量下沉到这里，渲染组件仍留在 components/shared。
 *
 * 颜色一律取 index.css 里已定义的 `--status-*`（含暗色的 bg 变体），
 * 不硬编码 hex——暗色主题才能随之切换。
 */

/** 语义色档位：绿=成功 / 黄=待处理·警告 / 红=失败·高危 / 蓝=进行中·提示 / 紫=特殊 / 灰=中性·已取消 */
export type Tone = 'green' | 'yellow' | 'red' | 'blue' | 'purple' | 'neutral'

/**
 * tone → border / bg / text 三件套。
 * 描边透明度按各色对比度微调（黄最亮需 50，其余 40），沿用历史列表的既有口径。
 */
export const BADGE_TONE_CLS: Record<Tone, string> = {
  green: 'border-status-green/40 bg-status-green-bg text-status-green',
  yellow: 'border-status-yellow/50 bg-status-yellow-bg text-status-yellow',
  red: 'border-status-red/40 bg-status-red-bg text-status-red',
  blue: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
  purple: 'border-status-purple/40 bg-status-purple-bg text-status-purple',
  neutral: 'border-border bg-secondary text-muted-foreground',
}
