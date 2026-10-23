// @vitest-environment jsdom
/**
 * SmsSuccessBody 测试（jsdom）。
 *
 * 法院短信处理完成后的结果体：
 * - 归档案件 chip（有案件 / 未关联两种文案）
 * - 文书列表：逐件复制与下载；无文书时给说明
 * - 「查看详情」折叠：状态/类型/案号/当事人/通知/重试次数/短信原文
 * - 通知摘要只在有渠道时出现，并按 success 计数
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  courtSmsDocDownloadUrl: vi.fn(() => '/dl/doc'),
  triggerDownload: vi.fn(),
}))
const copyMock = vi.hoisted(() => ({ copyDocFile: vi.fn(async () => {}) }))

vi.mock('../../../api', () => ({
  courtSmsDocDownloadUrl: apiMock.courtSmsDocDownloadUrl,
  triggerDownload: apiMock.triggerDownload,
}))
vi.mock('./copy-files', () => ({ copyDocFile: copyMock.copyDocFile }))
vi.mock('./stages', () => ({
  SMS_STATUS_LABEL: { completed: '已完成', failed: '失败' },
  SMS_TYPE_LABEL: { hearing: '开庭通知' },
}))

import { SmsSuccessBody } from './SmsSuccessBody'
import type { CourtSmsDetail } from '../../../api'

function detail(over: Record<string, unknown> = {}): CourtSmsDetail {
  return {
    id: 9,
    status: 'completed',
    sms_type: 'hearing',
    case_numbers: ['（20XX）京01民初1号'],
    party_names: ['张三'],
    retry_count: 0,
    content: '短信原文内容',
    case: { id: 1, name: '张三诉李四' },
    documents: [{ id: 11, name: 'a.pdf' }],
    notification_results: null,
    ...over,
  } as unknown as CourtSmsDetail
}

function renderBody(d: CourtSmsDetail) {
  return render(<SmsSuccessBody detail={d} />)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SmsSuccessBody：归档 chip', () => {
  it('有案件时显示「已归档到案件：X」', () => {
    const { container } = renderBody(detail())
    expect(container.textContent).toContain('已归档到案件：张三诉李四')
    container.remove()
  })

  it('无案件时显示「本次未关联案件（通知类短信）」', () => {
    const { container } = renderBody(detail({ case: null }))
    expect(container.textContent).toContain('本次未关联案件')
    container.remove()
  })
})

describe('SmsSuccessBody：文书列表', () => {
  it('渲染文书件数与文件名', () => {
    const { container } = renderBody(detail())
    expect(container.textContent).toContain('已下载文书 1 件')
    expect(within(container).getByText('a.pdf')).toBeTruthy()
    container.remove()
  })

  it('无文书时给出说明', () => {
    const { container } = renderBody(detail({ documents: [] }))
    expect(container.textContent).toContain('没有附带可下载文书')
    container.remove()
  })

  it('点复制调用 copyDocFile 并带下标与文件名', async () => {
    const { container } = renderBody(detail())
    fireEvent.click(screen.getByRole('button', { name: /复制/ }))

    await waitFor(() => expect(copyMock.copyDocFile).toHaveBeenCalledWith(9, 0, 'a.pdf'))
    container.remove()
  })

  it('点下载调用 triggerDownload', () => {
    const { container } = renderBody(detail())
    fireEvent.click(screen.getByRole('button', { name: /下载/ }))

    expect(apiMock.triggerDownload).toHaveBeenCalled()
    // triggerDownload 接收的是工厂函数，URL 在工厂内才生成
    const factory = apiMock.triggerDownload.mock.calls[0]![0] as () => unknown
    void factory()
    expect(apiMock.courtSmsDocDownloadUrl).toHaveBeenCalledWith(9, 0)
    container.remove()
  })
})

describe('SmsSuccessBody：详情折叠', () => {
  it('默认收起，点「查看详情」展开', () => {
    const { container } = renderBody(detail())
    expect(container.textContent).not.toContain('短信原文')

    fireEvent.click(screen.getByRole('button', { name: /查看详情/ }))
    expect(container.textContent).toContain('短信原文')
    expect(container.textContent).toContain('短信原文内容')
    container.remove()
  })

  it('展开后按钮文案变为「收起详情」，再点收起', () => {
    const { container } = renderBody(detail())
    fireEvent.click(screen.getByRole('button', { name: /查看详情/ }))
    expect(screen.getByRole('button', { name: /收起详情/ })).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /收起详情/ }))
    expect(container.textContent).not.toContain('短信原文内容')
    container.remove()
  })

  it('展开后展示状态、类型、案号、当事人、重试次数', () => {
    const { container } = renderBody(detail())
    fireEvent.click(screen.getByRole('button', { name: /查看详情/ }))

    const text = container.textContent ?? ''
    expect(text).toContain('已完成')
    expect(text).toContain('开庭通知')
    expect(text).toContain('（20XX）京01民初1号')
    expect(text).toContain('张三')
    expect(text).toContain('重试次数')
    container.remove()
  })

  it('无案号与当事人时不渲染对应行', () => {
    const { container } = renderBody(detail({ case_numbers: [], party_names: [] }))
    fireEvent.click(screen.getByRole('button', { name: /查看详情/ }))

    const text = container.textContent ?? ''
    expect(text).not.toContain('案号')
    expect(text).not.toContain('当事人')
    container.remove()
  })

  it('未知状态回退显示原始值', () => {
    const { container } = renderBody(detail({ status: 'weird' }))
    fireEvent.click(screen.getByRole('button', { name: /查看详情/ }))
    expect(container.textContent).toContain('weird')
    container.remove()
  })
})

describe('SmsSuccessBody：通知摘要', () => {
  it('多渠道路由成功时显示 n/m 成功', () => {
    const { container } = renderBody(
      detail({
        notification_results: {
          wechat: { success: true },
          email: { success: false },
        },
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: /查看详情/ }))
    expect(container.textContent).toContain('通知 1/2 个渠道成功')
    container.remove()
  })

  it('无通知结果时不显示通知行', () => {
    const { container } = renderBody(detail({ notification_results: null }))
    fireEvent.click(screen.getByRole('button', { name: /查看详情/ }))
    expect(container.textContent).not.toContain('个渠道成功')
    container.remove()
  })

  it('空通知对象同样不显示', () => {
    const { container } = renderBody(detail({ notification_results: {} }))
    fireEvent.click(screen.getByRole('button', { name: /查看详情/ }))
    expect(container.textContent).not.toContain('个渠道成功')
    container.remove()
  })
})
