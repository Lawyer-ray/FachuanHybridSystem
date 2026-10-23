import { describe, expect, it } from 'vitest'

import {
  validateAttachmentFile,
  formatFileSize,
  estimateTokens,
  historyToMessages,
  parseSseEvent,
  previewToolArgs,
  describeLocation,
  splitPageHintLine,
  splitRefBlocks,
  shortToolName,
  takeSseFrames,
  tokensPerSecond,
} from './domain'
import type { AgentHistoryMessage } from './types'

describe('takeSseFrames', () => {
  it('完整帧切出、半截留作 rest', () => {
    const { frames, rest } = takeSseFrames('data: {"type":"meta"}\n\ndata: {"type":"del')
    expect(frames).toEqual(['data: {"type":"meta"}'])
    expect(rest).toBe('data: {"type":"del')
  })

  it('跨 chunk 拼回后半截变完整帧', () => {
    const first = takeSseFrames('data: {"type":"a')
    const merged = first.rest + 'ta"}\n\n'
    const { frames, rest } = takeSseFrames(merged)
    expect(frames).toEqual(['data: {"type":"ata"}'])
    expect(rest).toBe('')
  })

  it('多帧一次取出（真机线上格式）', () => {
    const wire = 'data: {"type": "delta", "content": "你好"}\n\ndata: {"type": "done"}\n\n'
    const { frames, rest } = takeSseFrames(wire)
    expect(frames).toHaveLength(2)
    expect(rest).toBe('')
  })

  it('帧尾容忍 CR（行尾为 CRLF 的帧也能解析；后端实际只发 LF）', () => {
    const { frames } = takeSseFrames('data: {"type":"done"}\r\n\n')
    expect(frames).toEqual(['data: {"type":"done"}\r'])
    expect(parseSseEvent(frames[0] ?? '')).toEqual({ type: 'done' })
  })
})

describe('parseSseEvent', () => {
  it('解析 data 帧为事件对象', () => {
    expect(parseSseEvent('data: {"type":"delta","content":"A"}')).toEqual({ type: 'delta', content: 'A' })
  })

  it('坏 JSON / 无 data 前缀 / 缺 type 字段一律返回 null', () => {
    expect(parseSseEvent('data: {oops')).toBeNull()
    expect(parseSseEvent('event: ping\nid: 1')).toBeNull()
    expect(parseSseEvent('data: "纯字符串"')).toBeNull()
  })
})

describe('historyToMessages', () => {
  const rows: AgentHistoryMessage[] = [
    { message_id: 1, role: 'user', content: '问', tool_name: '', created_at: '', metadata: {} },
    { message_id: 2, role: 'assistant', content: '答', tool_name: '', created_at: '', metadata: { truncated: true } },
    { message_id: 3, role: 'tool', content: 'x'.repeat(3000), tool_name: 'mcp__fachuan__list_cases', created_at: '', metadata: {} },
  ]

  it('role/content 映射 + truncated 透传', () => {
    const messages = historyToMessages(rows)
    expect(messages.map((m) => m.role)).toEqual(['user', 'assistant', 'tool'])
    expect(messages[1]?.truncated).toBe(true)
    expect(messages[0]?.truncated).toBeUndefined()
  })

  it('工具结果预览截到 2000 字符', () => {
    expect(historyToMessages(rows)[2]?.content).toHaveLength(2000)
  })
})

describe('展示归一', () => {
  it('shortToolName 去掉 mcp 前缀，空名兜底', () => {
    expect(shortToolName('mcp__fachuan__delete_case')).toBe('delete_case')
    expect(shortToolName('list_cases')).toBe('list_cases')
    expect(shortToolName(undefined)).toBe('工具')
  })

  it('previewToolArgs 空对象为空串、超长截断', () => {
    expect(previewToolArgs({})).toBe('')
    expect(previewToolArgs({ a: 1 })).toBe('{"a":1}')
    expect(previewToolArgs({ k: 'x'.repeat(200) }, 50).endsWith('…')).toBe(true)
  })
})

describe('输出速度估算', () => {
  it('estimateTokens：CJK 约 0.7/字，ASCII 约 4 字符/token', () => {
    expect(estimateTokens('你好')).toBe(1) // 2 字 × 0.7 = 1.4 → 1
    expect(estimateTokens('abcdefgh')).toBe(2) // 8/4
    expect(estimateTokens('你好abcdefgh')).toBe(3) // 1.4 + 2 ≈ 3
    expect(estimateTokens('')).toBe(0)
  })

  it('tokensPerSecond：滑动窗口内按采样斜率计算', () => {
    const now = 10_000
    const samples: Array<[number, number]> = [
      [now - 3000, 0],
      [now - 2000, 10],
      [now - 1000, 20],
      [now, 30],
    ]
    // 窗口起点取第一个 >= now-2000 的采样（10 tokens），2 秒 +20
    expect(tokensPerSecond(samples, now)).toBeCloseTo(10, 5)
  })

  it('样本不足或时间倒挂时为 0', () => {
    expect(tokensPerSecond([], Date.now())).toBe(0)
    expect(tokensPerSecond([[1000, 5]], Date.now())).toBe(0)
  })
})

describe('附件预检（P1-11）', () => {
  it('validateAttachmentFile：白名单/限额/空文件', () => {
    expect(validateAttachmentFile({ name: '合同.PDF', size: 100 })).toBeNull()
    expect(validateAttachmentFile({ name: '图.JPG', size: 100 })).toBeNull()
    expect(validateAttachmentFile({ name: 'a.exe', size: 1 })).toContain('不支持的格式')
    expect(validateAttachmentFile({ name: 'a.txt', size: 21 * 1024 * 1024 })).toContain('20MB')
    expect(validateAttachmentFile({ name: 'a.txt', size: 0 })).toContain('文件为空')
  })

  it('formatFileSize：B/KB/MB', () => {
    expect(formatFileSize(500)).toBe('500B')
    expect(formatFileSize(2048)).toBe('2KB')
    expect(formatFileSize(3 * 1024 * 1024)).toBe('3.0MB')
  })
})

describe('引用块拆分（folder-ref 回放）', () => {
  const REF = '[已引用文件：委托合同.docx (attachment_id=a1b2c3d4-0000-0000-0000-000000000000, contract_id=8, subpath="1-一审/起诉状.pdf")]'

  it('纯引用消息：refs 解析出来，body 剩空串', () => {
    const { refs, body } = splitRefBlocks(REF)
    expect(refs).toEqual([{ name: '委托合同.docx', kind: 'contract', ownerId: 8, subpath: '1-一审/起诉状.pdf' }])
    expect(body).toBe('')
  })

  it('引用 + 正文混合：引用行剔除、正文换行结构保留', () => {
    const REF2 = '[已引用文件：判决书.pdf (attachment_id=b2c3d4e5-0000-0000-0000-000000000001, contract_id=9, subpath="判决书.pdf")]'
    const { refs, body } = splitRefBlocks(`${REF}\n请对比这两份文件的关键条款。\n${REF2}`)
    expect(refs).toHaveLength(2)
    expect(body).toBe('请对比这两份文件的关键条款。')
  })

  it('无引用消息原样返回（body 不动、refs 为空）', () => {
    const content = '普通提问\n[已引用文件：长得像但不是]'
    const { refs, body } = splitRefBlocks(content)
    expect(refs).toEqual([])
    expect(body).toBe(content)
  })

  it('historyToMessages：user 行引用重放为 refs、assistant 行不受影响', () => {
    const rows: AgentHistoryMessage[] = [
      { message_id: 1, role: 'user', content: `${REF}\n帮我审一遍`, tool_name: '', created_at: '', metadata: {} },
      { message_id: 2, role: 'assistant', content: REF, tool_name: '', created_at: '', metadata: {} },
    ]
    const msgs = historyToMessages(rows)
    expect(msgs[0]).toMatchObject({ refs: [{ kind: 'contract', ownerId: 8 }] })
    expect(msgs[0]!.content).toBe('帮我审一遍')
    expect(msgs[1]!.refs).toBeUndefined()
    expect(msgs[1]!.content).toBe(REF)
  })
})

describe('页面锚点（通用助手页面感知）', () => {
  it('splitPageHintLine：拆出首行锚点、正文保留；无锚点原样返回', () => {
    expect(splitPageHintLine('[当前页面：办案列表页]\n这个页面有什么功能')).toEqual({
      pageHint: '办案列表页',
      body: '这个页面有什么功能',
    })
    expect(splitPageHintLine('普通消息')).toEqual({ pageHint: null, body: '普通消息' })
    // 锚点不在首行不解析（注入永远在开头，防误伤正文里的同款文本）
    expect(splitPageHintLine('前言行\n[当前页面：x]').pageHint).toBeNull()
  })

  it('describeLocation：路由 → 页面描述（详情页由页面自己覆盖精确值）', () => {
    expect(describeLocation('/')).toBe('工作台首页')
    expect(describeLocation('/cases')).toBe('办案列表页')
    expect(describeLocation('/cases/386')).toBe('委托详情页')
    expect(describeLocation('/material-prep')).toBe('材料预处理台')
  })

  it('historyToMessages：user 行锚点折叠为 pageHint、不进正文', () => {
    const rows: AgentHistoryMessage[] = [
      { message_id: 1, role: 'user', content: '[当前页面：委托详情 · 某银行（contract_id=8）]\n总结一下', tool_name: '', created_at: '', metadata: {} },
    ]
    const msg = historyToMessages(rows)[0]!
    expect(msg.pageHint).toBe('委托详情 · 某银行（contract_id=8）')
    expect(msg.content).toBe('总结一下')
  })
})

describe('引用块解析（kind 与目录）', () => {
  it('案件文件引用块：case_id → kind=case', () => {
    const { refs } = splitRefBlocks('[已引用文件：微信记录.txt (attachment_id=c3d4e5f6-0000-0000-0000-000000000002, case_id=99, subpath="证据/微信记录.txt")]')
    expect(refs[0]).toMatchObject({ kind: 'case', ownerId: 99, subpath: '证据/微信记录.txt', isFolder: undefined })
  })

  it('目录引用块：无 attachment_id、isFolder=true（contract 与 case）', () => {
    const { refs } = splitRefBlocks(
      '[已引用目录：1-一审 (contract_id=8, subpath="1-一审")]\n[已引用目录：证据 (case_id=99, subpath="证据")]',
    )
    expect(refs).toHaveLength(2)
    expect(refs[0]).toMatchObject({ kind: 'contract', ownerId: 8, subpath: '1-一审', isFolder: true })
    expect(refs[1]).toMatchObject({ kind: 'case', ownerId: 99, subpath: '证据', isFolder: true })
  })
})
