// @vitest-environment jsdom
/**
 * ⑤ 回扫面板（`ReturnedPanel`）的交互测试（jsdom）。
 *
 * - 归案日志筛选（自动归案 / 待人工 / 已标记无关）
 * - 附件就地预览、邮箱配置弹窗、手动归案的「搜案件 → 选槽位 → 确认」
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DEMO_X2_MAIL_ATTACHMENTS } from '../demo-data'
import { ReturnedPanel } from './ReturnedPanel'

describe('ReturnedPanel · 归案日志筛选', () => {
  it('筛选「自动归案」只留自动归的，筛选「待人工」只留要人工定的', () => {
    render(<ReturnedPanel />)
    expect(screen.getByText('FW: 律师函签收回执')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /^自动归案/ }))
    expect(screen.queryByText('FW: 律师函签收回执')).toBeNull()
    expect(screen.getByText('Re: 谭某某案 补充材料')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /^待人工/ }))
    expect(screen.getByText('FW: 律师函签收回执')).toBeTruthy()
    expect(screen.queryByText('Re: 谭某某案 补充材料')).toBeNull()
  })

  it('在邮件抽屉里标记为无关后，该封只在「已标记无关」下出现', () => {
    render(<ReturnedPanel />)
    fireEvent.click(screen.getByText('FW: 律师函签收回执'))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '标记为无关' }))

    fireEvent.click(screen.getByRole('button', { name: /^已标记无关/ }))
    expect(screen.getByText('FW: 律师函签收回执')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /^待人工/ }))
    expect(screen.queryByText('FW: 律师函签收回执')).toBeNull()
  })
})

describe('ReturnedPanel · 附件预览', () => {
  it('邮件抽屉里点附件行就地展开预览占位', () => {
    render(<ReturnedPanel />)
    fireEvent.click(screen.getByText('扫描件-不动产权证'))

    const drawer = screen.getByRole('dialog')
    const file = DEMO_X2_MAIL_ATTACHMENTS.find((a) => a.subject === '扫描件-不动产权证')!
    const row = within(drawer).getByRole('button', { name: new RegExp(file.name) })
    expect(within(drawer).queryByText('PDF 首页预览占位')).toBeNull()

    fireEvent.click(row)
    expect(within(drawer).getByText('PDF 首页预览占位')).toBeTruthy()
    expect(within(drawer).getByText(`${file.pages} 页 · 第 1 页 / ${file.pages}`)).toBeTruthy()

    fireEvent.click(row)
    expect(within(drawer).queryByText('PDF 首页预览占位')).toBeNull()
  })
})

describe('ReturnedPanel · 邮箱配置', () => {
  it('点「设置」打开弹窗，改轮询间隔保存后回写到卡片上', () => {
    render(<ReturnedPanel />)
    fireEvent.click(screen.getAllByRole('button', { name: /设置/ })[0]!)
    expect(screen.getByText('邮箱扫描设置')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('轮询间隔'), { target: { value: '1 分钟' } })
    fireEvent.change(screen.getByLabelText('监听文件夹'), { target: { value: 'INBOX / 送达文书 / 加急' } })
    fireEvent.click(screen.getByRole('button', { name: '保存配置' }))

    expect(screen.queryByText('邮箱扫描设置')).toBeNull()
    expect(screen.getByText('已改配置')).toBeTruthy()
    expect(screen.getByText(/每 1 分钟 · INBOX \/ 送达文书 \/ 加急/)).toBeTruthy()
  })
})

describe('ReturnedPanel · 手动归案', () => {
  it('「指定归属」弹出搜案件 → 选槽位 → 确认（进度跑到 100%）', async () => {
    render(<ReturnedPanel />)
    fireEvent.click(screen.getByRole('button', { name: /指定归属/ }))

    const drawer = screen.getByRole('dialog')
    // 搜案件
    fireEvent.change(within(drawer).getByLabelText('搜案件名称或案号'), { target: { value: '信用卡' } })
    expect(within(drawer).getByText("李某某信用卡纠纷")).toBeTruthy()
    expect(within(drawer).queryByText('谭某某金融借款')).toBeNull()

    // 选中后出现该案的槽位
    fireEvent.click(within(drawer).getByText("李某某信用卡纠纷"))
    expect(within(drawer).getByRole('button', { name: '信用卡对账单' })).toBeTruthy()

    fireEvent.click(within(drawer).getByRole('button', { name: '催收记录' }))
    fireEvent.click(within(drawer).getByRole('button', { name: /确认归案/ }))

    // 进度跑完后抽屉标「已归案」，并把归入的案件 + 槽位写清楚
    expect(await screen.findByText('已归案', undefined, { timeout: 8000 })).toBeTruthy()
    expect(screen.getByText('已归入「李某某信用卡纠纷」· 催收记录，缺件检测已重跑')).toBeTruthy()
    expect(screen.getByText('100%')).toBeTruthy()
  }, 15000)
})
