// @vitest-environment jsdom
/**
 * 邮件 HTML 正文渲染（jsdom）。
 *
 * 锁定：只有 HTML 正文的邮件（银行到账通知）必须真的渲染出来，不能白屏；
 * 且渲染容器不得被授予脚本 / 同源权限。
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MailHtmlBody } from './MailHtmlBody'

describe('MailHtmlBody', () => {
  it('用 sandboxed iframe 渲染，且不授予脚本权限', async () => {
    render(<MailHtmlBody html="<html><body><p>存入人民币 2400 元</p></body></html>" />)

    const frame = await screen.findByTitle('邮件正文')
    // 安全边界：这两个属性都不能出现
    const sandbox = frame.getAttribute('sandbox') ?? ''
    expect(sandbox).not.toContain('allow-scripts')
    expect(sandbox).not.toContain('allow-same-origin')
    // 正文内容应写进 srcDoc
    await waitFor(() => {
      expect(frame.getAttribute('srcdoc')).toContain('2400')
    })
  })

  it('剥掉邮件自带 html/head 外壳，只留 body 内容', async () => {
    render(
      <MailHtmlBody html="<html><head><style>p{color:red}</style></head><body><p>正文在</p></body></html>" />,
    )

    const frame = await screen.findByTitle('邮件正文')
    const doc = frame.getAttribute('srcdoc') ?? ''
    expect(doc).toContain('正文在')
    // 邮件自带的 head 内容不应出现（会被我们注入的样式覆盖，导致排版错乱）
    expect(doc).not.toContain('color:red')
  })
})
