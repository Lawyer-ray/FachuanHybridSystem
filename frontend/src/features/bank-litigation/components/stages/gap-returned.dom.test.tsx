// @vitest-environment jsdom
/**
 * ③ 缺件 / ⑤ 回扫 的交互测试（jsdom）。
 *
 * 两个面板的细节都藏在交互里，只看渲染出来的字不够：
 * - 缺件：来源分组过滤、勾选批量操作、话术编辑后回显、抽屉里的客户往来时间线
 * - 回扫：归案日志筛选、附件就地预览、邮箱配置弹窗、手动归案的搜案件→选槽位
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  DEMO_GAP_NOTICES,
  DEMO_X2_GAP_SCRIPTS,
  DEMO_X2_GAP_SOURCES,
  DEMO_X2_GAP_TIMELINE,
  DEMO_X2_MAIL_ATTACHMENTS,
} from '../demo-data'
import { GapPanel } from './GapPanel'
import { ReturnedPanel } from './ReturnedPanel'

describe('GapPanel · 客户往来时间线', () => {
  it('点开一条缺件，抽屉里给出这条缺件的完整沟通过程，每条带渠道与时间', () => {
    render(<GapPanel />)
    // 同一句话在「缺件清单」和「客户补回来的材料」里各出现一次，点清单那一行
    fireEvent.click(screen.getAllByText('催收记录（2025 年后）')[0]!)

    const drawer = screen.getByRole('dialog')
    const events = DEMO_X2_GAP_TIMELINE.filter((t) => t.item === '催收记录（2025 年后）')
    expect(within(drawer).getByText(`客户往来时间线（${events.length} 条）`)).toBeTruthy()
    // 首条（系统检测）与末条（重跑缺件检测）都在画面上
    expect(within(drawer).getByText('检测到缺件，生成补件清单')).toBeTruthy()
    expect(within(drawer).getByText('重跑缺件检测')).toBeTruthy()
    // 每条事件的时刻都照实显示
    for (const at of new Set(events.map((e) => e.at))) {
      expect(within(drawer).getAllByText(at).length).toBeGreaterThan(0)
    }
    // 渠道标签（短信 / 邮件 / 客户 / 系统）逐条带出来
    expect(within(drawer).getAllByText('短信').length).toBeGreaterThan(0)
    expect(within(drawer).getAllByText('客户').length).toBeGreaterThan(0)
  })
})

describe('GapPanel · 来源分组', () => {
  it('切到「担保类」只剩担保类缺件，再切回「全部」恢复全量', () => {
    render(<GapPanel />)
    const suretyship = DEMO_X2_GAP_SOURCES.filter((s) => s.source === '担保类').map((s) => s.item)

    fireEvent.click(screen.getByRole('button', { name: /^担保类/ }))
    // 只看清单列表：已补齐的项在「客户补回来的材料」那张卡里仍会显示
    const listAfter = () => screen.getAllByRole('list')[0]!
    expect(within(listAfter()).getByText(suretyship[0]!)).toBeTruthy()
    for (const g of DEMO_GAP_NOTICES.filter((n) => !suretyship.includes(n.item))) {
      expect(within(listAfter()).queryByText(g.item)).toBeNull()
    }

    fireEvent.click(screen.getByRole('button', { name: /^全部/ }))
    for (const g of DEMO_GAP_NOTICES) {
      expect(within(listAfter()).getByText(g.item)).toBeTruthy()
    }
  })
})

describe('GapPanel · 勾选与批量操作', () => {
  it('全选后可批量催办，回执按勾选条数给出', async () => {
    render(<GapPanel />)
    // 只勾一条「还没补齐」的硬阻塞项
    fireEvent.click(screen.getByRole('button', { name: '勾选 抵押物权属证明' }))
    expect(screen.getByText('已选 1 项')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '批量催办' }))
    const note = await screen.findByText(/已批量催办 1 项：抵押物权属证明/, undefined, { timeout: 5000 })
    expect(note).toBeTruthy()
  })

  it('没勾选时批量按钮不可点', () => {
    render(<GapPanel />)
    expect((screen.getByRole('button', { name: '批量催办' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: '批量标记已收' }) as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('GapPanel · 话术可编辑', () => {
  it('编辑话术后保存，卡片上回显新话术并标「已改过」，可恢复默认', () => {
    render(<GapPanel />)
    const first = DEMO_X2_GAP_SCRIPTS[0]!
    fireEvent.click(screen.getAllByRole('button', { name: /编辑话术/ })[0]!)

    const textarea = screen.getByLabelText(`编辑「${first.title}」话术`) as HTMLTextAreaElement
    expect(textarea.value).toBe(first.body)
    fireEvent.change(textarea, { target: { value: '【定制】请于 3 日内补齐：{list}' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(screen.getByText('【定制】请于 3 日内补齐：{list}')).toBeTruthy()
    expect(screen.getByText('已改过')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '恢复默认' }))
    expect(screen.queryByText('【定制】请于 3 日内补齐：{list}')).toBeNull()
    expect(screen.getByText(first.body)).toBeTruthy()
  })
})

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
