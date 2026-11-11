import { describe, expect, it } from 'vitest'

import {
  MATERIAL_STAGES,
  SMS_STAGES,
  failedStageFor,
  smsStageInfo,
  stageIndexFor,
  stageIndexFromRaw,
  stagesFor,
} from './stages'

describe('smsStageInfo 状态机映射', () => {
  it('流水线各进行中状态映射到递增阶段', () => {
    expect(smsStageInfo('pending').stage).toBe(0)
    expect(smsStageInfo('parsing').stage).toBe(0)
    expect(smsStageInfo('downloading').stage).toBe(1)
    expect(smsStageInfo('matching').stage).toBe(2)
    expect(smsStageInfo('renaming').stage).toBe(3)
    expect(smsStageInfo('notifying').stage).toBe(4)
  })

  it('进行中状态都不是终态', () => {
    for (const s of ['pending', 'parsing', 'downloading', 'matching', 'renaming', 'notifying']) {
      expect(smsStageInfo(s).terminal).toBeNull()
    }
  })

  it('completed 是成功终态且阶段走满', () => {
    const info = smsStageInfo('completed')
    expect(info.terminal).toBe('completed')
    expect(info.stage).toBe(SMS_STAGES.length)
  })

  it('pending_manual 是人工终态，停在匹配阶段', () => {
    const info = smsStageInfo('pending_manual')
    expect(info.terminal).toBe('manual')
    expect(info.stage).toBe(2)
    expect(info.failedAt).toBeNull()
  })

  it('download_failed 是等待自动重试的非终态，标注失败在下载阶段', () => {
    // 后端 retry_count<3 会建 +60s 调度自动重试，若当终态停轮询会错过恢复
    const info = smsStageInfo('download_failed')
    expect(info.terminal).toBeNull()
    expect(info.failedAt).toBe(1)
  })

  it('failed 是失败终态但不指定失败阶段（由观测兜底）', () => {
    const info = smsStageInfo('failed')
    expect(info.terminal).toBe('failed')
    expect(info.failedAt).toBeNull()
  })

  it('未知状态按处理中兜底，不误判终态', () => {
    const info = smsStageInfo('some_new_status')
    expect(info.terminal).toBeNull()
    expect(info.stage).toBe(0)
  })
})

describe('客户转交通道的阶段表（无下载环节）', () => {
  it('两套阶段表长度与文案不同', () => {
    expect(stagesFor('sms')).toBe(SMS_STAGES)
    expect(stagesFor('material')).toBe(MATERIAL_STAGES)
    expect(MATERIAL_STAGES).toHaveLength(4)
    expect(MATERIAL_STAGES).not.toContain('下载文书')
  })

  it('material 下 downloading 不会漏到「匹配案件」之后', () => {
    // 后端理论不会给 material 通道发 downloading，但历史记录/重试可能残留，
    // 映射必须保证不越界（四步表的合法下标 0..3）
    expect(stageIndexFor('downloading', 'material')).toBeLessThanOrEqual(3)
    expect(stageIndexFor('downloading', 'sms')).toBe(1)
  })

  it('material 下 matching/renaming/notifying 各左移一位', () => {
    expect(stageIndexFor('matching', 'material')).toBe(1)
    expect(stageIndexFor('renaming', 'material')).toBe(2)
    expect(stageIndexFor('notifying', 'material')).toBe(3)
  })

  it('material 下解析阶段仍是第 0 步', () => {
    expect(stageIndexFor('pending', 'material')).toBe(0)
    expect(stageIndexFor('parsing', 'material')).toBe(0)
  })

  it('sms 来源的映射保持原样（不回归）', () => {
    for (const s of ['pending', 'downloading', 'matching', 'renaming', 'notifying']) {
      expect(stageIndexFor(s, 'sms')).toBe(smsStageInfo(s).stage)
    }
  })

  it('stageIndexFromRaw 把后端原始下标换算成 material 下标', () => {
    expect(stageIndexFromRaw(0, 'material')).toBe(0)
    expect(stageIndexFromRaw(1, 'material')).toBe(0)
    expect(stageIndexFromRaw(2, 'material')).toBe(1)
    expect(stageIndexFromRaw(4, 'material')).toBe(3)
    // sms 恒等
    expect(stageIndexFromRaw(3, 'sms')).toBe(3)
  })

  it('failedStageFor 在 material 下把失败位置同步左移', () => {
    // download_failed 的 failedAt=1；material 没有下载阶段 → 落在第 0 步
    expect(failedStageFor('download_failed', 'sms')).toBe(1)
    expect(failedStageFor('download_failed', 'material')).toBe(0)
    // 无明确失败阶段的状态返回 null
    expect(failedStageFor('failed', 'material')).toBeNull()
  })
})
