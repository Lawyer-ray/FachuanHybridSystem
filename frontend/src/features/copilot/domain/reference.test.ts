import { describe, expect, it } from 'vitest'

import {
  buildSelectionQuoteBlock,
  defaultOutgoingPrompt,
  extractRewriteArgs,
  normalizeSelectionText,
  parseFileRewrite,
  shortToolName,
} from './reference'
import { splitQuoteBlock } from './transcript'

describe('引用与改写信号：展示归一', () => {
  it('shortToolName 去掉 mcp 前缀，空名兜底', () => {
    expect(shortToolName('mcp__fachuan__delete_case')).toBe('delete_case')
    expect(shortToolName('list_cases')).toBe('list_cases')
    expect(shortToolName(undefined)).toBe('工具')
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
})

describe('默认出站提示语（defaultOutgoingPrompt）', () => {
  const quote = { kind: 'contract' as const, ownerId: 1, subpath: 'a.docx', name: 'a.docx', text: '选段' }
  const fileRef = { kind: 'contract' as const, ownerId: 1, subpath: 'a.docx', name: 'a.docx' }
  const folderRef = { ...fileRef, isFolder: true }

  it('按「引用了什么」选措辞：目录 / 文件 / 附件 / 选段依次兜底', () => {
    expect(defaultOutgoingPrompt([folderRef], 0, null)).toBe('请浏览我引用的目录并梳理其中的材料。')
    expect(defaultOutgoingPrompt([fileRef], 0, null)).toBe('请分析我引用的文件。')
    expect(defaultOutgoingPrompt([], 1, null)).toBe('请分析我上传的附件。')
    expect(defaultOutgoingPrompt([], 0, quote)).toBe('请结合原文件，分析我引用的这段内容。')
  })

  it('目录与文件混引按「有文件」处理；什么都没有则空串', () => {
    expect(defaultOutgoingPrompt([folderRef, fileRef], 0, null)).toBe('请分析我引用的文件。')
    expect(defaultOutgoingPrompt([], 0, null)).toBe('')
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
    expect(r).toEqual({
      kind: 'contract',
      ownerId: 393,
      subpath: '1-律师资料/1-合同/专项合同.docx',
      name: '专项合同.docx',
    })
  })

  it('案件直改回包（case_id）同样识别，kind=case', () => {
    const caseApplied = JSON.stringify({
      applied: true,
      contract_id: 0,
      case_id: 399,
      subpath: '2-诉状/起诉状.docx',
      name: '起诉状.docx',
      reason: '',
    })
    const r = parseFileRewrite('mcp__fachuan__rewrite_folder_file', caseApplied)
    expect(r).toEqual({
      kind: 'case',
      ownerId: 399,
      subpath: '2-诉状/起诉状.docx',
      name: '起诉状.docx',
    })
  })

  it('applied=false（定位失败）不是落盘信号', () => {
    const failed = JSON.stringify({ applied: false, contract_id: 393, subpath: 'x.docx', name: 'x.docx', reason: '找不到了' })
    expect(parseFileRewrite('mcp__fachuan__rewrite_folder_file', failed)).toBeNull()
  })

  it('is_error / 其它工具 / 坏 JSON / 缺归属 id 一律 null（宁可不刷新）', () => {
    expect(parseFileRewrite('mcp__fachuan__rewrite_folder_file', applied, true)).toBeNull()
    expect(parseFileRewrite('mcp__fachuan__read_folder_file', applied)).toBeNull()
    expect(parseFileRewrite('mcp__fachuan__rewrite_folder_file', '{"applied": true, "subpath":')).toBeNull()
    // 旧后端没有归属 id 字段：没有定向刷新的依据，宁可不动
    expect(parseFileRewrite('mcp__fachuan__rewrite_folder_file', '{"applied": true, "subpath": "a.docx"}')).toBeNull()
    expect(parseFileRewrite(undefined, applied)).toBeNull()
  })

  it('带调用参数时透传 original/replacement（画布内就地落修订用）', () => {
    const r = parseFileRewrite('mcp__fachuan__rewrite_folder_file', applied, false, {
      original: '甲方拟就与对方之事宜',
      replacement: '鉴于甲方因经营调整拟停止生产经营',
    })
    expect(r).toMatchObject({
      kind: 'contract',
      ownerId: 393,
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
