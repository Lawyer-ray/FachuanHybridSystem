/**
 * 非诉线 · 工作台分流与出口。
 *
 * ═══ 为什么要加 ═══
 * 非诉页原来只有静态的阶段表 / 服务事项流，律师点进去**没有任何可操作的东西**；
 * 录屏时最能说明问题的「点一下、看机器跑」完全缺失，观感上与诉讼线是两个产品。
 *
 * 三个非诉场景各配一组可执行动作：
 *   · 专项服务  → 设计阶段 / 从 0 起草 / 校验交付物   （./SpecialPhaseWorkbench）
 *   · 跨境审查  → 逐条审查 / 泰文法条核验（三道规则闸 + 判断层）（./CrossBorderWorkbench）
 *   · 常年顾问  → 配额可视化 / 可展开事项流 / 风险清单 / 续签检测  （./AdvisorWorkbench）
 *
 * ═══ 为什么本文件只剩分流 ═══
 * 2026-11 拆分缘起：单文件到 532 行越过 450 行硬红线，而三个工作台各自是**完整
 * 的一屏**（各自的动作脚本、汇总口径、子卡编排），混在一个文件里改一处要跨屏
 * 读 500 行。判据是「一屏一文件」，不是机械切行；三屏共用的汇总小件（SectionHead
 * / StatStrip / StatCell）提到 nonlit/special/special-stat.tsx，避免复制成三份口径。
 *
 * 本文件保留 re-export 与 `NonLitWorkbench` 分流——NonLitDetailPage 与各 dom 测试
 * mock 的都是 `./nonlit-workbench`，换成别的模块路径会让 mock 边界静默失效。
 */

import { AdvisorWorkbench } from './AdvisorWorkbench'
import { CrossBorderWorkbench } from './CrossBorderWorkbench'

export { AdvisorWorkbench } from './AdvisorWorkbench'
export { CrossBorderWorkbench } from './CrossBorderWorkbench'
export { SpecialPhaseWorkbench } from './SpecialPhaseWorkbench'

/** 按 case_type 选对应工作台（后端只有 advisor / 其余两个代码值） */
export function NonLitWorkbench({ caseType }: { caseType: string }) {
  if (caseType === 'advisor') return <AdvisorWorkbench />
  return <CrossBorderWorkbench />
}
