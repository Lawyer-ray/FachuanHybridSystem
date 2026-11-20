// @vitest-environment jsdom
/**
 * 右栏正文「渲染 / 源码 / 编辑整段」三种呈现的单测（P3-2）。
 *
 * 锁三件事：① 表格/标题真的按结构渲染（律师核对的正是 OCR 最易错处）；
 * ② **不执行原始 HTML**、图片不发请求（识别产物里泄漏的标签与相对路径不能变成注入面）；
 * ③ 整段编辑走显式保存，取消不写回。
 *
 * 组件是**受控**的（`mode` / `onModeChange` 由父级给）：切换器只有一套，在
 * `SegmentMarkdown` 的 tab 行里。所以这里直接按 mode 渲染，不再点本组件的按钮。
 */
import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SegmentMarkdownView, type MarkdownViewMode } from './SegmentMarkdownView'

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

/** 受控渲染的最小外壳：与 SegmentMarkdown 一样把 mode 放在 state 里 */
function controlled(
  props: { md?: string; mode?: MarkdownViewMode; onCommit?: (md: string) => void } = {},
) {
  const { md = MD, mode = 'render' as MarkdownViewMode, onCommit } = props
  const onModeChange = vi.fn()
  const utils = render(
    <SegmentMarkdownView md={md} mode={mode} onModeChange={onModeChange} onCommit={onCommit} />,
  )
  return { ...utils, onModeChange }
}

describe('渲染视图：结构看得见', () => {
  it('标题按层级渲染、表格渲染成 table/th/td（不再是拍平的纯文本行）', () => {
    const { container } = controlled({ mode: 'render' })
    expect(container.querySelector('h1')?.textContent).toBe('借款合同')
    expect(container.querySelector('h2')?.textContent).toBe('第一条 借款金额')
    expect(container.querySelectorAll('th')).toHaveLength(2)
    expect(container.querySelectorAll('td')).toHaveLength(2)
    expect(container.querySelector('table')).toBeTruthy()
    // 渲染视图不是源码
    expect(container.querySelector('pre')).toBeNull()
  })

  it('源码视图给出原始 md（含 GFM 竖线），不渲染结构', () => {
    const { container } = controlled({ mode: 'source' })
    const pre = container.querySelector('pre')
    expect(pre?.textContent).toBe(MD)
    expect(container.querySelector('table')).toBeNull()
  })
})

describe('安全口径：不执行原始 HTML、图片不发请求', () => {
  it('泄漏的 <img>/<div>/<script> 不进 DOM，只提示去源码看', () => {
    const md = '正文一\n\n<img src="imgs/box_1.jpg">\n<div>块</div>\n<script>alert(1)</script>\n\n正文二'
    const { container, getByText } = controlled({ md })
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
    const { container } = controlled({ md: '![身份证](imgs/id.jpg)' })
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('未随正文提供')
    expect(container.textContent).toContain('imgs/id.jpg')
  })

  it('没有 HTML 标签时不渲染提示（不制造噪声）', () => {
    const { queryByText } = controlled()
    expect(queryByText(/正文里有 HTML 标签/)).toBeNull()
  })
})

describe('整段编辑：显式保存，取消不写回', () => {
  it('编辑态预填当前 md，保存回调新正文并交回渲染视图', () => {
    const onCommit = vi.fn()
    const { container, getByText, onModeChange } = controlled({ mode: 'edit', onCommit })
    const ta = container.querySelector('textarea') as HTMLTextAreaElement
    expect(ta.value).toBe(MD)
    fireEvent.change(ta, { target: { value: '# 律师核过的正文' } })
    fireEvent.click(getByText('保存整段'))
    expect(onCommit).toHaveBeenCalledExactlyOnceWith('# 律师核过的正文')
    // 保存后由父级切回渲染视图（本组件只上报，不自己改 mode）
    expect(onModeChange).toHaveBeenCalledWith('render')
  })

  it('取消不写回；Esc 同样取消', () => {
    const onCommit = vi.fn()
    const { container, getByText, onModeChange } = controlled({ mode: 'edit', onCommit })
    fireEvent.change(container.querySelector('textarea')!, { target: { value: '改坏了' } })
    fireEvent.click(getByText('取消'))
    expect(onCommit).not.toHaveBeenCalled()
    expect(onModeChange).toHaveBeenCalledWith('render')

    onModeChange.mockClear()
    fireEvent.keyDown(container.querySelector('textarea')!, { key: 'Escape' })
    expect(onCommit).not.toHaveBeenCalled()
    expect(onModeChange).toHaveBeenCalledWith('render')
  })

  it('失焦不自动保存（法律正文不能「切走就提交」）', () => {
    const onCommit = vi.fn()
    const { container } = controlled({ mode: 'edit', onCommit })
    fireEvent.blur(container.querySelector('textarea')!)
    expect(onCommit).not.toHaveBeenCalled()
  })

  /**
   * 进入编辑态那一下才用最新 md 预填：编辑期间父级重渲染不能把律师正在打的话冲掉。
   * 改成受控之后最容易写错的地方，就是把 md 直接写进 value。
   */
  it('进编辑时用最新 md 预填；已在编辑中则不覆盖用户输入', () => {
    const { container, rerender } = render(
      <SegmentMarkdownView md={MD} mode="render" onModeChange={vi.fn()} onCommit={vi.fn()} />,
    )
    rerender(<SegmentMarkdownView md={MD} mode="edit" onModeChange={vi.fn()} onCommit={vi.fn()} />)
    expect((container.querySelector('textarea') as HTMLTextAreaElement).value).toBe(MD)

    fireEvent.change(container.querySelector('textarea')!, { target: { value: '律师正在改' } })
    rerender(<SegmentMarkdownView md="父级又换了正文" mode="edit" onModeChange={vi.fn()} onCommit={vi.fn()} />)
    expect((container.querySelector('textarea') as HTMLTextAreaElement).value).toBe('律师正在改')
  })
})
