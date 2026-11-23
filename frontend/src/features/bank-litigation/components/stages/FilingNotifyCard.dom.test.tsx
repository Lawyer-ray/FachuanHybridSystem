// @vitest-environment jsdom
/**
 * 通知律师卡（`FilingNotifyCard`）单测（jsdom）。
 *
 * - 签章没齐时不发通知，显示阻塞原因
 * - 已送达后显示三条通道的送达状态与已读
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_X3_NOTICE_DELIVERY } from '../demo-data'
import { FilingNotifyCard } from './FilingNotifyCard'

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
