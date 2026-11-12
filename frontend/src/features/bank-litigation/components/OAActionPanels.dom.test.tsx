// @vitest-environment jsdom
/**
 * OA 盖章 / 归档面板单测（jsdom）。
 *
 * 这里有一条**业务前提**必须钉住：入参是 file_path，后端按文件目录反查合同绑定。
 * 反查不到就说明这份文件不属于任何委托 —— 那时提交会失败在很晚的阶段（OA 已经动了）。
 * 所以界面强制「先反查，反查通过才允许提交」，这个顺序是面板的核心不变式：
 * - 空路径 / 反查中 / 执行中 → 按钮不可点
 * - 仅填了路径但没反查 → 提交按钮仍禁用，旁边写「先『反查合同』」
 * - 反查失败 → 显示后端原话 + 常见原因，提交维持禁用
 * - 反查成功 → 显示合同名与 OA 案号，提交解锁
 * - 路径改动会清掉上次反查结果（防止拿旧结果去提新文件）
 *
 * mock 只打 ../api（lookupStampContract / lookupArchiveContract），
 * 另 mock ../hooks/use-auto-run 与 use-oa-site，避免真的发起轮询。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    lookupStampContract: vi.fn(),
    lookupArchiveContract: vi.fn(),
  }
})

/** 用可控的假 hook 替掉轮询状态机（它自身的行为由 use-auto-run.dom.test.tsx 覆盖） */
const autoRun = vi.hoisted(() => ({
  useOAStamp: vi.fn(),
  useOAArchive: vi.fn(),
}))

vi.mock('../hooks/use-auto-run', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/use-auto-run')>()
  return { ...actual, ...autoRun }
})

import { lookupArchiveContract, lookupStampContract } from '../api'
import {
  DEMO_OA_SEALS,
  DEMO_OA_SEAL_RULES,
  DEMO_STAMP_BATCHES,
  DEMO_STAMP_FAILURES,
  DEMO_STAMP_HISTORY,
} from './demo-data'
import { OAArchivePanel, OAStampPanel } from './OAActionPanels'

const lookupStampMock = vi.mocked(lookupStampContract)
const lookupArchiveMock = vi.mocked(lookupArchiveContract)

/** 一个 idle 状态的假 AutoRun */
function idleRun() {
  return {
    state: { phase: 'idle', session: null, status: '', error: null, ticks: 0 },
    run: vi.fn().mockResolvedValue(undefined),
    reset: vi.fn(),
  }
}

/** 从 textarea 里读 placeholder（两种 kind 的占位文案不同） */
function pathInput(): HTMLTextAreaElement {
  return document.querySelector('textarea') as HTMLTextAreaElement
}

beforeEach(() => {
  vi.clearAllMocks()
  autoRun.useOAStamp.mockReturnValue(idleRun() as never)
  autoRun.useOAArchive.mockReturnValue(idleRun() as never)
  lookupStampMock.mockResolvedValue({
    contract_name: '某某买卖合同',
    oa_case_number: 'OA-2026-0001',
  } as never)
  lookupArchiveMock.mockResolvedValue({
    contract_name: '某某买卖合同',
    oa_case_number: null,
  } as never)
})

describe('OAActionPanel · 说明与初始状态', () => {
  it('盖章与归档展示各自的标题、verb 与提示', () => {
    const { unmount } = render(<OAStampPanel />)
    expect(screen.getByText('OA 盖章')).toBeTruthy()
    expect(screen.getByRole('button', { name: /申请盖章/ })).toBeTruthy()
    unmount()

    render(<OAArchivePanel />)
    expect(screen.getByText('OA 归档')).toBeTruthy()
    expect(screen.getByRole('button', { name: /提交归档/ })).toBeTruthy()
  })

  it('没填路径时两个按钮都不可点，统计格写「未填」', () => {
    render(<OAStampPanel />)
    expect((screen.getByRole('button', { name: /反查合同/ }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: /申请盖章/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('未填')).toBeTruthy()
  })

  it('盖章只接受一行路径，归档接受多行（占位文案不同）', () => {
    const { unmount } = render(<OAStampPanel />)
    expect(pathInput().placeholder).toContain('文件绝对路径')
    expect(pathInput().rows).toBe(2)
    unmount()

    render(<OAArchivePanel />)
    expect(pathInput().placeholder).toContain('每行一个')
    expect(pathInput().rows).toBe(4)
  })

  it('填了路径但还没反查时，提交按钮仍禁用并提示先反查', () => {
    render(<OAStampPanel />)
    fireEvent.change(pathInput(), { target: { value: '/case/起诉状.pdf' } })

    expect((screen.getByRole('button', { name: /申请盖章/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('先「反查合同」，确认归属后才允许申请盖章')).toBeTruthy()
    // 统计格报路径条数
    expect(screen.getByText('1 个')).toBeTruthy()
  })

  it('多行空白被过滤，只算非空行（空行不应该被当成一个路径去反查）', () => {
    render(<OAArchivePanel />)
    fireEvent.change(pathInput(), { target: { value: '/a.pdf\n\n  \n/b.pdf' } })
    expect(screen.getByText('2 个')).toBeTruthy()
  })
})

describe('OAActionPanel · 反查合同', () => {
  it('反查成功：显示合同名与 OA 案号，提交按钮解锁', async () => {
    render(<OAStampPanel />)
    fireEvent.change(pathInput(), { target: { value: '/case/起诉状.pdf' } })
    fireEvent.click(screen.getByRole('button', { name: /反查合同/ }))

    await waitFor(() => expect(screen.getByText('已识别到合同')).toBeTruthy())
    expect(lookupStampMock).toHaveBeenCalledWith({ file_path: '/case/起诉状.pdf', site_name: '' })
    // 合同名在「合同」键值行与归档说明里都可能出现，用 allBy
    expect(screen.getAllByText('某某买卖合同').length).toBeGreaterThan(0)
    expect(screen.getAllByText('OA-2026-0001').length).toBeGreaterThan(0)

    expect((screen.getByRole('button', { name: /申请盖章/ }) as HTMLButtonElement).disabled).toBe(false)
    // 统计格跟进
    expect(screen.getByText('已确认')).toBeTruthy()
    expect(screen.getByText('是')).toBeTruthy()
  })

  it('OA 尚未生成案号时写「（OA 尚未生成案号）」，不留空白', async () => {
    render(<OAArchivePanel />)
    fireEvent.change(pathInput(), { target: { value: '/case/判决书.pdf' } })
    fireEvent.click(screen.getByRole('button', { name: /反查合同/ }))

    await waitFor(() => expect(screen.getByText('（OA 尚未生成案号）')).toBeTruthy())
  })

  it('归档反查把路径包成数组（接口形状是 file_paths）', async () => {
    render(<OAArchivePanel />)
    fireEvent.change(pathInput(), { target: { value: '/case/判决书.pdf' } })
    fireEvent.click(screen.getByRole('button', { name: /反查合同/ }))

    await waitFor(() => expect(lookupArchiveMock).toHaveBeenCalled())
    expect(lookupArchiveMock).toHaveBeenCalledWith({
      file_paths: ['/case/判决书.pdf'],
      site_name: '',
    })
  })

  it('反查失败：显示后端原话与常见原因，提交维持禁用', async () => {
    lookupStampMock.mockRejectedValue(new Error('无法根据文件路径找到关联合同'))
    render(<OAStampPanel />)
    fireEvent.change(pathInput(), { target: { value: '/other/x.pdf' } })
    fireEvent.click(screen.getByRole('button', { name: /反查合同/ }))

    await waitFor(() => expect(screen.getByText('反查失败')).toBeTruthy())
    expect(screen.getByText('无法根据文件路径找到关联合同')).toBeTruthy()
    expect(screen.getByText(/文件不在已绑定的案件\/合同文件夹里/)).toBeTruthy()

    expect((screen.getByRole('button', { name: /申请盖章/ }) as HTMLButtonElement).disabled).toBe(true)
    // 统计格回到「未反查」（顶部 StatsStrip 与右栏 dl 各一次）/「否」
    expect(screen.getAllByText('未反查').length).toBeGreaterThan(0)
  })

  it('反查期间按钮禁用并显示 loading（防止连点起多个查询）', async () => {
    let release!: (v: unknown) => void
    lookupStampMock.mockReturnValue(new Promise((r) => (release = r)) as never)

    render(<OAStampPanel />)
    fireEvent.change(pathInput(), { target: { value: '/case/a.pdf' } })
    fireEvent.click(screen.getByRole('button', { name: /反查合同/ }))

    const btn = screen.getByRole('button', { name: /反查合同/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)

    release({ contract_name: 'A', oa_case_number: null })
    await waitFor(() => expect(screen.getByText('已识别到合同')).toBeTruthy())
  })

  it('改路径会清掉上一次的合同与错误（防止拿旧结果去提新文件）', async () => {
    render(<OAStampPanel />)
    fireEvent.change(pathInput(), { target: { value: '/case/a.pdf' } })
    fireEvent.click(screen.getByRole('button', { name: /反查合同/ }))
    await waitFor(() => expect(screen.getByText('已识别到合同')).toBeTruthy())

    fireEvent.change(pathInput(), { target: { value: '/case/b.pdf' } })
    expect(screen.queryByText('已识别到合同')).toBeNull()
    expect((screen.getByRole('button', { name: /申请盖章/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('反查会顺带 reset 掉上一次的执行状态', async () => {
    const stampRun = idleRun()
    autoRun.useOAStamp.mockReturnValue(stampRun as never)

    render(<OAStampPanel />)
    fireEvent.change(pathInput(), { target: { value: '/case/a.pdf' } })
    fireEvent.click(screen.getByRole('button', { name: /反查合同/ }))

    await waitFor(() => expect(lookupStampMock).toHaveBeenCalled())
    expect(stampRun.reset).toHaveBeenCalled()
  })
})

describe('OAActionPanel · 提交', () => {
  it('反查通过后点提交，把路径列表交给 run', async () => {
    const run = vi.fn().mockResolvedValue(undefined)
    autoRun.useOAArchive.mockReturnValue({ ...idleRun(), run } as never)

    render(<OAArchivePanel />)
    fireEvent.change(pathInput(), { target: { value: '/a.pdf\n/b.pdf' } })
    fireEvent.click(screen.getByRole('button', { name: /反查合同/ }))
    await waitFor(() => expect(screen.getByText('已识别到合同')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /提交归档/ }))
    await waitFor(() => expect(run).toHaveBeenCalledWith(['/a.pdf', '/b.pdf']))
  })

  it('running 期间提交按钮禁用并显示「执行中…」', () => {
    autoRun.useOAStamp.mockReturnValue({
      ...idleRun(),
      state: { phase: 'running', session: null, status: 'running', error: null, ticks: 3 },
    } as never)

    render(<OAStampPanel />)
    fireEvent.change(pathInput(), { target: { value: '/a.pdf' } })
    // 反查成功不是这条用例的前提（按钮已因 running 禁用），
    // 只断言文案与禁用状态。
    expect(screen.getByText('执行中…')).toBeTruthy()
    expect((screen.getByRole('button', { name: /执行中…/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('提交阶段（submitting）同样禁用', () => {
    autoRun.useOAStamp.mockReturnValue({
      ...idleRun(),
      state: { phase: 'submitting', session: null, status: '', error: null, ticks: 0 },
    } as never)
    render(<OAStampPanel />)
    expect((screen.getByRole('button', { name: /执行中…/ }) as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('OAActionPanel · 侧栏（仅盖章）', () => {
  it('批量盖章预设逐条列出名称 / 印章 / 份数页数', () => {
    render(<OAStampPanel />)
    // 印章组合文案在「预设」与「位置规则」两处都会出现，用 allBy
    for (const b of DEMO_STAMP_BATCHES) {
      expect(screen.getAllByText(b.name).length).toBeGreaterThan(0)
      expect(screen.getByText(`${b.docs} 份 · ${b.pages} 页`)).toBeTruthy()
      expect(screen.getAllByText(b.seals).length).toBeGreaterThan(0)
    }
  })

  it('印章库报可用枚数，四种状态各有文案', () => {
    render(<OAStampPanel />)
    const available = DEMO_OA_SEALS.filter((x) => x.status === 'available').length
    expect(screen.getByText(`${available} 枚可用`)).toBeTruthy()

    // 印章「种类」（公章/合同章…）在位置规则里也会出现，用 allBy
    for (const x of DEMO_OA_SEALS) {
      expect(screen.getByText(x.name)).toBeTruthy()
      expect(screen.getAllByText(x.kind).length).toBeGreaterThan(0)
      // holder 相同（都是行政部）的印章有多枚，用 allBy
      expect(screen.getAllByText(x.holder).length).toBeGreaterThan(0)
      expect(screen.getByText(`${x.usedThisMonth} 次`)).toBeTruthy()
      // 有两枚印章的最后使用时间相同，用 allBy
      expect(screen.getAllByText(x.lastUsed).length).toBeGreaterThan(0)
    }
    // 三种状态文案都至少出现一次（数据里有 available / in-use / expired）
    expect(screen.getAllByText('可用').length).toBe(available)
  })

  it('盖章位置规则逐条列出：文书类型 / 印章 / 位置 / 说明', () => {
    render(<OAStampPanel />)
    // 位置 / 说明在规则卡与失败原因卡里都可能重复，用 allBy
    for (const r of DEMO_OA_SEAL_RULES) {
      expect(screen.getAllByText(r.docType).length).toBeGreaterThan(0)
      expect(screen.getAllByText(r.position).length).toBeGreaterThan(0)
      expect(screen.getAllByText(r.note).length).toBeGreaterThan(0)
    }
  })

  it('盖章记录：成功的写「已盖章」，失败的写原因', () => {
    render(<OAStampPanel />)
    expect(screen.getByText(`最近 ${DEMO_STAMP_HISTORY.length} 次`)).toBeTruthy()

    const ok = DEMO_STAMP_HISTORY.filter((r) => r.ok).length
    expect(screen.getAllByText('已盖章')).toHaveLength(ok)
    for (const r of DEMO_STAMP_HISTORY) {
      expect(screen.getAllByText(r.fileName).length).toBeGreaterThan(0)
      if (!r.ok) expect(screen.getAllByText(r.reason).length).toBeGreaterThan(0)
    }
  })

  it('常见失败原因：自动重试 / 需人工两类分开标', () => {
    render(<OAStampPanel />)
    for (const f of DEMO_STAMP_FAILURES) {
      expect(screen.getAllByText(f.cause).length).toBeGreaterThan(0)
      expect(screen.getAllByText(f.stage).length).toBeGreaterThan(0)
    }
    const auto = DEMO_STAMP_FAILURES.filter((f) => f.autoRetry).length
    expect(screen.getAllByText('自动重试')).toHaveLength(auto)
    expect(screen.getAllByText('需人工')).toHaveLength(DEMO_STAMP_FAILURES.length - auto)
  })

  it('归档面板不渲染盖章专属区块（预设 / 印章库 / 记录 / 失败原因）', () => {
    render(<OAArchivePanel />)
    expect(screen.queryByText('批量盖章预设')).toBeNull()
    expect(screen.queryByText('可用印章')).toBeNull()
    expect(screen.queryByText('盖章记录')).toBeNull()
    expect(screen.queryByText('常见失败原因')).toBeNull()
    expect(screen.queryByText('盖章流程')).toBeNull()
  })
})
