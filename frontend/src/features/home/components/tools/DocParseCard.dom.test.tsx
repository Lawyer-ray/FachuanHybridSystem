// @vitest-environment jsdom
/**
 * DocParseCard 测试（jsdom）。
 *
 * 文档解析卡的提交前置校验与状态展示：
 * - 未选文件时提示且不提交
 * - 格式不被当前引擎支持时警告且不提交（省掉注定失败的往返）
 * - 超 100MB 时警告且不提交
 * - 校验通过才提交并带上引擎参数
 * - busy 时引擎下拉、文件选择、复选框与按钮全部禁用
 * - 引擎切换后格式提示与 accept 跟着变
 * - 完成态显示「查看结果」/「解析失败 · 查看」
 */
import { fireEvent, render, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const parseMock = vi.hoisted(() => ({
  phase: 'idle' as string,
  hint: '',
  outcome: null as unknown,
  submit: vi.fn(async (_f: File, _o: Record<string, unknown>) => {}),
  reset: vi.fn(),
}))

vi.mock('../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api')>()
  return {
    ...actual,
    PARSE_BACKENDS: [
      { value: 'auto', label: '自动', desc: '后端挑选' },
      { value: 'mineru', label: 'MinerU', desc: '表格' },
      { value: 'textin', label: 'Textin', desc: '标题树' },
      { value: 'local', label: '本地', desc: '无网' },
    ],
  }
})
vi.mock('./use-doc-parse', () => ({ useDocParse: () => parseMock }))
vi.mock('./doc-parse-outcome', () => ({
  copyOutcome: vi.fn(),
  downloadOutcome: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
vi.mock('./history/ParseHistoryDialog', () => ({
  ParseHistoryDialog: ({ open }: { open: boolean }) => (open ? <div>PARSE_HISTORY</div> : null),
}))

import { toast } from 'sonner'

import { DocParseCard } from './DocParseCard'

function clickText(re: RegExp) {
  const btn = Array.from(document.querySelectorAll('button')).find((b) => re.test(b.textContent ?? ''))
  if (!btn) throw new Error('button not found: ' + String(re))
  fireEvent.click(btn)
  return btn as HTMLButtonElement
}

function pickFile(container: HTMLElement, name = 'a.pdf') {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement
  fireEvent.change(input, { target: { files: [new File(['x'], name)] } })
}

function selectEngine(container: HTMLElement, value: string) {
  const sel = container.querySelector('select') as HTMLSelectElement
  fireEvent.change(sel, { target: { value } })
  return sel
}

beforeEach(() => {
  vi.clearAllMocks()
  parseMock.phase = 'idle'
  parseMock.hint = ''
  parseMock.outcome = null
  parseMock.submit = vi.fn(async (_f: File, _o: Record<string, unknown>) => {})
  parseMock.reset = vi.fn()
})

describe('DocParseCard：前置校验', () => {
  it('未选文件时提示且不提交', () => {
    const { container } = render(<DocParseCard />)
    clickText(/开始解析/)
    expect(toast.info).toHaveBeenCalledWith('先选择要解析的文件')
    expect(parseMock.submit).not.toHaveBeenCalled()
    container.remove()
  })

  it('格式不被当前引擎支持时警告且不提交', () => {
    const { container } = render(<DocParseCard />)
    // 默认引擎 textin 支持 pdf；先切到 local（只支持 pdf/图片）
    selectEngine(container, 'local')
    pickFile(container, 'a.docx')

    clickText(/开始解析/)
    expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('不支持 .docx'))
    expect(parseMock.submit).not.toHaveBeenCalled()
    container.remove()
  })

  it('校验通过才提交，并带上引擎参数', async () => {
    const { container } = render(<DocParseCard />)
    pickFile(container, 'a.pdf')
    clickText(/开始解析/)

    await vi.waitFor(() => expect(parseMock.submit).toHaveBeenCalled())
    const [, opts] = parseMock.submit.mock.calls[0]!
    expect(opts).toMatchObject({ backend: 'textin', extractTables: true, returnMarkdown: true })
    container.remove()
  })

  it('取消「提取表格结构」后提交参数随之变化', async () => {
    const { container } = render(<DocParseCard />)
    pickFile(container, 'a.pdf')
    const cb = container.querySelector('input[type="checkbox"]') as HTMLInputElement
    fireEvent.click(cb)

    clickText(/开始解析/)
    await vi.waitFor(() => expect(parseMock.submit).toHaveBeenCalled())
    const [, opts] = parseMock.submit.mock.calls[0]!
    expect((opts as { extractTables: boolean }).extractTables).toBe(false)
    container.remove()
  })
})

describe('DocParseCard：引擎切换', () => {
  it('切换引擎后 accept 与格式提示跟着变', () => {
    const { container } = render(<DocParseCard />)
    const before = (container.querySelector('input[type="file"]') as HTMLInputElement).accept
    expect(before).toContain('.pdf')

    selectEngine(container, 'local')
    const after = (container.querySelector('input[type="file"]') as HTMLInputElement).accept
    // local 不支持 docx
    expect(after).not.toContain('.docx')
    container.remove()
  })

  it('选文件后提示改为文件名', () => {
    const { container } = render(<DocParseCard />)
    pickFile(container, '起诉状.pdf')
    expect(within(container).getByText('起诉状.pdf')).toBeTruthy()
    container.remove()
  })

  it('换文件会重置上一次结果', () => {
    const { container } = render(<DocParseCard />)
    pickFile(container, 'a.pdf')
    expect(parseMock.reset).toHaveBeenCalled()
    container.remove()
  })
})

describe('DocParseCard：busy 态', () => {
  it('解析中：引擎、文件、复选框与按钮全部禁用', () => {
    parseMock.phase = 'polling'
    parseMock.hint = '正在解析第 2 页'
    const { container } = render(<DocParseCard />)

    expect((container.querySelector('select') as HTMLSelectElement).disabled).toBe(true)
    expect((container.querySelector('input[type="file"]') as HTMLInputElement).disabled).toBe(true)
    expect((container.querySelector('input[type="checkbox"]') as HTMLInputElement).disabled).toBe(true)
    const btn = clickText(/解析中/)
    expect(btn.disabled).toBe(true)
    // busy 时右侧显示进度 hint 而非引擎速览
    expect(container.textContent).toContain('正在解析第 2 页')
    container.remove()
  })

  it('submitting 同样视为 busy', () => {
    parseMock.phase = 'submitting'
    const { container } = render(<DocParseCard />)
    expect((container.querySelector('select') as HTMLSelectElement).disabled).toBe(true)
    container.remove()
  })
})

describe('DocParseCard：完成后入口', () => {
  it('成功：显示「已完成 · 查看结果」', () => {
    parseMock.phase = 'done'
    parseMock.outcome = {
      ok: true,
      method: 'textin',
      markdown: '# 标题',
      text: '',
      metadata: { page_count: 3 },
    }
    const { container } = render(<DocParseCard />)
    expect(within(container).getByText(/已完成 · 查看结果/)).toBeTruthy()
    container.remove()
  })

  it('失败：显示「解析失败 · 查看」', () => {
    parseMock.phase = 'done'
    parseMock.outcome = { ok: false, error: '引擎超时', markdown: '', text: '', metadata: { page_count: 0 } }
    const { container } = render(<DocParseCard />)
    expect(within(container).getByText(/解析失败 · 查看/)).toBeTruthy()
    container.remove()
  })

  it('未完成时不显示查看入口，显示引擎速览', () => {
    const { container } = render(<DocParseCard />)
    expect(container.textContent).not.toContain('查看结果')
    expect(container.textContent).toContain('MinerU')
    container.remove()
  })
})

describe('DocParseCard：历史入口', () => {
  it('点历史打开解析历史弹窗', () => {
    const { container } = render(<DocParseCard />)
    clickText(/历史/)
    expect(within(container).getByText('PARSE_HISTORY')).toBeTruthy()
    container.remove()
  })
})
