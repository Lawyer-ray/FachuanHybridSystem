/**
 * 服务事项识别测试（用例取自 300-常法 下的真实目录名）。
 *
 * 核心主张：常法项目的目录结构本身就是数据。律师每天就在
 * `3-办案/2026.04.27-草拟付款确认书/` 里干活，事项名与日期都写在文件夹名上；
 * 再让他到系统里录一遍是同一件事做两次，且两边一旦不同步就不知道该信哪个。
 */
import { describe, expect, it } from 'vitest'

import {
  looksLikeCaseFolder,
  parseDatedFolder,
  pickServiceItems,
  stripOrderPrefix,
  type FolderEntry,
} from './service-items'

const f = (name: string): FolderEntry => ({ name, subpath: name })

describe('stripOrderPrefix', () => {
  it('去掉排序前缀但不动正文', () => {
    expect(stripOrderPrefix('3-办案')).toBe('办案')
    expect(stripOrderPrefix('2-办案')).toBe('办案')
    expect(stripOrderPrefix('1-合同发票')).toBe('合同发票')
    expect(stripOrderPrefix('办案')).toBe('办案')
  })

  it('不把年份当排序前缀吃掉', () => {
    // `2026.04.27-xx` 若被当成 `序号.` 前缀会毁掉日期
    expect(stripOrderPrefix('2026.04.27-草拟付款确认书')).toBe('2026.04.27-草拟付款确认书')
  })
})

describe('parseDatedFolder', () => {
  it('解析点分隔日期', () => {
    expect(parseDatedFolder('2026.04.27-草拟付款确认书')).toEqual({
      date: '2026-04-27',
      title: '草拟付款确认书',
    })
  })

  it('解析横线分隔日期', () => {
    expect(parseDatedFolder('2026-04-27-修改租赁合同')).toEqual({
      date: '2026-04-27',
      title: '修改租赁合同',
    })
  })

  it('解析中文日期', () => {
    expect(parseDatedFolder('2026年4月27日-发送律师函')).toEqual({
      date: '2026-04-27',
      title: '发送律师函',
    })
  })

  it('日期补零（4 → 04）', () => {
    expect(parseDatedFolder('2026.4.7-简易事项').date).toBe('2026-04-07')
  })

  it('无日期时保留整名、不丢条目', () => {
    // 宁可少一个日期，也不要因为格式不合就整条丢掉
    expect(parseDatedFolder('交接清单')).toEqual({ date: '', title: '交接清单' })
  })

  it('日期后无事项名时回退为原目录名', () => {
    expect(parseDatedFolder('2026.05.11-').title).toBe('2026.05.11-')
  })
})

describe('looksLikeCaseFolder', () => {
  it('认「办案」与「日常办案」', () => {
    expect(looksLikeCaseFolder('3-办案')).toBe(true)
    expect(looksLikeCaseFolder('3-日常办案')).toBe(true)
    expect(looksLikeCaseFolder('2-办案')).toBe(true)
  })

  it('不误认合同/邮寄目录', () => {
    expect(looksLikeCaseFolder('1-合同发票')).toBe(false)
    expect(looksLikeCaseFolder('2-邮寄')).toBe(false)
    expect(looksLikeCaseFolder('归档文件夹')).toBe(false)
  })
})

describe('pickServiceItems', () => {
  const roots = [f('1-合同发票'), f('2-邮寄'), f('3-办案'), f('归档文件夹')]
  const kids: Record<string, FolderEntry[]> = {
    '1-合同发票': [f('【顾问合同】.docx'), f('【发票】.pdf')],
    '2-邮寄': [],
    '3-办案': [
      f('2026.05.11-交接清单'),
      f('2026.06.09-租赁合同'),
      f('2026.04.27-草拟付款确认书'),
    ],
    '归档文件夹': [],
  }
  const childrenOf = (p: string) => kids[p] ?? []

  it('把「办案」下的子目录转成事项', () => {
    const items = pickServiceItems(roots, childrenOf)
    expect(items.map((i) => i.title)).toEqual(['租赁合同', '交接清单', '草拟付款确认书'])
  })

  it('按日期倒序（最近的在前）', () => {
    const items = pickServiceItems(roots, childrenOf)
    const dates = items.map((i) => i.date)
    expect(dates).toEqual(['2026-06-09', '2026-05-11', '2026-04-27'])
  })

  it('不把合同/发票目录的文件当事项', () => {
    const items = pickServiceItems(roots, childrenOf)
    expect(items.every((i) => !i.title.includes('顾问合同'))).toBe(true)
  })

  it('ignores 事项层里的散文件（附件不是事项）', () => {
    const withFiles = (p: string) =>
      p === '3-办案' ? [...(kids['3-办案'] ?? []), f('说明.pdf')] : childrenOf(p)
    const items = pickServiceItems(roots, withFiles)
    expect(items.every((i) => !i.title.endsWith('.pdf'))).toBe(true)
  })

  it('没有「办案」目录时，退化为「子目录最像日期-事项」的那个', () => {
    // 客户把事项放在 2-案件记录 里也应该能认出来
    const alt = [f('1-合同发票'), f('2-案件记录')]
    const altKids: Record<string, FolderEntry[]> = {
      '1-合同发票': [f('a.docx')],
      '2-案件记录': [f('2026.03.01-起草协议'), f('2026.03.15-审查合同')],
    }
    const items = pickServiceItems(alt, (p) => altKids[p] ?? [])
    expect(items.map((i) => i.title)).toEqual(['审查合同', '起草协议'])
  })

  it('完全没有日期目录时返回空（不瞎猜）', () => {
    const items = pickServiceItems([f('1-合同发票')], () => [f('a.docx'), f('b.pdf')])
    expect(items).toEqual([])
  })

  it('无日期的事项沉底并按名称排', () => {
    const ks: Record<string, FolderEntry[]> = {
      '3-办案': [f('2026.01.01-有日期'), f('交接清单'), f('归档说明')],
    }
    const items = pickServiceItems([f('3-办案')], (p) => ks[p] ?? [])
    expect(items[0]!.title).toBe('有日期')
    // 无日期的按中文（拼音）升序：归 < 交
    expect(items.slice(1).map((i) => i.title)).toEqual(['归档说明', '交接清单'])
  })

  it('保留 subpath 供下载/预览定位', () => {
    const items = pickServiceItems(roots, childrenOf)
    expect(items[0]!.subpath).toBe('2026.06.09-租赁合同')
  })
})
