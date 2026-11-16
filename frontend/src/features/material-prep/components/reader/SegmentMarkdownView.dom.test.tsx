// @vitest-environment jsdom
/**
 * 「原始 Markdown」视图单测（P3-2）。
 *
 * 锁三件事：① 表格/标题真的按结构渲染（律师核对的正是 OCR 最易错处）；
 * ② **不执行原始 HTML**、图片不发请求（识别产物里泄漏的标签与相对路径不能变成注入面）；
 * ③ 整段编辑走显式保存，取消不写回。全部用合成数据。
 */
import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SegmentMarkdownView } from './SegmentMarkdownView'

const MD = [
  '# 借款合同',
  '',
  '## 第一条 借款金额',
  '',
  '| 日期 | 金额 |',
  '| --- | --- |',
  '| 20260101 | 100 |',
  '',
  '借款人：测试甲',
].join('\n')

describe('渲染视图：结构看得见', () => {
  it('标题按层级渲染、表格渲染成 table/th/td（不再是拍平的纯文本行）', () => {
    const { container } = render(<SegmentMarkdownView md={MD} />)
    expect(container.querySelector('h1')?.textContent).toBe('借款合同')
    expect(container.querySelector('h2')?.textContent).toBe('第一条 借款金额')
    expect(container.querySelectorAll('th')).toHaveLength(2)
    expect(container.querySelectorAll('td')).toHaveLength(2)
    expect(container.querySelector('table')).toBeTruthy()
    // 默认不是源码视图
    expect(container.querySelector('pre')).toBeNull()
  })

  it('切到「源码」看得到原始 md（含 GFM 竖线）', () => {
    const { container, getByText } = render(<SegmentMarkdownView md={MD} />)
    fireEvent.click(getByText('源码'))
    const pre = container.querySelector('pre')
    expect(pre?.textContent).toBe(MD)
    expect(container.querySelector('table')).toBeNull()
  })
})

describe('安全口径：不执行原始 HTML、图片不发请求', () => {
  it('泄漏的 <img>/<div>/<script> 不进 DOM，只提示去源码看', () => {
    const md = '正文一\n\n<img src="imgs/box_1.jpg">\n<div>块</div>\n<script>alert(1)</script>\n\n正文二'
    const { container, getByText } = render(<SegmentMarkdownView md={md} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    // 原始 HTML 只以**文本**形式出现（转义后给律师看见泄漏），不变成 DOM 节点
    expect(container.textContent).toContain('<div>块</div>')
    expect(getByText(/正文里有 HTML 标签/)).toBeTruthy()
    // 正文本身照常渲染
    expect(container.textContent).toContain('正文一')
    expect(container.textContent).toContain('正文二')
  })

  it('Markdown 图片渲染成占位说明，不产生 img 请求（相对路径解析不到）', () => {
    const { container } = render(<SegmentMarkdownView md={'![身份证](imgs/id.jpg)'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('未随正文提供')
    expect(container.textContent).toContain('imgs/id.jpg')
  })

  it('没有 HTML 标签时不渲染提示（不制造噪声）', () => {
    const { queryByText } = render(<SegmentMarkdownView md={MD} />)
    expect(queryByText(/正文里有 HTML 标签/)).toBeNull()
  })
})

describe('整段编辑：显式保存，取消不写回', () => {
  it('点「编辑整段」预填当前 md，保存回调新正文', () => {
    const onCommit = vi.fn()
    const { container, getByText } = render(<SegmentMarkdownView md={MD} onCommit={onCommit} />)
    fireEvent.click(getByText('编辑整段'))
    const ta = container.querySelector('textarea') as HTMLTextAreaElement
    expect(ta.value).toBe(MD)
    fireEvent.change(ta, { target: { value: '# 律师核过的正文' } })
    fireEvent.click(getByText('保存整段'))
    expect(onCommit).toHaveBeenCalledExactlyOnceWith('# 律师核过的正文')
    // 保存后回到渲染视图
    expect(container.querySelector('textarea')).toBeNull()
  })

  it('取消不写回；Esc 同样取消', () => {
    const onCommit = vi.fn()
    const { container, getByText } = render(<SegmentMarkdownView md={MD} onCommit={onCommit} />)
    fireEvent.click(getByText('编辑整段'))
    fireEvent.change(container.querySelector('textarea')!, { target: { value: '改坏了' } })
    fireEvent.click(getByText('取消'))
    expect(onCommit).not.toHaveBeenCalled()

    fireEvent.click(getByText('编辑整段'))
    fireEvent.keyDown(container.querySelector('textarea')!, { key: 'Escape' })
    expect(onCommit).not.toHaveBeenCalled()
    expect(container.querySelector('textarea')).toBeNull()
  })

  it('失焦不自动保存（法律正文不能「切走就提交」）', () => {
    const onCommit = vi.fn()
    const { container, getByText } = render(<SegmentMarkdownView md={MD} onCommit={onCommit} />)
    fireEvent.click(getByText('编辑整段'))
    fireEvent.blur(container.querySelector('textarea')!)
    expect(onCommit).not.toHaveBeenCalled()
  })

  it('只读场景（未给 onCommit）没有编辑入口', () => {
    const { queryByText } = render(<SegmentMarkdownView md={MD} />)
    expect(queryByText('编辑整段')).toBeNull()
  })

  it('editRequest 递增 → 直接进编辑态并预填最新 md（页面框双击的退路）', () => {
    const { container, rerender } = render(<SegmentMarkdownView md={MD} onCommit={vi.fn()} editRequest={0} />)
    expect(container.querySelector('textarea')).toBeNull()
    rerender(<SegmentMarkdownView md="新的正文" onCommit={vi.fn()} editRequest={1} />)
    expect((container.querySelector('textarea') as HTMLTextAreaElement).value).toBe('新的正文')
    // 同一请求号不重复触发：用户正在打的话不被父级重渲染覆盖
    fireEvent.change(container.querySelector('textarea')!, { target: { value: '律师正在改' } })
    rerender(<SegmentMarkdownView md="新的正文" onCommit={vi.fn()} editRequest={1} />)
    expect((container.querySelector('textarea') as HTMLTextAreaElement).value).toBe('律师正在改')
  })
})
