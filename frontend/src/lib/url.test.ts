import { describe, expect, it } from 'vitest'

import { safeHttpUrl } from './url'

describe('safeHttpUrl（scheme 白名单守卫）', () => {
  it('http / https 放行', () => {
    expect(safeHttpUrl('https://example.com/a?b=1')).toBe('https://example.com/a?b=1')
    expect(safeHttpUrl('http://127.0.0.1:8002/media/x.pdf')).toBe('http://127.0.0.1:8002/media/x.pdf')
  })

  it('javascript: 注入拦截（含大小写、前导空白变体）', () => {
    expect(safeHttpUrl('javascript:alert(1)')).toBe('')
    expect(safeHttpUrl('JAVASCRIPT:alert(1)')).toBe('')
    expect(safeHttpUrl(' javascript:alert(1)')).toBe('')
    expect(safeHttpUrl('data:text/html,<script>1</script>')).toBe('')
    expect(safeHttpUrl('vbscript:msgbox(1)')).toBe('')
  })

  it('相对路径按同源解析为绝对 http URL（node 单测无 window，base 固定 localhost）', () => {
    expect(safeHttpUrl('/media/doc.pdf')).toBe('http://localhost/media/doc.pdf')
    expect(safeHttpUrl('docs/a.pdf')).toBe('http://localhost/docs/a.pdf')
  })

  it('空值与非 http scheme 回退 fallback', () => {
    expect(safeHttpUrl('')).toBe('')
    expect(safeHttpUrl(null)).toBe('')
    expect(safeHttpUrl(undefined, '#')).toBe('#')
    expect(safeHttpUrl('javascript:alert(1)', '#')).toBe('#')
  })
})
