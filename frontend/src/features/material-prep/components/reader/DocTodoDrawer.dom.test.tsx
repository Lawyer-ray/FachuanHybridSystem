// @vitest-environment jsdom
/**
 * 全卷「证件页待补录」清单（抽屉）单测。
 *
 * 真实痛点：姓名、身份证号、住址就在原页上，只是没读出来——而它们是律师必须
 * 一个字一个字抄进卷宗的东西。164 页里逐页找「哪张身份证没读出身份证号」不可能，
 * 所以这张清单必须做到四件事：
 *  1. 每条说清「哪一页、什么证件、缺什么」；
 *  2. 缺得多的排最前（最急的先看到）；
 *  3. 「查看原页」能跳过去——只能看不能跳的清单等于让人自己再翻一遍；
 *  4. 旧任务没有这项数据时是一句解释，而不是空白抽屉。
 */
import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { PageQuality } from '../../types'
import { DocTodoDrawer } from './DocTodoDrawer'

const quality: PageQuality = {
  graphic_pages: [],
  sparse_pages: [],
  blank_pages: [],
  details: {},
  doc_hints: { '23': 'id_card', '42': 'id_card', '144': 'property_cert', '8': 'license' },
  doc_missing: {
    '23': { doc: 'id_card', missing: ['姓名', '身份证号', '住址'] },
    // 字段都在、但整页内容可疑（满是乱码）：missing 为空数组，仍要出现在清单里
    '42': { doc: 'id_card', missing: [] },
    '144': { doc: 'property_cert', missing: ['权证号'] },
  },
}

function renderDrawer(over: Partial<Parameters<typeof DocTodoDrawer>[0]> = {}) {
  return render(<DocTodoDrawer open onOpenChange={vi.fn()} pageQuality={quality} {...over} />)
}

describe('DocTodoDrawer', () => {
  it('每条列出页号、证件类型与缺失字段', () => {
    const { baseElement } = renderDrawer()
    const rows = Array.from(baseElement.querySelectorAll('[data-doc-todo]')).map((li) => li.textContent ?? '')
    expect(rows[0]).toContain('P23')
    expect(rows[0]).toContain('身份证')
    expect(rows[0]).toContain('缺：姓名、身份证号、住址')
    expect(rows[1]).toContain('P144')
    expect(rows[1]).toContain('不动产权证')
    expect(rows[1]).toContain('缺：权证号')
  })

  it('按缺失字段数量降序：3 个字段的排最前', () => {
    const { baseElement } = renderDrawer()
    const pages = Array.from(baseElement.querySelectorAll('[data-doc-todo]')).map(
      (li) => li.textContent?.match(/^P(\d+)/)?.[1] ?? '',
    )
    // P23 缺 3 项 → 最前；P144 缺 1 项；P42 列不出字段（0 项但整页核对）
    expect(pages).toEqual(['23', '144', '42'])
  })

  it('missing 为空数组时仍列出该页，显示「—（建议整页核对）」而不是隐掉', () => {
    const { baseElement } = renderDrawer()
    const rows = Array.from(baseElement.querySelectorAll('[data-doc-todo]')).map((li) => li.textContent ?? '')
    const row42 = rows.find((t) => t.includes('P42'))
    // 字段都在不等于可以放过：那一页仍要翻
    expect(row42).toBeTruthy()
    expect(row42).toContain('缺：—（建议整页核对）')
  })

  it('没缺字段的证件页不进清单（无补录任务）', () => {
    const { baseElement } = renderDrawer()
    expect(baseElement.textContent).not.toContain('P8')
    expect(baseElement.querySelectorAll('[data-doc-todo]')).toHaveLength(3)
  })

  it('点「查看原页」跳到那一页', () => {
    const onGotoPage = vi.fn()
    const { baseElement } = renderDrawer({ onGotoPage })
    const rows = baseElement.querySelectorAll('[data-doc-todo]')
    fireEvent.click(within(rows[1] as HTMLElement).getByText('查看原页'))
    expect(onGotoPage).toHaveBeenCalledWith(144)
  })

  it('没有 onGotoPage 时不渲染「查看原页」按钮', () => {
    const { baseElement } = renderDrawer()
    expect(baseElement.textContent).not.toContain('查看原页')
  })

  it('摘要给出总页数', () => {
    const { baseElement } = renderDrawer()
    expect(baseElement.textContent).toContain('全卷 3 页证件材料有字段没读出来')
  })

  it('旧任务没有 doc_hints / doc_missing 时给出解释，而不是空白', () => {
    const { baseElement } = renderDrawer({
      pageQuality: { graphic_pages: [147], sparse_pages: [], blank_pages: [], details: {} },
    })
    expect(baseElement.textContent).toContain('没有发现需要补录的证件页')
    expect(baseElement.textContent).toContain('旧任务的识别结果里没有这项统计')
    expect(baseElement.querySelectorAll('[data-doc-todo]')).toHaveLength(0)
  })

  it('pageQuality 为 null 时不崩，给出空态', () => {
    const { baseElement } = renderDrawer({ pageQuality: null })
    expect(baseElement.textContent).toContain('没有发现需要补录的证件页')
    expect(baseElement.querySelectorAll('[data-doc-todo]')).toHaveLength(0)
  })

  /**
   * 真实后端 payload 回归（576 实测形态，与 `page_quality_summary` 输出逐字同形）。
   *
   * 这条锁的是「后端结构 → 律师看到的那一行」整条链路：一旦后端改字段名、
   * 或前端收窄层漏了一个键，其余单测都是自己造的夹具，照样全绿而真机白屏。
   */
  it('真实后端 page_quality payload 能直接渲染成清单', () => {
    const realPayload: PageQuality = {
      graphic_pages: [],
      sparse_pages: [23, 30],
      blank_pages: [],
      details: { '23': '这页是身份证，但姓名 / 身份证号 / 住址 均未读出，请人工录入或核对原图' },
      doc_hints: { '23': 'id_card', '30': 'marriage' },
      doc_missing: {
        '23': { doc: 'id_card', missing: ['姓名', '身份证号', '住址'] },
        '30': { doc: 'marriage', missing: [] },
      },
    }
    const { baseElement } = renderDrawer({ pageQuality: realPayload })
    const rows = Array.from(baseElement.querySelectorAll('[data-doc-todo]')).map((li) => li.textContent ?? '')
    expect(rows[0]).toContain('P23')
    expect(rows[0]).toContain('身份证')
    expect(rows[0]).toContain('缺：姓名、身份证号、住址')
    // marriage 的中文名必须与后端 _DOC_LABELS 一致（「结婚证」，不是「婚姻状况证明」）
    expect(rows[1]).toContain('P30')
    expect(rows[1]).toContain('结婚证')
    expect(rows[1]).toContain('缺：—（建议整页核对）')
  })
})
