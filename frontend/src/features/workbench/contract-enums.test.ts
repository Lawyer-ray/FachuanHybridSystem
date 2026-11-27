import { describe, expect, it } from 'vitest'

import { STAGE_ORDER } from './components/deal-detail/detail/chain-domain'
import {
  FEE_MODE_OPTIONS,
  STAGE_OPTIONS,
  feeModeCodeToLabel,
  feeModeLabelToCode,
  stageCodesToLabels,
  stageLabelsToCodes,
  stageOptionsFor,
} from './contract-enums'

/**
 * 枚举镜像的防漂移测试。
 *
 * 这份表是**手抄**后端枚举的（后端不暴露枚举端点），所以必须有东西钉住它：
 * - 阶段标签集合必须与详情页程序链的 STAGE_ORDER 逐项一致，否则同一条「一审」
 *   在两个地方会显示/排序不同；
 * - 非诉三类案子的可用阶段必须为空——后端对它们传任何非空数组都返回 400。
 */
describe('contract-enums', () => {
  it('阶段中文标签集合与程序链 STAGE_ORDER 完全一致（防手抄漂移）', () => {
    expect(STAGE_OPTIONS.map((s) => s.label).sort()).toEqual([...STAGE_ORDER].sort())
  })

  it('收费方式的标签与后端 get_fee_mode_display 口径一致', () => {
    expect(FEE_MODE_OPTIONS.map((o) => [o.value, o.label])).toEqual([
      ['FIXED', '固定收费'],
      ['SEMI_RISK', '半风险收费'],
      ['FULL_RISK', '全风险收费'],
      ['CUSTOM', '自定义收费'],
    ])
  })

  it('涉外 / 专项 / 常法没有任何可用阶段（后端这两类传非空数组必 400）', () => {
    for (const caseType of ['intl', 'special', 'advisor']) {
      expect(stageOptionsFor(caseType)).toEqual([])
    }
  })

  it('劳动只有劳动仲裁；民商事/行政有执行、刑事没有', () => {
    expect(stageOptionsFor('labor').map((s) => s.code)).toEqual(['labor_arbitration'])
    expect(stageOptionsFor('civil').map((s) => s.code)).toContain('enforcement')
    expect(stageOptionsFor('criminal').map((s) => s.code)).not.toContain('enforcement')
  })

  it('读写互转：标签 ↔ 代码（后端 GET 给标签、PUT 要代码）', () => {
    expect(feeModeLabelToCode('半风险收费')).toBe('SEMI_RISK')
    expect(feeModeCodeToLabel('SEMI_RISK')).toBe('半风险收费')
    expect(stageLabelsToCodes(['一审', '执行'])).toEqual(['first_trial', 'enforcement'])
    expect(stageCodesToLabels(['first_trial', 'enforcement'])).toEqual(['一审', '执行'])
  })

  it('认不出的历史脏值原样返回（不静默吞掉，交给校验拦住）', () => {
    expect(feeModeLabelToCode('risk')).toBe('risk')
    expect(stageLabelsToCodes(['神秘阶段'])).toEqual(['神秘阶段'])
  })
})
