import { describe, expect, it } from 'vitest'

import {
  validateAttachmentFile,
  formatFileSize,
  estimateTokens,
  historyToMessages,
  parseSseEvent,
  previewToolArgs,
  describeLocation,
  groupSessions,
  splitBizHintLine,
  splitPageHintLine,
  buildSelectionQuoteBlock,
  normalizeSelectionText,
  parseFileRewrite,
  extractRewriteArgs,
  splitQuoteBlock,
  splitRefBlocks,
  shortToolName,
  takeSseFrames,
  tokensPerSecond,
  buildSlashMenuItems,
  filterSlashMenuItems,
  slashMenuQuery,
} from './domain'
import type { AgentHistoryMessage, AgentSession } from './types'

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

  it('splitBizHintLine：拆出业务归属锚点（context 模式每轮注入），与页面锚点可叠加解析', () => {
    expect(splitBizHintLine('[当前业务：本委托「某银行」 contract_id=8]\n梳理材料')).toEqual({
      bizHint: '本委托「某银行」 contract_id=8',
      body: '梳理材料',
    })
    expect(splitBizHintLine('普通消息')).toEqual({ bizHint: null, body: '普通消息' })
    expect(splitBizHintLine('前言行\n[当前业务：x]').bizHint).toBeNull()
  })

  it('groupSessions：按业务范围分组（案件/合同取 scope_name，任务与通用兜底组），组间按最新排序', () => {
    const mk = (o: Partial<AgentSession> & Pick<AgentSession, 'session_id' | 'updated_at'>): AgentSession => ({
      title: o.session_id,
      llm_model: '',
      created_at: o.updated_at,
      ...o,
    } as AgentSession)
    const groups = groupSessions([
      mk({ session_id: 'chat-1', updated_at: '2026-10-23T10:00:00' }),
      mk({ session_id: 'c-1', updated_at: '2026-10-23T12:00:00', origin: 'contract', contract_id: 390, scope_name: '贵州某公司' }),
      mk({ session_id: 'c-2', updated_at: '2026-10-23T11:00:00', origin: 'contract', contract_id: 390, scope_name: '贵州某公司' }),
      mk({ session_id: 'k-1', updated_at: '2026-10-23T09:00:00', origin: 'case', case_id: 217, scope_name: '' }),
      mk({ session_id: 't-1', updated_at: '2026-10-23T08:00:00', origin: 'task' }),
    ])
    expect(groups.map((g) => g.key)).toEqual(['contract:390', 'chat', 'case:217', 'task'])
    const [contractGroup, , caseGroup, taskGroup] = groups
    expect(contractGroup).toMatchObject({ kind: 'contract', label: '贵州某公司' })
    expect(contractGroup?.sessions.map((s) => s.session_id)).toEqual(['c-1', 'c-2'])
    // scope_name 缺失回退「案件 #id」
    expect(caseGroup?.label).toBe('案件 #217')
    expect(taskGroup).toMatchObject({ kind: 'task', label: '后台任务' })
  })

  it('describeLocation：路由 → 页面描述（详情页由页面自己覆盖精确值）', () => {
    expect(describeLocation('/')).toBe('工作台首页')
    expect(describeLocation('/projects')).toBe('办案列表页')
    expect(describeLocation('/projects/386')).toBe('委托详情页')
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

// ── `/` 命令菜单纯函数 ──────────────────────────────────────────────────────

describe('slash 菜单（build/filter/query）', () => {
  const skills = [
    { name: 'web-research', description: '联网搜索', enabled: true },
    { name: 'deadline-queries', description: '期限查询', enabled: true },
    { name: 'off-skill', description: '已停用', enabled: false },
  ]

  it('构建：命令在前、技能只列启用的；无会话时 compact 禁用', () => {
    const items = buildSlashMenuItems(skills, false)
    expect(items[0]?.kind).toBe('command')
    expect(items[0]?.disabled).toBe(true)
    expect(items[0]?.disabledHint).toBe('先开始对话')
    expect(items.filter((i) => i.kind === 'skill').map((i) => i.id)).toEqual(['web-research', 'deadline-queries'])
    expect(buildSlashMenuItems(skills, true)[0]?.disabled).toBeUndefined()
  })

  it('过滤：子串匹配名与描述；skill: 前缀只挑技能', () => {
    const items = buildSlashMenuItems(skills, true)
    // 「期限」同时命中 deadline-queries 的描述与 compact 的描述（保留…期限等锚点）
    expect(filterSlashMenuItems(items, '期限').map((i) => i.id)).toEqual(['compact', 'deadline-queries'])
    expect(filterSlashMenuItems(items, 'web').map((i) => i.id)).toEqual(['web-research'])
    expect(filterSlashMenuItems(items, 'skill:dead').map((i) => i.id)).toEqual(['deadline-queries'])
    expect(filterSlashMenuItems(items, 'skill:')).toHaveLength(2)
    expect(filterSlashMenuItems(items, '不存在的词')).toEqual([])
  })

  it('触发条件：/ 打头才弹、多行/普通文本不弹', () => {
    expect(slashMenuQuery('/')).toBe('')
    expect(slashMenuQuery('/dead')).toBe('dead')
    expect(slashMenuQuery('你好')).toBeNull()
    expect(slashMenuQuery('/第一行\n第二行')).toBeNull()
  })
})


describe('框选引用块（豆包式引用）', () => {
  const quote = {
    kind: 'contract' as const,
    ownerId: 393,
    subpath: '1-律师资料/1-合同/专项合同.docx',
    name: '专项合同.docx',
    text: '甲方拟就与对方拖欠货款之事宜，委托乙方提供专项法律服务。',
  }

  it('构建与拆解严格互逆（round-trip）', () => {
    const block = buildSelectionQuoteBlock(quote)
    const { quote: parsed, body } = splitQuoteBlock(`请解释这段。\n${block}`)
    // 引用块不在首行也要能拆出来（与 refs 同口径的逐行扫描）
    expect(parsed?.text).toBe(quote.text)
    expect(parsed?.kind).toBe('contract')
    expect(parsed?.ownerId).toBe(393)
    expect(parsed?.subpath).toBe(quote.subpath)
    expect(body).toBe('请解释这段。')
  })

  it('引号被归一成全角，不会破坏块的闭引号', () => {
    const q = { ...quote, text: '他说"不合格"应更换' }
    const block = buildSelectionQuoteBlock(q)
    const { quote: parsed } = splitQuoteBlock(block)
    expect(parsed?.text).toBe('他说”不合格”应更换')
  })

  it('换行归一为空格、超长截断（400 + 省略号）', () => {
    expect(normalizeSelectionText('第一行\n  第二行')).toBe('第一行 第二行')
    const long = '甲'.repeat(500)
    expect(normalizeSelectionText(long)).toHaveLength(402)
    expect(normalizeSelectionText(long).endsWith('……')).toBe(true)
  })

  it('无引用块的消息原样返回（quote=null）', () => {
    const { quote: q, body } = splitQuoteBlock('普通消息正文')
    expect(q).toBeNull()
    expect(body).toBe('普通消息正文')
  })

  it('历史回放：quote 从块还原到消息字段、正文不残留块文本', () => {
    const rows = [
      {
        message_id: 1,
        role: 'user' as const,
        content: `[当前业务：本委托「测试」 contract_id=393]\n${buildSelectionQuoteBlock(quote)}\n这段条款什么意思？`,
      },
    ]
    const m = historyToMessages(rows as never)[0]
    expect(m?.quote?.text).toBe(quote.text)
    expect(m?.content).toBe('这段条款什么意思？')
    expect(m?.bizHint).toContain('测试')
  })
})


describe('AI 改写落盘信号（parseFileRewrite）', () => {
  /** 线上真实回包形状（AgentMessage 实测）：pretty JSON + mcp 前缀工具名 */
  const applied = JSON.stringify({
    applied: true,
    contract_id: 393,
    subpath: '1-律师资料/1-合同/专项合同.docx',
    name: '专项合同.docx',
    reason: '',
  })

  it('识别 mcp__fachuan__rewrite_folder_file 的成功结果（含 contract_id）', () => {
    const r = parseFileRewrite('mcp__fachuan__rewrite_folder_file', applied)
    expect(r).toEqual({ contractId: 393, subpath: '1-律师资料/1-合同/专项合同.docx', name: '专项合同.docx' })
  })

  it('applied=false（定位失败）不是落盘信号', () => {
    const failed = JSON.stringify({ applied: false, contract_id: 393, subpath: 'x.docx', name: 'x.docx', reason: '找不到了' })
    expect(parseFileRewrite('mcp__fachuan__rewrite_folder_file', failed)).toBeNull()
  })

  it('is_error / 其它工具 / 坏 JSON / 缺 contract_id 一律 null（宁可不刷新）', () => {
    expect(parseFileRewrite('mcp__fachuan__rewrite_folder_file', applied, true)).toBeNull()
    expect(parseFileRewrite('mcp__fachuan__read_folder_file', applied)).toBeNull()
    expect(parseFileRewrite('mcp__fachuan__rewrite_folder_file', '{"applied": true, "subpath":')).toBeNull()
    // 旧后端没有 contract_id 字段：没有定向刷新的依据，宁可不动
    expect(parseFileRewrite('mcp__fachuan__rewrite_folder_file', '{"applied": true, "subpath": "a.docx"}')).toBeNull()
    expect(parseFileRewrite(undefined, applied)).toBeNull()
  })

  it('带调用参数时透传 original/replacement（画布内就地落修订用）', () => {
    const r = parseFileRewrite('mcp__fachuan__rewrite_folder_file', applied, false, {
      original: '甲方拟就与对方之事宜',
      replacement: '鉴于甲方因经营调整拟停止生产经营',
    })
    expect(r).toMatchObject({
      contractId: 393,
      original: '甲方拟就与对方之事宜',
      replacement: '鉴于甲方因经营调整拟停止生产经营',
    })
  })

  it('缺参数时信号仍然有效（只是退回换 key 重载）', () => {
    const r = parseFileRewrite('mcp__fachuan__rewrite_folder_file', applied)
    expect(r?.original).toBeUndefined()
    expect(r?.replacement).toBeUndefined()
  })
})

describe('rewrite 调用参数提取（extractRewriteArgs）', () => {
  it('对象与 JSON 字符串两种形状都能取到原文/改写全文', () => {
    const args = { original: '原文段落', replacement: '改写段落' }
    expect(extractRewriteArgs(args)).toEqual(args)
    expect(extractRewriteArgs(JSON.stringify(args))).toEqual(args)
  })

  it('形状不对 / 字段缺失 / 空白文本一律 null（宁缺勿错）', () => {
    expect(extractRewriteArgs(undefined)).toBeNull()
    expect(extractRewriteArgs('不是 JSON')).toBeNull()
    expect(extractRewriteArgs({ original: '只有原文' })).toBeNull()
    expect(extractRewriteArgs({ original: '原文', replacement: '   ' })).toBeNull()
    expect(extractRewriteArgs({ original: 1, replacement: 2 })).toBeNull()
  })
})
