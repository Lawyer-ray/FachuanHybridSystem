import { describe, expect, it } from 'vitest'

import { SMS_STAGES, smsStageInfo } from './stages'

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
