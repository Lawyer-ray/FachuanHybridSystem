/**
 * useMediaQuery 的「无 window」守卫（本文件跑在 node 环境，没有 window / document）。
 *
 * 真实场景：SSR 或纯逻辑测试里渲染到使用本 hook 的模块时，惰性初始化直接读
 * window.matchMedia 会抛 ReferenceError（App.dom.test 里那片 stubMatchMedia
 * 的注释就是踩过这个坑）。用 react-dom/server 渲染正好只走到惰性初始化这一行
 * ——有 DOM 的 renderHook 在本环境跑不起来，也就测不到要守的地方。
 */
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { useMediaQuery } from './use-media'

function Probe() {
  return createElement('span', null, String(useMediaQuery('(max-width: 760px)')))
}

describe('useMediaQuery / 无 window 守卫', () => {
  it('无 window / document 时惰性初始化不抛错，按不匹配（false）渲染', () => {
    expect(typeof window).toBe('undefined')
    expect(() => renderToString(createElement(Probe))).not.toThrow()
    expect(renderToString(createElement(Probe))).toContain('false')
  })
})
