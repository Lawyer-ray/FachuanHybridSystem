// @vitest-environment jsdom
/**
 * 首页小组件测试：CardHead 与 ToolDock。
 *
 * ToolDock 的四个工具卡各自连后端，这里整域 mock 掉，只验证工具坞的
 * 结构（四张卡都在）与全局拖放拦截（不接卡的角落拖文件不应跳走整页）。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./tools/CourtSmsCard', () => ({ CourtSmsCard: () => <div>法院短信卡</div> }))
vi.mock('./tools/DocConvertCard', () => ({ DocConvertCard: () => <div>要素式转换卡</div> }))
vi.mock('./tools/DocConverterCard', () => ({ DocConverterCard: () => <div>DOC转DOCX卡</div> }))
vi.mock('./tools/DocParseCard', () => ({ DocParseCard: () => <div>文档解析卡</div> }))

import { CardHead } from './CardHead'
import { ToolDock } from './ToolDock'

describe('CardHead', () => {
  it('渲染标题与计数丸', () => {
    const { container } = render(<CardHead title="今日" count="3 件待办" />)
    expect(screen.getByText('今日')).toBeTruthy()
    expect(screen.getByText('3 件待办')).toBeTruthy()
    container.remove()
  })
})

describe('ToolDock', () => {
  it('四张工具卡全部渲染', () => {
    const { container } = render(<ToolDock />)
    expect(screen.getByText('法院短信卡')).toBeTruthy()
    expect(screen.getByText('要素式转换卡')).toBeTruthy()
    expect(screen.getByText('DOC转DOCX卡')).toBeTruthy()
    expect(screen.getByText('文档解析卡')).toBeTruthy()
    expect(screen.getByText('快捷工具')).toBeTruthy()
    container.remove()
  })

  it('拖放文件时拦截浏览器默认行为（避免整页跳转）', () => {
    const { unmount } = render(<ToolDock />)

    const dragOver = new Event('dragover', { cancelable: true })
    Object.defineProperty(dragOver, 'dataTransfer', { value: { types: ['Files'] } })
    window.dispatchEvent(dragOver)
    expect(dragOver.defaultPrevented).toBe(true)

    const drop = new Event('drop', { cancelable: true })
    Object.defineProperty(drop, 'dataTransfer', { value: { types: ['Files'] } })
    window.dispatchEvent(drop)
    expect(drop.defaultPrevented).toBe(true)

    unmount()
  })

  it('非文件拖放不拦截（保留文本拖选等原生行为）', () => {
    const { unmount } = render(<ToolDock />)

    const dragOver = new Event('dragover', { cancelable: true })
    Object.defineProperty(dragOver, 'dataTransfer', { value: { types: ['text/plain'] } })
    window.dispatchEvent(dragOver)
    expect(dragOver.defaultPrevented).toBe(false)

    unmount()
  })

  it('卸载后移除全局监听器', () => {
    const { unmount } = render(<ToolDock />)
    unmount()

    const drop = new Event('drop', { cancelable: true })
    Object.defineProperty(drop, 'dataTransfer', { value: { types: ['Files'] } })
    window.dispatchEvent(drop)
    expect(drop.defaultPrevented).toBe(false)
  })
})
