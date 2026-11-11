// @vitest-environment jsdom
/**
 * ForeignLawVerifyCard：泰国法核验（真调后端，真查 BARLC）。
 *
 * 这张卡的价值全在「证据感」：条文原文与 MCP 调用轨迹都是**真实返回**的，
 * 查到什么显示什么，查不到就说查不到。所以断言集中在：
 * - 三条引用逐条串行查询，每条的状态独立（一条失败不拖垮其余）
 * - 成功时显示原文 + 出处 + 耗时；`needs_model_judgement` 时标「待判断层比对」
 * - 失败时显示原因；抛错时显示错误消息
 * - 查询期间按钮禁用并显示「正在查询…」（接口 6–8 秒，不能让律师以为卡死）
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ verifyThaiLaw: vi.fn() }))

vi.mock('./foreign-law-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./foreign-law-api')>()
  return { ...actual, verifyThaiLaw: apiMock.verifyThaiLaw }
})

import { DEMO_THAI_CITATIONS } from './foreign-law-api'
import { ForeignLawVerifyCard } from './ForeignLawVerifyCard'

function okResult(over: Record<string, unknown> = {}) {
  return {
    ok: true,
    law_title: 'Civil and Commercial Code of Thailand',
    section_number: '538',
    section_text: 'Section text from BARLC',
    total_ms: 7000,
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('初始态', () => {
  it('列出三条引用与各自的合同主张', () => {
    render(<ForeignLawVerifyCard />)
    for (const c of DEMO_THAI_CITATIONS) {
      expect(screen.getByText(c.article)).toBeTruthy()
      expect(screen.getByText(`合同主张：${c.claim}`)).toBeTruthy()
    }
  })

  it('按钮文案与右下说明在未跑时', () => {
    render(<ForeignLawVerifyCard />)
    expect(screen.getByRole('button', { name: /核验这 3 条/ })).toBeTruthy()
    expect(screen.getByText('3 条引用 · 每条约 6-8 秒')).toBeTruthy()
  })
})

describe('成功路径', () => {
  it('串行查三条，逐条显示原文、出处与耗时', async () => {
    apiMock.verifyThaiLaw.mockResolvedValue(okResult())
    render(<ForeignLawVerifyCard />)
    fireEvent.click(screen.getByRole('button', { name: /核验这 3 条/ }))

    await waitFor(() => expect(screen.getAllByText('已取到原文')).toHaveLength(3))
    expect(apiMock.verifyThaiLaw).toHaveBeenCalledTimes(3)
    expect(screen.getAllByText('Section text from BARLC')).toHaveLength(3)
    expect(screen.getAllByText('BARLC 返回原文')).toHaveLength(3)
  })

  it('查完后按钮变「重新核验」，说明写通过/失败数', async () => {
    apiMock.verifyThaiLaw.mockResolvedValue(okResult())
    render(<ForeignLawVerifyCard />)
    fireEvent.click(screen.getByRole('button', { name: /核验这 3 条/ }))
    await waitFor(() => expect(screen.getByRole('button', { name: /重新核验/ })).toBeTruthy())
    expect(screen.getByText('通过 3 / 失败 0 · 每条约 6-8 秒')).toBeTruthy()
  })

  it('needs_model_judgement 时标「待判断层比对」（不假装结论已定）', async () => {
    apiMock.verifyThaiLaw.mockResolvedValue(okResult({ needs_model_judgement: true }))
    render(<ForeignLawVerifyCard />)
    fireEvent.click(screen.getByRole('button', { name: /核验这 3 条/ }))
    await waitFor(() => expect(screen.getAllByText('待判断层比对')).toHaveLength(3))
  })

  it('有 trace 时渲染 MCP 调用轨迹（看得出真连了 BARLC）', async () => {
    apiMock.verifyThaiLaw.mockResolvedValue(
      okResult({
        trace: [
          { name: 'asean_law_login', detail: '登录 BARLC', ok: true, result: 'token ok', ms: 900 },
          { name: 'asean_law_fetch', detail: '取正文', ok: false, result: 'timeout', ms: 6000 },
        ],
      }),
    )
    render(<ForeignLawVerifyCard />)
    fireEvent.click(screen.getByRole('button', { name: /核验这 3 条/ }))
    await waitFor(() => expect(screen.getAllByText('MCP 调用过程').length).toBeGreaterThan(0))
    expect(screen.getAllByText('asean_law_login').length).toBeGreaterThan(0)
    expect(screen.getAllByText('登录 BARLC').length).toBeGreaterThan(0)
    expect(screen.getAllByText('token ok').length).toBeGreaterThan(0)
    expect(screen.getAllByText('timeout').length).toBeGreaterThan(0)
  })
})

describe('失败路径', () => {
  it('ok=false 时标「未核验」并显示 reason', async () => {
    apiMock.verifyThaiLaw.mockResolvedValue({ ok: false, reason: 'BARLC 未收录该条文' })
    render(<ForeignLawVerifyCard />)
    fireEvent.click(screen.getByRole('button', { name: /核验这 3 条/ }))
    await waitFor(() => expect(screen.getAllByText('未核验')).toHaveLength(3))
    expect(screen.getAllByText('BARLC 未收录该条文')).toHaveLength(3)
    expect(screen.getByText('通过 0 / 失败 3 · 每条约 6-8 秒')).toBeTruthy()
  })

  it('请求抛错时显示错误消息（不静默吞掉）', async () => {
    apiMock.verifyThaiLaw.mockRejectedValue(new Error('网络中断'))
    render(<ForeignLawVerifyCard />)
    fireEvent.click(screen.getByRole('button', { name: /核验这 3 条/ }))
    await waitFor(() => expect(screen.getAllByText('网络中断')).toHaveLength(3))
  })

  it('非 Error 抛出时退化成字符串消息', async () => {
    apiMock.verifyThaiLaw.mockRejectedValue('纯字符串错误')
    render(<ForeignLawVerifyCard />)
    fireEvent.click(screen.getByRole('button', { name: /核验这 3 条/ }))
    await waitFor(() => expect(screen.getAllByText('纯字符串错误')).toHaveLength(3))
  })

  it('一条失败不影响后续条目继续查（逐张独立成败）', async () => {
    apiMock.verifyThaiLaw
      .mockResolvedValueOnce({ ok: false, reason: 'bad' })
      .mockResolvedValue(okResult())
    render(<ForeignLawVerifyCard />)
    fireEvent.click(screen.getByRole('button', { name: /核验这 3 条/ }))
    await waitFor(() => expect(screen.getAllByText('已取到原文')).toHaveLength(2))
    expect(screen.getAllByText('未核验')).toHaveLength(1)
  })
})

describe('查询中', () => {
  it('按钮禁用并显示「正在查询…」，跑完恢复', async () => {
    let release: (v: unknown) => void = () => {}
    apiMock.verifyThaiLaw.mockImplementation(() => new Promise((r) => (release = r)))
    render(<ForeignLawVerifyCard />)
    fireEvent.click(screen.getByRole('button', { name: /核验这 3 条/ }))

    const busy = await screen.findByRole('button', { name: /正在查询…/ })
    expect((busy as HTMLButtonElement).disabled).toBe(true)

    // 放掉三次查询
    for (let i = 0; i < 3; i++) {
      release(okResult())
      await waitFor(() => expect(apiMock.verifyThaiLaw).toHaveBeenCalledTimes(i + 1))
    }
    await waitFor(() => expect((screen.getByRole('button', { name: /重新核验/ }) as HTMLButtonElement).disabled).toBe(false))
  })
})
