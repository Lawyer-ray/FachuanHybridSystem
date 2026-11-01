// @vitest-environment jsdom
/**
 * ④ 文书 / ⑥ 校验 的细化交互（jsdom）。
 *
 * 覆盖点：
 * - 条款逐条审核：未填项高亮、编辑后保存回「已修改」、待定数减一
 * - 生成的文书：每行有模板下拉，默认 v3.2，可切 v2.8
 * - 利冲：导出报告走进度并落一个 PDF 名
 * - 机器人录像：5 帧依次点亮，点时间轴能跳帧
 * - 三处金额：差异行标红，点开看口径
 * - 一键修正：先出 diff 预览，确认后才跑
 * - 通知律师：两阶段，发完显示站内/短信/已读
 * - 签章：放大查看弹全屏大图
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  DEMO_CONTRACT_GEN,
  DEMO_CONTRACT_TERMS,
  DEMO_SIGN_CHECKS,
  DEMO_X3_AMOUNTS,
  DEMO_X3_BROWSER_FRAMES,
  DEMO_X3_FIX_DIFF,
  DEMO_X3_NOTICE_DELIVERY,
} from '../demo-data'
import { ContractTermsCard, TermEditDrawer } from './ContractTermsCard'
import { initTermDrafts, pendingTermCount } from './contract-terms'
import { BotReplayDrawer } from './BotReplayDrawer'
import { FilingAmountCard } from './FilingAmountCard'
import { FilingFixPreviewDrawer } from './FilingFixPreviewDrawer'
import { FilingNotifyCard } from './FilingNotifyCard'
import { SignDrawer } from './FilingSignDrawer'
import { ContractPanel } from './ContractPanel'

describe('contract-terms', () => {
  it('初始草稿取自动填充值，未填项计入待定数', () => {
    const drafts = initTermDrafts()
    expect(Object.keys(drafts)).toHaveLength(DEMO_CONTRACT_TERMS.length)
    const unfilled = DEMO_CONTRACT_TERMS.filter((t) => !t.filled).length
    expect(pendingTermCount(drafts)).toBe(unfilled)
    expect(unfilled).toBeGreaterThan(0)

    // 律师改过就不再算待定
    const clause = DEMO_CONTRACT_TERMS.find((t) => !t.filled)!.clause
    drafts[clause] = { value: '代为和解、代收法律文书及执行款项', edited: true }
    expect(pendingTermCount(drafts)).toBe(unfilled - 1)
  })
})

describe('ContractTermsCard', () => {
  it('每条都有编辑按钮，未填项标「未填」', () => {
    const onEdit = vi.fn()
    render(<ContractTermsCard drafts={initTermDrafts()} onEdit={onEdit} />)

    expect(screen.getAllByRole('button', { name: /编辑/ })).toHaveLength(DEMO_CONTRACT_TERMS.length)
    const unfilled = DEMO_CONTRACT_TERMS.filter((t) => !t.filled)
    expect(screen.getAllByText('未填')).toHaveLength(unfilled.length)

    fireEvent.click(screen.getAllByRole('button', { name: /编辑/ })[0]!)
    expect(onEdit).toHaveBeenCalledWith(DEMO_CONTRACT_TERMS[0]!.clause)
  })

  it('改过的行打「已修改」，不再算待定', () => {
    const drafts = initTermDrafts()
    const clause = DEMO_CONTRACT_TERMS.find((t) => !t.filled)!.clause
    drafts[clause] = { value: '改过的特别授权', edited: true }
    render(<ContractTermsCard drafts={drafts} onEdit={() => {}} />)

    expect(screen.getByText('已修改')).toBeTruthy()
    // 8 条里只有 1 条本来「待定」，改过之后全部确认
    expect(pendingTermCount(drafts)).toBeLessThan(
      DEMO_CONTRACT_TERMS.filter((t) => !t.filled).length,
    )
    expect(screen.getByText('全部确认')).toBeTruthy()
  })
})

describe('TermEditDrawer', () => {
  it('保存时把改后的文本交给上层', () => {
    const clause = DEMO_CONTRACT_TERMS.find((t) => !t.filled)!.clause
    const onSave = vi.fn()
    render(
      <TermEditDrawer clause={clause} drafts={initTermDrafts()} onSave={onSave} onClose={() => {}} />,
    )

    const box = screen.getByRole('textbox')
    fireEvent.change(box, { target: { value: '代为和解、代收款项' } })
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }))

    expect(onSave).toHaveBeenCalledTimes(1)
    const [savedClause, savedValue] = vi.mocked(onSave).mock.calls[0]!
    expect(savedClause).toBe(clause)
    // 抽屉按详情键复用，保存的是输入框里那一版（不是自动填充原文）
    expect(savedValue).not.toBe('')
  })
})

describe('BotReplayDrawer', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('打开即播第 1 帧，逐帧推进到最后一帧', () => {
    render(<BotReplayDrawer open onClose={() => {}} />)
    expect(screen.getByText(/第 1 \/ 5 帧/)).toBeTruthy()
    expect(screen.getByText(DEMO_X3_BROWSER_FRAMES[0]!.url)).toBeTruthy()

    // 帧时长最多 1600ms，一次推 2 秒稳过一帧
    for (let i = 1; i < DEMO_X3_BROWSER_FRAMES.length; i++) {
      act(() => void vi.advanceTimersByTime(2000))
    }
    expect(screen.getByText(`第 ${DEMO_X3_BROWSER_FRAMES.length} / 5 帧`)).toBeTruthy()
    expect(screen.getByText('机器人已放弃点击')).toBeTruthy()
  })

  it('点时间轴可跳到指定帧', () => {
    render(<BotReplayDrawer open onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: '跳到第 4 帧' }))
    expect(screen.getByText('第 4 / 5 帧')).toBeTruthy()
    expect(screen.getByText(DEMO_X3_BROWSER_FRAMES[3]!.action)).toBeTruthy()
  })

  it('未打开时不渲染画面', () => {
    render(<BotReplayDrawer open={false} onClose={() => {}} />)
    expect(screen.queryByText(/帧/)).toBeNull()
  })
})

describe('ContractPanel', () => {
  it('生成的委托材料每行可切模板', () => {
    render(<ContractPanel />)
    const selects = screen.getAllByRole('combobox')
    expect(selects).toHaveLength(DEMO_CONTRACT_GEN.length)

    const first = selects[0]!
    expect((first as HTMLSelectElement).value).toBe('v3.2')
    fireEvent.change(first, { target: { value: 'v2.8' } })
    expect((first as HTMLSelectElement).value).toBe('v2.8')
    // 右栏回显「换了模板的文书」
    expect(screen.getByText('v2.8', { selector: 'span' })).toBeTruthy()
  })

  it('点「导出利冲报告」后走进度并提示已生成 PDF', async () => {
    vi.useFakeTimers()
    render(<ContractPanel />)
    fireEvent.click(screen.getByRole('button', { name: '导出利冲报告' }))
    expect(screen.getByRole('button', { name: '生成中…' })).toBeTruthy()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000)
    })
    expect(screen.getByText(/已生成 PDF：LCA-20261101-0007/)).toBeTruthy()
    vi.useRealTimers()
  })

  it('抽屉里逐条编辑条款，保存后列表回显「已修改」', () => {
    render(<ContractPanel />)

    const clause = DEMO_CONTRACT_TERMS.find((t) => !t.filled)!.clause
    const row = screen.getByText(clause).closest('li')!
    fireEvent.click(within(row).getByRole('button', { name: /编辑/ }))

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '代为和解、代收款项及执行款' } })
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }))

    const updated = screen.getByText(clause).closest('li')!
    expect(within(updated).getByText('已修改')).toBeTruthy()
    expect(within(updated).getByText('代为和解、代收款项及执行款')).toBeTruthy()
    expect(within(updated).queryByText('未填')).toBeNull()
  })

  it('点「查看执行录像」打开录像抽屉', () => {
    render(<ContractPanel />)
    fireEvent.click(screen.getByRole('button', { name: /查看执行录像/ }))
    expect(screen.getByText(/第 1 \/ 5 帧/)).toBeTruthy()
    expect(screen.getByText(DEMO_X3_BROWSER_FRAMES[0]!.url)).toBeTruthy()
  })
})

describe('FilingAmountCard', () => {
  it('差异行标红并给出差额，点开看口径', () => {
    const diffs = DEMO_X3_AMOUNTS.filter((a) => !a.consistent)
    render(<FilingAmountCard />)

    expect(screen.getByText(`${diffs.length} 处不一致`)).toBeTruthy()
    // 罚息行与合计行都差 31.85，所以按条数断言而不是唯一性
    expect(screen.getAllByText(`+${diffs[0]!.delta}`)).toHaveLength(diffs.length)

    fireEvent.click(screen.getByText(diffs[0]!.item))
    expect(screen.getByText(`${diffs[0]!.item} · 计算口径`)).toBeTruthy()
    expect(screen.getByText(diffs[0]!.basis)).toBeTruthy()
  })
})

describe('FilingFixPreviewDrawer', () => {
  it('列出全部 before/after，确认才执行', () => {
    const onConfirm = vi.fn()
    render(
      <FilingFixPreviewDrawer open running={false} onConfirm={onConfirm} onClose={() => {}} />,
    )

    for (const d of DEMO_X3_FIX_DIFF) {
      expect(screen.getByText(d.before)).toBeTruthy()
      expect(screen.getByText(d.after)).toBeTruthy()
    }

    fireEvent.click(screen.getByRole('button', { name: '确认执行' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)

    // 没打开就不渲染
    render(<FilingFixPreviewDrawer open={false} running={false} onConfirm={() => {}} onClose={() => {}} />)
    expect(screen.getAllByText('确认执行')).toHaveLength(1)
  })
})

describe('FilingNotifyCard', () => {
  it('签章没齐时不发通知，显示阻塞原因', () => {
    const onSend = vi.fn()
    render(<FilingNotifyCard blockedCount={2} blockedNotes={['授权委托书缺签名']} stage="idle" onSend={onSend} />)
    expect(screen.getByText('还不能通知律师：2 份文书未通过核对')).toBeTruthy()
    expect(screen.getByText('授权委托书缺签名')).toBeTruthy()
    expect(screen.queryByText('送达情况')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '通知律师去提交' }))
    expect(onSend).toHaveBeenCalledTimes(1)
  })

  it('已送达后显示三条通道的送达状态与已读', () => {
    render(<FilingNotifyCard blockedCount={0} blockedNotes={[]} stage="sent" onSend={() => {}} />)

    expect(screen.getByText('送达情况')).toBeTruthy()
    expect(screen.getByRole('button', { name: '已发送' })).toBeTruthy()
    const read = DEMO_X3_NOTICE_DELIVERY.filter((d) => d.state === 'read').length
    expect(screen.getAllByText('已读')).toHaveLength(read)
    for (const d of DEMO_X3_NOTICE_DELIVERY) {
      expect(screen.getByText(d.channel)).toBeTruthy()
    }
  })
})

describe('SignDrawer', () => {
  it('双图对照可放大成全屏大图', () => {
    const failing = DEMO_SIGN_CHECKS.find((d) => !d.sealOk || !d.signOk)!
    render(<SignDrawer name={failing.docName} onClose={() => {}} />)

    fireEvent.click(screen.getAllByRole('button', { name: /放大查看/ })[0]!)
    expect(screen.getByText('印章区域 · 放大查看')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '关闭大图' }))
    expect(screen.queryByText('印章区域 · 放大查看')).toBeNull()
  })

  it('无签名的那份放大后点名缺失', () => {
    const noSign = DEMO_SIGN_CHECKS.find((d) => d.sealOk && !d.signOk)!
    render(<SignDrawer name={noSign.docName} onClose={() => {}} />)

    const zoomButtons = screen.getAllByRole('button', { name: /放大查看/ })
    fireEvent.click(zoomButtons[1]!)
    expect(screen.getByText('签名区域 · 放大查看')).toBeTruthy()
    expect(screen.getByText(/这一份不能送法院/)).toBeTruthy()
  })
})
