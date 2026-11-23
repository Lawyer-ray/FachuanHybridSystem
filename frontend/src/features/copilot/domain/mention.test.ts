/**
 * `@` 引用的纯函数测试（node 环境，无 DOM）。
 *
 * 重点在三处「只在真实使用中才炸」的边界：
 * 1. **识别**：邮箱/网址里的 `@` `/` 不能弹菜单；中文标点后必须能弹；token 不跨空白。
 * 2. **过滤**：只在 label 上匹配（菜单只有一个共享高亮，副标题命中会把无关行顶上来，
 *    Enter 就引用错对象）。
 * 3. **出站协议**：`mentionRefBlock` 与 `transcript.ts` 的 `SENT_REF_RE` 必须互逆
 *    ——这是「历史 chip 与实时 chip 长得一样」的唯一保证，故这里直接喂给
 *    `splitRefBlocks` 反向解析。
 */
import { describe, expect, it } from 'vitest'

import {
  applyMention,
  detectMentionToken,
  filterMentionCandidates,
  flattenMentionOptions,
  makeMentionInsert,
  mentionOptionId,
  mentionRefBlock,
  mentionTokenAt,
  mentionTokenSignature,
  moveMentionHighlight,
  type MentionCandidate,
} from './mention'
import { splitRefBlocks } from './transcript'

const at = (text: string) => detectMentionToken(text, text.length)

describe('detectMentionToken：谁该触发', () => {
  it('草稿开头的 @ 立即开火，query 为空', () => {
    expect(at('@')).toEqual({ trigger: '@', query: '', start: 0, end: 1 })
  })

  it('空白后与中文标点后开火（律师写「结合，@起诉状」这种句子）', () => {
    expect(at('结合 @起诉')).toEqual({ trigger: '@', query: '起诉', start: 3, end: 6 })
    expect(at('见上文，@合同')).toEqual({ trigger: '@', query: '合同', start: 4, end: 7 })
    expect(at('（@案件')).toEqual({ trigger: '@', query: '案件', start: 1, end: 4 })
  })

  it('邮箱里的 @ 不触发（词中间出现的 @ 是正文，不是引用）', () => {
    // 用占位而非真实邮箱字面量：隐私闸门会拦形似邮箱的串，而这里要测的是
    // 「@ 前面是字母数字时不触发」这条边界，与具体域名无关。
    expect(at('abc@def')).toBeNull()
    expect(at('联系 lvshi@example')).toBeNull()
  })

  it('网址里的 / 不触发：https:// 后、协议冒号后、路径中的斜杠都不算命令', () => {
    expect(at('https://example.com/a')).toBeNull()
    expect(at('https:/x')).toBeNull()
    // 双斜杠的第二个：整串 `//` 不是命令
    expect(detectMentionToken('//', 2)).toBeNull()
  })

  it('token 不跨空白：打空格即结束查询', () => {
    expect(detectMentionToken('@起诉 状', 5)).toBeNull()
  })

  it('光标在 token 中间时 end 等于光标（后续文字不算查询词）', () => {
    expect(detectMentionToken('@起诉状', 3)).toEqual({ trigger: '@', query: '起诉', start: 0, end: 3 })
  })

  it('/ 命令同样被识别（同一检测器）', () => {
    expect(at('/compact')).toEqual({ trigger: '/', query: 'compact', start: 0, end: 8 })
  })

  it('越界光标返回 null（粘贴/程序化设置 selectionStart 的野值）', () => {
    expect(detectMentionToken('@x', -1)).toBeNull()
    expect(detectMentionToken('@x', 99)).toBeNull()
  })

  it('没有触发字符时返回 null', () => {
    expect(at('起诉状')).toBeNull()
    expect(at('')).toBeNull()
  })
})

describe('mentionTokenAt：菜单只认 @', () => {
  it('`@` token 原样返回', () => {
    expect(mentionTokenAt('结合 @起诉', 6)).toEqual({ trigger: '@', query: '起诉', start: 3, end: 6 })
  })

  it('`/` token 不放行（命令菜单自带禁用项语义，仍归 use-slash-menu）', () => {
    expect(mentionTokenAt('/compact', 8)).toBeNull()
  })

  it('没有 token 时返回 null', () => {
    expect(mentionTokenAt('起诉状', 3)).toBeNull()
  })
})

describe('mentionTokenSignature：Esc 只否掉当前这一个 token', () => {
  it('同起点同查询词的签名相同（不改字就不重开）', () => {
    const a = mentionTokenSignature({ trigger: '@', query: '起诉', start: 3, end: 6 })
    const b = mentionTokenSignature({ trigger: '@', query: '起诉', start: 3, end: 8 })
    expect(a).toBe(b)
    expect(a).toBe('3:起诉')
  })

  it('改字或挪起点都会换签名（菜单重新自动弹出）', () => {
    expect(mentionTokenSignature({ trigger: '@', query: '起诉', start: 3, end: 6 })).not.toBe(
      mentionTokenSignature({ trigger: '@', query: '起诉状', start: 3, end: 7 }),
    )
    expect(mentionTokenSignature({ trigger: '@', query: '起诉', start: 4, end: 7 })).not.toBe('3:起诉')
  })

  it('无 token 时签名为 null（与空查询词的签名不同）', () => {
    expect(mentionTokenSignature(null)).toBeNull()
    expect(mentionTokenSignature({ trigger: '@', query: '', start: 0, end: 1 })).toBe('0:')
  })
})

describe('filterMentionCandidates：只在 label 上匹配', () => {
  const candidates: MentionCandidate[] = [
    { kind: 'document', label: '起诉状.pdf', sublabel: '2-立案材料' },
    { kind: 'document', label: '借款合同.docx', sublabel: '起诉状 相关' },
    { kind: 'case', label: '张三诉李四', sublabel: '民间借贷纠纷' },
  ]

  it('副标题命中不算命中（否则共享高亮会把无关行顶到第一位）', () => {
    const hits = filterMentionCandidates(candidates, '起诉')
    expect(hits.map((c) => c.label)).toEqual(['起诉状.pdf'])
  })

  it('前缀命中排在包含命中之前（法律场景：打「借贷」先给以借贷开头的那个）', () => {
    const hits = filterMentionCandidates(
      [{ kind: 'case', label: '民间借贷纠纷' }, { kind: 'case', label: '借贷合同争议' }],
      '借贷',
    )
    expect(hits.map((c) => c.label)).toEqual(['借贷合同争议', '民间借贷纠纷'])
  })

  it('大小写不敏感；空查询原序截断', () => {
    expect(filterMentionCandidates([{ kind: 'case', label: 'ABC' }], 'ab')).toHaveLength(1)
    expect(filterMentionCandidates(candidates, '  ', 2)).toHaveLength(2)
  })

  it('limit 生效', () => {
    expect(filterMentionCandidates(candidates, '', 1)).toHaveLength(1)
  })
})

describe('applyMention：替换 token 并把光标放到插入点之后', () => {
  const insert = makeMentionInsert({
    kind: 'document',
    label: '起诉状.pdf',
    subpath: '1-一审/起诉状.pdf',
    owner: { kind: 'contract', id: 5 },
  })

  it('替换整段 token（连触发字符一起），caret = 起点 + 内联文本长度', () => {
    const text = '结合 @起诉 第3段分析'
    // 光标停在「起诉」末尾（@ 后第 2 个字之后）
    const token = detectMentionToken(text, 6)!
    const out = applyMention(text, token, insert)
    expect(out.text).toBe('结合 @起诉状.pdf  第3段分析')
    expect(out.caret).toBe('结合 @起诉状.pdf '.length)
    // 光标确实落在插入内容之后（继续打字不会插进引用中间）
    expect(out.text.slice(0, out.caret)).toBe('结合 @起诉状.pdf ')
  })

  it('没有 insertText 时回落到 clipboardText（老调用点兼容）', () => {
    const out = applyMention('@x', { trigger: '@', query: 'x', start: 0, end: 2 }, { ...insert, insertText: undefined })
    expect(out.text).toBe(insert.clipboardText)
  })
})

describe('mentionRefBlock：出站协议的唯一构造点', () => {
  it('文书 → 已引用文件块（无 attachment_id 的引用形态）', () => {
    expect(
      mentionRefBlock({ kind: 'document', label: '起诉状.pdf', subpath: '1-一审/起诉状.pdf', owner: { kind: 'contract', id: 5 } }),
    ).toBe('[已引用文件：起诉状.pdf (contract_id=5, subpath="1-一审/起诉状.pdf")]')
  })

  it('案件/合同/目录 → 已引用目录块，进度是 case_id 还是 contract_id 由 owner 决定', () => {
    expect(mentionRefBlock({ kind: 'folder', label: '立案材料', subpath: '1-一审/立案材料', owner: { kind: 'case', id: 7 } })).toBe(
      '[已引用目录：立案材料 (case_id=7, subpath="1-一审/立案材料")]',
    )
    // 整案引用：'.' 经后端 normalize_subpath 归一成绑定根（空串会让 SENT_REF_RE 认不出）
    expect(mentionRefBlock({ kind: 'case', label: '张三诉李四', subpath: '.', owner: { kind: 'case', id: 7 } })).toBe(
      '[已引用目录：张三诉李四 (case_id=7, subpath=".")]',
    )
  })

  it('拖拽/上传路径复用同一构造器：attachment_id 在前', () => {
    expect(
      mentionRefBlock(
        { kind: 'document', label: 'a.pdf', subpath: 'a.pdf', owner: { kind: 'contract', id: 3 } },
        'ab-12',
      ),
    ).toBe('[已引用文件：a.pdf (attachment_id=ab-12, contract_id=3, subpath="a.pdf")]')
  })

  it('文件名里的换行/引号被归一（否则行式解析被切坏、正则提前闭合）', () => {
    expect(
      mentionRefBlock({ kind: 'document', label: '起\n诉状.pdf', subpath: 'a"b.pdf', owner: { kind: 'case', id: 1 } }),
    ).toBe('[已引用文件：起 诉状.pdf (case_id=1, subpath="a\'b.pdf")]')
  })

  it('没有归属就拼不出块（宁可空串，让 outgoing 留痕，也不发明第二种格式）', () => {
    expect(mentionRefBlock({ kind: 'document', label: 'x.pdf' })).toBe('')
  })

  it('与历史回放的解析器互逆：块 → chip 元数据', () => {
    const block = mentionRefBlock({
      kind: 'folder',
      label: '立案材料',
      subpath: '1-一审/立案材料',
      owner: { kind: 'case', id: 7 },
    })
    const parsed = splitRefBlocks(`正文\n${block}`)
    expect(parsed.body).toBe('正文')
    expect(parsed.refs).toEqual([
      { isFolder: true, name: '立案材料', kind: 'case', ownerId: 7, subpath: '1-一审/立案材料' },
    ])
  })

  it('整案引用的 "." 也能被历史回放解析回来（不是一条认不出的文本）', () => {
    const block = mentionRefBlock({ kind: 'case', label: '张三诉李四', subpath: '.', owner: { kind: 'case', id: 7 } })
    expect(splitRefBlocks(block).refs).toHaveLength(1)
  })
})

describe('makeMentionInsert', () => {
  it('内联文本是 @名字+空格，出站文本是协议块', () => {
    const insert = makeMentionInsert({ kind: 'case', refId: 3, label: '张三诉李四', subpath: '.', owner: { kind: 'case', id: 3 } })
    expect(insert.insertText).toBe('@张三诉李四 ')
    expect(insert.clipboardText).toBe('[已引用目录：张三诉李四 (case_id=3, subpath=".")]')
  })
})

describe('菜单行与高亮（纯函数部分）', () => {
  const groups = [
    { key: 'case', status: 'ready' as const, items: [{ kind: 'case' as const, label: '案件A' }] },
    { key: 'document', status: 'pending' as const, items: [{ kind: 'document' as const, label: '陈旧文书' }] },
  ]

  it('pending 组行不进选项：键盘永远碰不到陈旧数据', () => {
    expect(flattenMentionOptions(groups)).toEqual([{ key: 'case', index: 0, candidate: { kind: 'case', label: '案件A' } }])
  })

  it('高亮环形移动；位置失效回第一行；空选项为 null', () => {
    const options = flattenMentionOptions(groups)
    const first = moveMentionHighlight(options, null, 1)
    expect(first).toEqual({ key: 'case', index: 0 })
    expect(moveMentionHighlight(options, first, 1)).toEqual({ key: 'case', index: 0 })
    expect(moveMentionHighlight(options, { key: 'gone', index: 3 }, -1)).toEqual({ key: 'case', index: 0 })
    expect(moveMentionHighlight([], null, 1)).toBeNull()
  })

  it('选项 id 由分组键 + 组内下标组成（扁平下标会随组增减错位）', () => {
    expect(mentionOptionId('document', 2)).toBe('mention-opt-document-2')
  })
})
