import { describe, expect, it } from 'vitest'

import type { DealCase } from '../../../types'
import { caseMetaParts, legalStatusGroups, timelineEntries } from './case-section-domain'
import { stripEntryParens } from './filename-text'

function makeCase(over: Partial<DealCase> = {}): DealCase {
  return {
    id: 1,
    name: '案件',
    proc: '一审',
    ref: '',
    numbers: [],
    st: '在办',
    done: false,
    auth: '',
    auths: [],
    cause: '',
    target: null,
    preserv: null,
    from: '',
    partyRows: [],
    parties: [],
    logs: [],
    logReminders: [],
    contacts: [],
    ...over,
  }
}

/** 日志附件夹具（合并用例按 id 去重） */
const att = (id: number, name = 'a' + id + '.pdf') => ({ id, name, mediaUrl: '/media/x/' + id })

describe('案件节', () => {
  it('caseMetaParts：空值不出片段，机构/标的/保全加粗', () => {
    expect(caseMetaParts(makeCase())).toEqual([])
    expect(
      caseMetaParts(makeCase({ auth: '佛山中院', from: '2026-03-05', cause: '金融借款', target: 3200000, preserv: 0 })),
    ).toEqual([
      { v: '佛山中院', strong: true },
      { k: '收案', v: '2026-03-05' },
      { v: '金融借款' },
      { k: '标的', v: '¥3,200,000', strong: true },
    ])
  })

  it('legalStatusGroups：按地位分组保序、空名跳过、无地位归「当事人」', () => {
    expect(
      legalStatusGroups(
        makeCase({
          parties: [
            { status: '原告', name: '甲' },
            { status: '被告', name: '乙' },
            { status: '被告', name: '丙' },
            { status: '', name: '丁' },
            { status: '被告', name: '' },
          ],
        }),
      ),
    ).toEqual([
      { status: '原告', names: ['甲'] },
      { status: '被告', names: ['乙', '丙'] },
      { status: '当事人', names: ['丁'] },
    ])
  })

  it('legalStatusGroups：按判决书逻辑排序——原告 → 被告 → 第三人，不看出现顺序；未知地位殿后保序', () => {
    expect(
      legalStatusGroups(
        makeCase({
          parties: [
            { status: '被告', name: '乙' },
            { status: '第三人', name: '丙' },
            { status: '原告', name: '甲' },
            { status: '案外人', name: '戊' },
            { status: '案外人', name: '己' },
          ],
        }),
      ),
    ).toEqual([
      { status: '原告', names: ['甲'] },
      { status: '被告', names: ['乙'] },
      { status: '第三人', names: ['丙'] },
      { status: '案外人', names: ['戊', '己'] },
    ])
  })

  it('timelineEntries：倒序日志翻成升序叙事，日期取前 10 位', () => {
    const c = makeCase({
      logs: [
        { id: 2, when: '2026-03-05T10:00', who: '王某某', text: '二审立案', attN: 0, atts: [], rem: '', remToday: false },
        { id: 1, when: '2026-02-02T09:30', who: '李某某', text: '收到上诉状', attN: 2, atts: [att(11), att(12)], rem: '', remToday: false },
      ],
    })
    expect(timelineEntries(c).map((e) => [e.date, e.text, e.who, e.attN])).toEqual([
      ['2026-02-02', '收到上诉状', '李某某', 2],
      ['2026-03-05', '二审立案', '王某某', 0],
    ])
  })

  it('timelineEntries：相同内容自动合并（×N、落最新时间、who 取最新、附件按文件名去重并集）', () => {
    const dup = '收到法院短信：执行款已到账'
    const c = makeCase({
      logs: [
        // 倒序（新 → 旧）：两条同内容 + 一条独立；重放日志附件常同名不同 id
        { id: 5, when: '2026-09-03T10:00', who: '李某某', text: dup, attN: 2, atts: [{ id: 52, name: '裁定书.pdf', mediaUrl: '/media/x52' }, att(51)], rem: '', remToday: false },
        { id: 4, when: '2026-09-02T09:00', who: '系统', text: dup, attN: 2, atts: [{ id: 41, name: '裁定书.pdf', mediaUrl: '/media/x41' }, att(51)], rem: '', remToday: false },
        { id: 3, when: '2026-08-30T09:00', who: '李某某', text: '单独一条', attN: 0, atts: [], rem: '', remToday: false },
      ],
    })
    const out = timelineEntries(c)
    expect(out.map((e) => [e.date, e.text, e.who, e.n])).toEqual([
      ['2026-08-30', '单独一条', '李某某', 1],
      ['2026-09-03', dup, '李某某', 2],
    ])
    const merged = out[1]!
    // 「裁定书.pdf」两条同名只留先到的 id=41，a51 的名字不同保留
    expect(merged.atts.map((a) => a.id)).toEqual([41, 51])
    expect(merged.attN).toBe(2)
    expect(merged.key).toBe('L4')
  })

  it('timelineEntries：单条待合并日志自带两个同名附件时不得重复计入', () => {
    // 回归 2026-10 审查 P0：合并分支的 seenNames 漏 add，同一批 l.atts 内的同名
    // 第二个附件会绕过去重被重复 push（重放日志常带同名不同 id 的附件）
    const dup = '收到法院短信：执行款已到账'
    const c = makeCase({
      logs: [
        // 倒序：较新的一条带两个同名「裁定书.pdf」
        {
          id: 9,
          when: '2026-09-03T10:00',
          who: '系统',
          text: dup,
          attN: 2,
          atts: [att(92, '裁定书.pdf'), att(91, '裁定书.pdf')],
          rem: '',
          remToday: false,
        },
        // 较旧的一条先建立条目
        { id: 8, when: '2026-09-02T09:00', who: '系统', text: dup, attN: 1, atts: [att(81, '其它.pdf')], rem: '', remToday: false },
      ],
    })
    const merged = timelineEntries(c)[0]!
    expect(merged.n).toBe(2)
    // 「裁定书.pdf」只应留一个（先出现的 92），加「其它.pdf」共 2 个
    expect(merged.atts.map((a) => a.name)).toEqual(['其它.pdf', '裁定书.pdf'])
    expect(merged.attN).toBe(2)
  })

  it('timelineEntries：多条日志跨轮次合并时同名附件不重复', () => {
    // 回归 2026-10 审查 P0：合并分支的 seenNames 曾漏 add，导致第二轮之后的
    // 同名附件被重复 push（重放日志常带同名不同 id 的附件）
    const dup = '收到法院短信：执行款已到账'
    const c = makeCase({
      logs: [
        { id: 7, when: '2026-09-04T10:00', who: '李某某', text: dup, attN: 1, atts: [{ id: 73, name: '裁定书.pdf', mediaUrl: '/media/x73' }], rem: '', remToday: false },
        { id: 6, when: '2026-09-03T10:00', who: '系统', text: dup, attN: 1, atts: [{ id: 62, name: '裁定书.pdf', mediaUrl: '/media/x62' }], rem: '', remToday: false },
        { id: 5, when: '2026-09-02T09:00', who: '系统', text: dup, attN: 1, atts: [{ id: 51, name: '裁定书.pdf', mediaUrl: '/media/x51' }], rem: '', remToday: false },
      ],
    })
    const merged = timelineEntries(c)[0]!
    expect(merged.n).toBe(3)
    // 同名附件只保留最早的一条，跨三轮合并不得重复
    expect(merged.atts.map((a) => a.id)).toEqual([51])
    expect(merged.attN).toBe(1)
  })

  it('timelineEntries：三轮合并时每轮新增的不同名附件都要保留', () => {
    const dup = '收到法院短信：执行款已到账'
    const c = makeCase({
      logs: [
        { id: 7, when: '2026-09-04T10:00', who: 'A', text: dup, attN: 2, atts: [att(73, 'c.pdf'), att(71, 'a.pdf')], rem: '', remToday: false },
        { id: 6, when: '2026-09-03T10:00', who: 'B', text: dup, attN: 2, atts: [att(62, 'b.pdf'), att(61, 'a.pdf')], rem: '', remToday: false },
        { id: 5, when: '2026-09-02T09:00', who: 'C', text: dup, attN: 1, atts: [att(51, 'a.pdf')], rem: '', remToday: false },
      ],
    })
    const merged = timelineEntries(c)[0]!
    // 去重按文件名，保留首次出现的 id：a=51（最早）、b=62、c=73
    expect(merged.atts.map((a) => a.name).sort()).toEqual(['a.pdf', 'b.pdf', 'c.pdf'])
    expect(merged.attN).toBe(3)
  })

  it('stripEntryParens：括号内容一律隐藏（长案件名/当事人/年份都不留），退化情形回原名', () => {
    // 长描述型 → 隐藏，卡片已标明案件
    expect(stripEntryParens('民事裁定书（张某诉某公司买卖合同纠纷一案）_20260929收.pdf')).toBe(
      '民事裁定书_20260929收.pdf',
    )
    // 嵌套括号（案件名里嵌公司名括号）配平后整体隐藏
    expect(stripEntryParens('账户确认书（张某诉某公司买卖合同纠纷（二审）一案）V1.pdf')).toBe('账户确认书V1.pdf')
    // 短括号同样隐藏：当事人、年份案号、备注（全名看 tooltip / 预览面板）
    expect(stripEntryParens('通知书（王某执行案）_20260414收.pdf')).toBe('通知书_20260414收.pdf')
    expect(stripEntryParens('（20XX）粤0000执保1号民事裁定书.pdf')).toBe('粤0000执保1号民事裁定书.pdf')
    expect(stripEntryParens('2-授权委托书（张某）（某醉驾一案）V1.pdf')).toBe('2-授权委托书V1.pdf')
    expect(stripEntryParens('【发票】某甲（个人）_20251023.pdf')).toBe('【发票】某甲_20251023.pdf')
    // 整名都在括号里 / 括号不配对 / 隐藏后只剩扩展名 → 退回原名
    expect(stripEntryParens('（张某诉某公司买卖合同纠纷一案）.pdf')).toBe('（张某诉某公司买卖合同纠纷一案）.pdf')
    expect(stripEntryParens('说明（未闭合.pdf')).toBe('说明（未闭合.pdf')
  })
})
