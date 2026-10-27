import { describe, expect, it } from 'vitest'

import type { AgentHistoryMessage } from '../types'
import { buildSelectionQuoteBlock } from './reference'
import {
  bizHintFromContext,
  bizHintParts,
  buildBizHintBlock,
  historyToMessages,
  normalizeBizHintTitle,
  splitBizHintLine,
  splitPageHintLine,
  splitRefBlocks,
} from './transcript'

describe('splitRefBlocks（folder-ref 回放）', () => {
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
    expect(splitBizHintLine('[当前业务：本委托“某银行” contract_id=8]\n梳理材料')).toEqual({
      bizHint: { kind: 'contract', title: '某银行', refId: 8 },
      body: '梳理材料',
    })
    expect(splitBizHintLine('[当前业务：本案“某公司诉某银行案” case_id=217]\n梳理材料')).toEqual({
      bizHint: { kind: 'case', title: '某公司诉某银行案', refId: 217 },
      body: '梳理材料',
    })
    expect(splitBizHintLine('普通消息')).toEqual({ bizHint: null, body: '普通消息' })
    // 锚点不在首行不解析（注入永远在开头，防误伤正文里的同款文本）
    expect(splitBizHintLine('前言行\n[当前业务：x]').bizHint).toBeNull()
    // 旧格式（直角引号）不再认：结构与构建侧严格成对，不留两种口径
    expect(splitBizHintLine('[当前业务：本委托「某银行」 contract_id=8]\n问').bizHint).toBeNull()
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

describe('业务归属锚点（出站构建 ↔ 回放解析严格互逆）', () => {
  const contract = { origin: 'contract' as const, refId: 393, title: '示例甲方' }
  const kase = { origin: 'case' as const, refId: 217, title: '某公司诉某银行案' }

  it('buildBizHintBlock：按业务范围选单位词与 id 键名', () => {
    expect(buildBizHintBlock(contract, '梳理材料')).toBe('[当前业务：本委托“示例甲方” contract_id=393]\n梳理材料')
    expect(buildBizHintBlock(kase, '梳理材料')).toBe('[当前业务：本案“某公司诉某银行案” case_id=217]\n梳理材料')
  })

  it('round-trip：构建出来的行能解析回同一个结构化锚点，正文不残留', () => {
    for (const ctx of [contract, kase]) {
      const { bizHint, body } = splitBizHintLine(buildBizHintBlock(ctx, '梳理材料'))
      expect(bizHint).toEqual(bizHintFromContext(ctx))
      expect(body).toBe('梳理材料')
    }
  })

  it('标题自带引号（含闭引号）时仍能拆回 id——此前非贪婪匹配会切错位置', () => {
    // 律所习惯写法：合同名常自引号，与书名号混用也要过
    for (const title of ['「示例甲方」专项法律服务合同', '示例甲方“二期”委托', '某公司诉「某银行」案']) {
      const ctx = { ...contract, title }
      const { bizHint, body } = splitBizHintLine(buildBizHintBlock(ctx, '看下边界'))
      // 标题被归一成弯引号，但 id 与业务范围必须完整保住
      expect(bizHint?.refId).toBe(393)
      expect(bizHint?.kind).toBe('contract')
      expect(bizHint?.title).toBe(normalizeBizHintTitle(title))
      expect(body).toBe('看下边界')
    }
  })

  it('标题含换行归成单行（锚点必须一行，否则第二行会被当正文）', () => {
    const { bizHint, body } = splitBizHintLine(buildBizHintBlock({ ...contract, title: '示例甲方\n专项' }, '正文'))
    expect(bizHint?.title).toBe('示例甲方 专项')
    expect(body).toBe('正文')
  })

  it('historyToMessages 与本地发送同一解析：回放结构与出站构建一致（两侧不漂移）', () => {
    const outbound = buildBizHintBlock(contract, '梳理材料')
    const replayed = historyToMessages([
      { message_id: 1, role: 'user', content: outbound, tool_name: '', created_at: '', metadata: {} },
    ])[0]
    const { bizHint } = splitBizHintLine(outbound)
    expect(replayed?.bizHint).toEqual(bizHint)
    expect(replayed?.bizHint).toEqual({ kind: 'contract', title: '示例甲方', refId: 393 })
    expect(replayed?.content).toBe('梳理材料')
  })

  it('展示三段：id 单独成段（不再随整串截断被吃掉）', () => {
    expect(bizHintParts({ kind: 'case', title: '某公司诉某银行案', refId: 217 })).toEqual({
      unit: '本案',
      title: '某公司诉某银行案',
      ref: '#217',
    })
  })
})

describe('historyToMessages（转录映射）', () => {
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

  it('历史回放：quote 从块还原到消息字段、正文不残留块文本', () => {
    const quote = {
      kind: 'contract' as const,
      ownerId: 393,
      subpath: '1-律师资料/1-合同/专项合同.docx',
      name: '专项合同.docx',
      text: '甲方拟就与对方拖欠货款之事宜，委托乙方提供专项法律服务。',
    }
    const rows = [
      {
        message_id: 1,
        role: 'user' as const,
        content: buildBizHintBlock(
          { origin: 'contract', refId: 393, title: '测试' },
          `${buildSelectionQuoteBlock(quote)}\n这段条款什么意思？`,
        ),
      },
    ]
    const m = historyToMessages(rows as never)[0]
    expect(m?.quote?.text).toBe(quote.text)
    expect(m?.content).toBe('这段条款什么意思？')
    expect(m?.bizHint?.title).toBe('测试')
  })
})
