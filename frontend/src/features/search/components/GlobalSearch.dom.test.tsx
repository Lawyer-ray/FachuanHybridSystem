// @vitest-environment jsdom
/**
 * GlobalSearch（⌘K 命令面板）组件渲染单测（jsdom + 真实 timers）。
 *
 * mock 只打 api 层（../api 的 runSearch；CATEGORY_ORDER 等常量保留真实实现）。
 * 覆盖：开关挂载、输入防抖 250ms 触发查询（trim 后上送）、结果按类别分组渲染、
 * 项目类「合同组头 + 案件挂其下」分组与路由分流（诉讼/非诉/案件锚点）、
 * 空结果兜底、筛选标签前端过滤、键盘 ↑↓/Enter 选中跳转（inbox 跳
 * /material-prep/:id、未建页类别回调 onPickUnavailable）、查询失败分支、
 * 关闭再打开状态清零。
 * 防抖用真实短等待断言（fake timers 与 RTL waitFor 的探测不兼容，参照既有用例先例）。
 */
import { type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, runSearch: vi.fn() }
})

import { runSearch } from '../api'
import type { Hit } from '../types'

import { GlobalSearch } from './GlobalSearch'

const runSearchMock = vi.mocked(runSearch)

const onOpenChange = vi.fn()
const onPickUnavailable = vi.fn()

/** 通用命中工厂：Hit 现含 case_type/contract_* 字段（生成物 SearchResultItem 全量形状） */
function makeHit(category: string, id: number, title: string, subtitle = '', side: '' | 'ours' | 'opposing' = '', extra: Partial<Hit> = {}): Hit {
  return { category, id, title, subtitle, side, case_type: '', contract_id: null, contract_name: '', ...extra }
}

/** 项目类命中：contract=合同（项目）本身命中；case=挂在项目下的案件命中 */
function makeProject(kind: 'contract' | 'case', id: number, title: string, extra: Partial<Hit> = {}): Hit {
  return makeHit('projects', id, title, '', '', { kind, ...extra })
}

/** 路由探针：把导航目标的 pathname+hash 打到 DOM 上，供跳转断言 */
function LocationProbe({ label }: { label: string }) {
  const loc = useLocation()
  return <div>{`${label}:${loc.pathname}${loc.hash}`}</div>
}

function setupUi(open = true) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <GlobalSearch open={open} onOpenChange={onOpenChange} onPickUnavailable={onPickUnavailable} />
        <Routes>
          <Route path="/material-prep/:id" element={<div>material-reader-page</div>} />
          <Route path="/projects/:id/nonlit" element={<LocationProbe label="nonlit" />} />
          <Route path="/projects/:id" element={<LocationProbe label="lit" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const input = () => screen.getByPlaceholderText('搜项目 / 当事人 / 收件箱 / 法院短信 / 联系人')

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

beforeEach(() => {
  vi.clearAllMocks()
  runSearchMock.mockResolvedValue([])
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('GlobalSearch 挂载与引导', () => {
  it('open=false：面板不渲染，也不发请求', () => {
    setupUi(false)
    expect(screen.queryByPlaceholderText(/搜项目/)).toBeNull()
    expect(runSearch).not.toHaveBeenCalled()
  })

  it('打开且无关键词：展示引导文案，停顿后仍不发请求', async () => {
    setupUi(true)
    expect(screen.getByText('输入关键词开始搜索')).toBeTruthy()
    await sleep(320)
    expect(runSearch).not.toHaveBeenCalled()
  })

  it('关闭再打开：上次输入被清空，回到引导态（防抖窗口后）', async () => {
    runSearchMock.mockResolvedValue([makeProject('contract', 3, '王五委托合同')])
    const { rerender } = setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await waitFor(() => expect(runSearch).toHaveBeenCalledWith('王五'))
    expect(await screen.findByText('王五委托合同')).toBeTruthy()

    // 挂起后续查询：重开后旧词的最后一批响应不落进新面板
    runSearchMock.mockReturnValue(new Promise(() => {}))
    const shell = ({ open }: { open: boolean }): ReactNode => (
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <GlobalSearch open={open} onOpenChange={onOpenChange} />
        </MemoryRouter>
      </QueryClientProvider>
    )
    rerender(shell({ open: false }))
    rerender(shell({ open: true }))
    // q 被关闭 effect 清空，debounced 在 250ms 防抖后跟上 → 回到引导态
    await waitFor(() => expect(screen.getByText('输入关键词开始搜索')).toBeTruthy(), { timeout: 2000 })
    expect(screen.queryByText('王五委托合同')).toBeNull()
  })
})

describe('GlobalSearch 防抖查询', () => {
  it('输入停顿 250ms 后才触发查询，且关键词 trim 后上送', async () => {
    setupUi(true)
    fireEvent.change(input(), { target: { value: '  王五  ' } })
    // 防抖窗口内（100ms < 250ms）不重查
    await sleep(100)
    expect(runSearch).not.toHaveBeenCalled()
    await waitFor(() => expect(runSearch).toHaveBeenCalledWith('王五'), { timeout: 2000 })
  })

  it('查询失败：不崩溃，落到空结果兜底文案', async () => {
    runSearchMock.mockRejectedValue(new Error('网络中断'))
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await waitFor(() => expect(runSearch).toHaveBeenCalled())
    expect(await screen.findByText('没有匹配「王五」的结果')).toBeTruthy()
  })
})

describe('GlobalSearch 结果渲染', () => {
  it('结果按类别分组渲染：组标签 + 标题 + 副标题 + 全部计数', async () => {
    runSearchMock.mockResolvedValue([
      makeProject('contract', 3, '王五委托合同', { case_type: 'civil' }),
      makeHit('inbox', 7, '法院专递-王五', '2 个附件'),
    ])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    expect(await screen.findByText('王五委托合同')).toBeTruthy()
    // 组标签是 div；同名筛选标签是 button（own text 同为「项目」），用 selector 区分
    expect(screen.getByText('项目', { selector: 'div' })).toBeTruthy()
    expect(screen.getByText('收件箱', { selector: 'div' })).toBeTruthy()
    expect(screen.getByText('法院专递-王五')).toBeTruthy()
    // 筛选标签的可访问名是「标签+计数」紧拼（如「全部2」），用正则容忍
    expect(screen.getByRole('button', { name: /^全部/ })).toBeTruthy()
  })

  it('项目分组：合同作组头、案件挂其下缩进；合同没命中时用案件携带的合同名补组头（不可点）', async () => {
    runSearchMock.mockResolvedValue([
      makeProject('case', 21, '赵六常法日常事务', { contract_id: 9, contract_name: '赵六常年法律顾问合同', case_type: 'advisor' }),
      makeProject('contract', 3, '王五委托合同', { case_type: 'civil' }),
      makeProject('case', 11, '王五一审案', { contract_id: 3, contract_name: '王五委托合同', case_type: 'civil', subtitle: '(2026)粤01民初1号' }), // privacy-allow 虚构案号
    ])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王' } })
    expect(await screen.findByText('王五委托合同')).toBeTruthy()
    expect(screen.getByText('王五一审案')).toBeTruthy()
    expect(screen.getByText('(2026)粤01民初1号')).toBeTruthy() // privacy-allow 虚构案号
    // 合同 9 没命中：组头来自案件携带的 contract_name，且非诉案件组头带「非诉」标
    expect(screen.getByText('赵六常年法律顾问合同')).toBeTruthy()
    expect(screen.getByText('赵六常法日常事务')).toBeTruthy()
    expect(screen.getByText('非诉')).toBeTruthy()
  })

  it('无命中：展示空态文案', async () => {
    runSearchMock.mockResolvedValue([])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '不存在' } })
    expect(await screen.findByText('没有匹配「不存在」的结果')).toBeTruthy()
  })

  it('当事人类：组标签叫「当事人」不叫「客户」，命中带我方/对方徽章，电话原样显示', async () => {
    runSearchMock.mockResolvedValue([
      makeHit('clients', 2, '甲方运动用品有限公司', '0757-22334455', 'ours'), // privacy-allow 虚构号码
      makeHit('clients', 3, '乙方科技有限公司', '13800000000', 'opposing'), // privacy-allow 虚构号码
    ])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '有限公司' } })
    expect(await screen.findByText('甲方运动用品有限公司')).toBeTruthy()
    expect(screen.getByText('当事人', { selector: 'div' })).toBeTruthy()
    expect(screen.queryByText('客户', { selector: 'div' })).toBeNull()
    expect(screen.getByRole('button', { name: /^当事人/ })).toBeTruthy()
    expect(screen.getByText('我方')).toBeTruthy()
    expect(screen.getByText('对方')).toBeTruthy()
    // 座机号原样出现，不再是一串星号
    expect(screen.getByText('0757-22334455')).toBeTruthy() // privacy-allow 虚构号码
  })

  it('非当事人类命中（side 为空）不渲染我方/对方徽章', async () => {
    runSearchMock.mockResolvedValue([makeHit('court_sms', 1, '开庭通知短信')])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '开庭' } })
    await screen.findByText('开庭通知短信')
    expect(screen.queryByText('我方')).toBeNull()
    expect(screen.queryByText('对方')).toBeNull()
  })

  it('筛选标签是纯前端过滤：点「收件箱」后只留该类别命中', async () => {
    runSearchMock.mockResolvedValue([
      makeProject('contract', 3, '王五委托合同'),
      makeHit('inbox', 7, '法院专递-王五'),
    ])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await screen.findByText('王五委托合同')

    fireEvent.click(screen.getByRole('button', { name: /^收件箱/ }))
    expect(screen.getByText('法院专递-王五')).toBeTruthy()
    expect(screen.queryByText('王五委托合同')).toBeNull()
  })
})

describe('GlobalSearch 项目路由分流', () => {
  it('诉讼合同命中点击：关面板并跳 /projects/:id', async () => {
    runSearchMock.mockResolvedValue([makeProject('contract', 3, '王五委托合同', { case_type: 'civil' })])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    fireEvent.click(await screen.findByText('王五委托合同'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(await screen.findByText('lit:/projects/3')).toBeTruthy()
  })

  it('非诉合同命中点击：跳 /projects/:id/nonlit', async () => {
    runSearchMock.mockResolvedValue([makeProject('contract', 4, '赵六常年法律顾问合同', { case_type: 'advisor' })])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '赵六' } })
    fireEvent.click(await screen.findByText('赵六常年法律顾问合同'))
    expect(await screen.findByText('nonlit:/projects/4/nonlit')).toBeTruthy()
  })

  it('案件命中点击：跳所属合同项目页并带 #case-<id> 锚点', async () => {
    runSearchMock.mockResolvedValue([
      makeProject('case', 11, '王五一审案', { contract_id: 5, contract_name: '王五委托合同', case_type: 'civil' }),
    ])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '一审' } })
    fireEvent.click(await screen.findByText('王五一审案'))
    expect(await screen.findByText('lit:/projects/5#case-11')).toBeTruthy()
  })

  it('键盘序与分组渲染一致：↓ 一次到案件行，回车跳案件锚点', async () => {
    runSearchMock.mockResolvedValue([
      makeProject('contract', 5, '王五委托合同', { case_type: 'civil' }),
      makeProject('case', 11, '王五一审案', { contract_id: 5, contract_name: '王五委托合同', case_type: 'civil' }),
    ])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await screen.findByText('王五委托合同')

    fireEvent.keyDown(input(), { key: 'ArrowDown' })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(await screen.findByText('lit:/projects/5#case-11')).toBeTruthy()
  })

  it('无合同的案件（历史孤案）按未建页处理：回调传「项目」', async () => {
    runSearchMock.mockResolvedValue([makeProject('case', 11, '历史孤案')])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '孤案' } })
    expect(await screen.findByText('历史孤案')).toBeTruthy()
    expect(screen.getByText('未建页')).toBeTruthy()

    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onPickUnavailable).toHaveBeenCalledWith('项目')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

describe('GlobalSearch 键盘导航与选中', () => {
  it('inbox 命中回车：关闭面板并跳转 /material-prep/:id', async () => {
    runSearchMock.mockResolvedValue([makeHit('inbox', 7, '法院专递-王五')])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await screen.findByText('法院专递-王五')

    fireEvent.keyDown(input(), { key: 'ArrowDown' })
    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(await screen.findByText('material-reader-page')).toBeTruthy()
  })

  it('未建页类别回车：回调 onPickUnavailable（传类别展示名）并关闭面板', async () => {
    runSearchMock.mockResolvedValue([makeHit('clients', 1, '王五委托人')])
    setupUi(true)
    fireEvent.change(input(), { target: { value: '王五' } })
    await screen.findByText('王五委托人')
    expect(screen.getByText('未建页')).toBeTruthy()

    fireEvent.keyDown(input(), { key: 'Enter' })
    expect(onPickUnavailable).toHaveBeenCalledWith('当事人')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(screen.queryByText('material-reader-page')).toBeNull()
  })
})
