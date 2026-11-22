// @vitest-environment jsdom
/**
 * 导出纯函数单测 + downloadText 的 DOM 行为（唯一触达 DOM 的导出函数）。
 * 其余函数仍只做纯逻辑断言。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ChatMessage } from '../types'
import { downloadText, exportFilename, toMarkdown, toPlainText } from './export'

function message(over: Partial<ChatMessage> & Pick<ChatMessage, 'id' | 'role'>): ChatMessage {
  return { content: '', ...over }
}

const USER = message({ id: 'u1', role: 'user', content: '合同解除的条件是什么？' })

describe('toMarkdown：多答分栏', () => {
  it('同一轮的多条回答各自一个三级标题（agent · 模型）', () => {
    const md = toMarkdown([
      USER,
      message({ id: 'a1', role: 'assistant', agentKind: 'pi', model: 'kimi-2.6', content: 'pi 的回答' }),
      message({ id: 'a2', role: 'assistant', agentKind: 'dsh', model: 'deepseek-v3', content: 'dsh 的回答' }),
    ])
    expect(md).toContain('# 法穿问答')
    expect(md).toContain('## 我：')
    expect(md).toContain('合同解除的条件是什么？')
    expect(md).toContain('### pi · kimi-2.6')
    expect(md).toContain('### dsh · deepseek-v3')
    expect(md.match(/^### /gm)).toHaveLength(2)
  })

  it('未标注 agent / 模型时按 pi 且只写 agent', () => {
    const md = toMarkdown([USER, message({ id: 'a1', role: 'assistant', content: '旧数据的回答' })])
    expect(md).toContain('### pi\n')
  })

  it('综合结论写可读名「综合结论」，不露出内部标识 synthesis', () => {
    const md = toMarkdown([
      USER,
      message({ id: 's1', role: 'assistant', agentKind: 'synthesis', model: 'kimi-2.6', content: '综合稿' }),
    ])
    expect(md).toContain('### 综合结论 · kimi-2.6')
    expect(md).not.toContain('### synthesis')
  })
})

describe('toMarkdown：引用与锚点', () => {
  it('引用卡/业务锚点/页面锚点压成一行 `> 引用：…`', () => {
    const md = toMarkdown([
      message({
        id: 'u1',
        role: 'user',
        content: '请分析这段',
        pageHint: '办案列表页',
        bizHint: { kind: 'case', title: '某公司诉某银行案', refId: 42 },
        refs: [{ kind: 'case', ownerId: 42, subpath: '证据/a.pdf', name: 'a.pdf' }],
        quote: { kind: 'case', ownerId: 42, subpath: '证据/a.pdf', name: 'a.pdf', text: '合同自通知到达对方时解除' },
      }),
    ])
    const refLines = md.split('\n').filter((line) => line.startsWith('> 引用：'))
    expect(refLines).toHaveLength(1)
    expect(refLines[0]).toContain('本案“某公司诉某银行案” #42')
    expect(refLines[0]).toContain('页面：办案列表页')
    expect(refLines[0]).toContain('文件：a.pdf')
    expect(refLines[0]).toContain('选段：a.pdf「合同自通知到达对方时解除」')
  })
})

describe('toMarkdown：工具默认不导出', () => {
  const tool = message({ id: 't1', role: 'tool', toolName: 'read_file', content: '第一行结果\n第二行结果' })

  it('默认既不出现在独立工具消息，也不出现在回答挂载的工具里', () => {
    const md = toMarkdown([USER, tool, message({ id: 'a1', role: 'assistant', content: '回答', tools: [tool] })])
    expect(md).not.toContain('🔧')
    expect(md).not.toContain('read_file')
  })

  it('includeTools 时按「- 🔧 工具名：结果首行」导出', () => {
    const md = toMarkdown([USER, tool, message({ id: 'a1', role: 'assistant', content: '回答', tools: [tool] })], {
      includeTools: true,
    })
    expect(md.match(/- 🔧 read_file：第一行结果/g)).toHaveLength(2)
    expect(md).not.toContain('第二行结果')
  })
})

describe('toMarkdown：异常回答', () => {
  it('truncated 的回答追加中断提示', () => {
    const md = toMarkdown([USER, message({ id: 'a1', role: 'assistant', content: '说了半句', truncated: true })])
    expect(md).toContain('> （本条被中断，内容可能不完整）')
  })

  it('跳过 failed 空回答（不留空标题）', () => {
    const md = toMarkdown([
      USER,
      message({ id: 'a1', role: 'assistant', agentKind: 'dsh', failed: true, content: '' }),
      message({ id: 'a2', role: 'assistant', agentKind: 'pi', content: '另一栏的回答' }),
    ])
    expect(md).not.toContain('### dsh')
    expect(md).toContain('### pi')
    expect(md).toContain('另一栏的回答')
  })

  it('thinking 默认不导出，includeThinking 时以引用块出现', () => {
    const answer = message({ id: 'a1', role: 'assistant', content: '结论', thinking: '先看条款\n再下结论' })
    expect(toMarkdown([USER, answer])).not.toContain('先看条款')
    expect(toMarkdown([USER, answer], { includeThinking: true })).toContain('> 思考：先看条款\n> 再下结论')
  })
})

describe('toPlainText', () => {
  it('去掉 Markdown 标题包装，保留正文与中断提示', () => {
    const text = toPlainText([
      USER,
      message({ id: 'a1', role: 'assistant', agentKind: 'pi', model: 'kimi-2.6', content: '正文', truncated: true }),
    ])
    expect(text).not.toContain('#')
    expect(text).toContain('法穿问答')
    expect(text).toContain('我：')
    expect(text).toContain('pi · kimi-2.6')
    expect(text).toContain('正文')
    expect(text).toContain('（本条被中断，内容可能不完整）')
  })
})

describe('exportFilename', () => {
  it('法穿问答-YYYY-MM-DD-HHmm.md（本地时区、补零）', () => {
    const now = new Date(2026, 10, 20, 9, 30).getTime()
    expect(exportFilename([], now)).toBe('法穿问答-2026-11-20-0930.md')
  })
})

describe('downloadText', () => {
  let createObjectURL: ReturnType<typeof vi.fn>
  let revokeObjectURL: ReturnType<typeof vi.fn>
  let clicked: Array<{ download: string; href: string; inDomAtClick: boolean }>

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
    delete (URL as unknown as Record<string, unknown>).createObjectURL
    delete (URL as unknown as Record<string, unknown>).revokeObjectURL
  })

  it('Blob MIME + `<a download>`，并在 finally 延到宏任务回收 URL', () => {
    vi.useFakeTimers()
    createObjectURL = vi.fn(() => 'blob:export-0')
    revokeObjectURL = vi.fn()
    URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL
    clicked = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({
        download: this.download,
        href: this.getAttribute('href') ?? '',
        inDomAtClick: document.body.contains(this),
      })
    })

    downloadText('法穿问答.md', '# 标题', 'text/markdown;charset=utf-8')

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    const blob = createObjectURL.mock.calls[0]![0] as Blob
    expect(blob.type).toBe('text/markdown;charset=utf-8')
    expect(clicked).toEqual([{ download: '法穿问答.md', href: 'blob:export-0', inDomAtClick: true }])
    // 临时锚点用完即摘
    expect(document.querySelector('a[download]')).toBeNull()
    // 同步 revoke 会让 Firefox 下到空文件，必须延到下一个宏任务
    expect(revokeObjectURL).not.toHaveBeenCalled()
    vi.runAllTimers()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:export-0')
  })
})
