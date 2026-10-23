// @vitest-environment jsdom
/**
 * DocumentPreview 的 scheme 守卫回归测试。
 *
 * 背景（2026-10 审查 D-P2-6）：`task.file_url` 来自后端文书识别任务表，
 * 直通 `<a href>` 与 `<iframe src>` 而未过白名单，与同目录
 * RecognizeDialog / RecognitionSummary 的口径不一致。
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DocumentPreview } from './DocumentPreview'

function getIframeSrc(container: HTMLElement): string | null {
  return container.querySelector('iframe')?.getAttribute('src') ?? null
}

function getAnchorHref(container: HTMLElement): string | null {
  return container.querySelector('a')?.getAttribute('href') ?? null
}

describe('DocumentPreview', () => {
  it('https 地址正常渲染进 iframe 与链接', () => {
    const { container } = render(<DocumentPreview url="https://example.com/a.pdf" />)
    expect(getIframeSrc(container)).toContain('https://example.com/a.pdf')
    expect(getAnchorHref(container)).toContain('https://example.com/a.pdf')
  })

  it('javascript: 伪协议不得进入 iframe src 或 a href', () => {
    const { container } = render(<DocumentPreview url="javascript:alert(document.cookie)" />)
    // safeHttpUrl 对非法 scheme 返回空串，React 因此不渲染 src/href 属性
    expect(getIframeSrc(container) ?? '').not.toContain('javascript:')
    expect(getAnchorHref(container) ?? '').not.toContain('javascript:')
  })

  it('data: 伪协议同样被挡（可承载 HTML/SVG 脚本）', () => {
    const { container } = render(<DocumentPreview url="data:text/html,<script>alert(1)</script>" />)
    expect(getIframeSrc(container) ?? '').not.toContain('data:')
    expect(getAnchorHref(container) ?? '').not.toContain('data:')
  })

  it('图片后缀走 img 分支，非法 scheme 时 img src 也被挡', () => {
    const { container } = render(<DocumentPreview url="javascript:alert(1)//x.png" />)
    expect(container.querySelector('img')?.getAttribute('src') ?? '').not.toContain('javascript:')
  })
})
