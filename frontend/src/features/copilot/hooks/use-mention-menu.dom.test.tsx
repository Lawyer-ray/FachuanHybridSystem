// @vitest-environment jsdom
/**
 * `@` 引用管线（jsdom）：**异步竞态与失败隔离**是本文件的主角。
 *
 * 这三条是「看起来能用、实际会引用错对象」的典型：
 * 1. 慢源迟到的结果覆盖新查询 → 菜单显示的是别的查询的行；
 * 2. 一个源失败把整个菜单带走 → 用户以为 `@` 坏了；
 * 3. 组还 pending 时 Enter 选了陈旧行（或落到「发送」）→ 半截查询被发出去。
 *
 * 数据源全部注入（`sources` 参数），不打网络：源是 async 的，靠手动 resolve 制造
 * 确定性的先后顺序，而不是靠 sleep 赌时序。
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { makeMentionInsert, type MentionCandidate, type MentionSource } from '../domain'
import { resetMentionWarnings, useMentionMenu } from './use-mention-menu'

/** 造一个「结果由测试手动 resolve」的源 */
function deferredSource(key: string, title = key) {
  const calls: { query: string; resolve: (items: MentionCandidate[]) => void; reject: (e: unknown) => void }[] = []
  const source: MentionSource = {
    key,
    trigger: '@',
    title,
    load: ({ query }) =>
      new Promise<MentionCandidate[]>((resolve, reject) => {
        calls.push({ query, resolve, reject })
      }),
    toInsert: makeMentionInsert,
  }
  return { source, calls }
}

/** 立即返回固定结果的源 */
function fixedSource(key: string, items: MentionCandidate[], title = key): MentionSource {
  return { key, trigger: '@', title, load: () => Promise.resolve(items), toInsert: makeMentionInsert }
}

const doc = (label: string): MentionCandidate => ({
  kind: 'document',
  label,
  sublabel: '1-一审',
  subpath: `1-一审/${label}`,
  owner: { kind: 'contract', id: 5 },
})

/** 键盘事件替身：只带 hook 会用到的字段（key / shiftKey / nativeEvent.isComposing） */
function key(name: string, extra: { isComposing?: boolean; shiftKey?: boolean } = {}) {
  return {
    key: name,
    shiftKey: extra.shiftKey ?? false,
    nativeEvent: { isComposing: extra.isComposing ?? false },
  } as unknown as React.KeyboardEvent
}

function renderMenu(sources: MentionSource[], text = '@起') {
  const onPick = vi.fn()
  const view = renderHook(
    ({ value }: { value: string }) => useMentionMenu({ text: value, caret: value.length, sources, onPick }),
    { initialProps: { value: text } },
  )
  return { ...view, onPick }
}

beforeEach(() => {
  resetMentionWarnings()
  vi.restoreAllMocks()
})

describe('use-mention-menu：查询与竞态', () => {
  it('打 `@` 就展开，四个源先全部 pending', () => {
    const a = deferredSource('case', '案件')
    const b = deferredSource('document', '文书')
    const { result } = renderMenu([a.source, b.source])
    expect(result.current.open).toBe(true)
    expect(result.current.groups.map((g) => [g.key, g.status])).toEqual([
      ['case', 'pending'],
      ['document', 'pending'],
    ])
  })

  it('慢源迟到的结果不覆盖新查询（generation 门控）', async () => {
    const { source, calls } = deferredSource('case')
    const { result, rerender } = renderMenu([source], '@起')
    rerender({ value: '@起诉' })
    expect(calls.map((c) => c.query)).toEqual(['起', '起诉'])

    // 新查询先回来，旧查询后回来（真实的慢网顺序）
    await act(async () => {
      calls[1]!.resolve([{ kind: 'case', refId: 2, label: '起诉状案' }])
    })
    await act(async () => {
      calls[0]!.resolve([{ kind: 'case', refId: 1, label: '起——过期结果' }])
    })
    await waitFor(() => expect(result.current.options.map((o) => o.candidate.label)).toEqual(['起诉状案']))
  })

  it('单个源失败只静默掉这一组，其余组照常（console 只打一次）', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const broken: MentionSource = {
      key: 'case',
      trigger: '@',
      title: '案件',
      load: () => Promise.reject(new Error('search 500')),
      toInsert: makeMentionInsert,
    }
    const { result } = renderMenu([broken, fixedSource('document', [doc('起诉状.pdf')], '文书')])

    await waitFor(() => expect(result.current.groups.map((g) => g.key)).toEqual(['document']))
    expect(result.current.options.map((o) => o.candidate.label)).toEqual(['起诉状.pdf'])
    expect(result.current.open).toBe(true)
    expect(warn).toHaveBeenCalledTimes(1)
    expect(String(warn.mock.calls[0]?.[0])).toContain('案件')
  })

  it('Esc 关闭后同一 token 不再自动弹，改字才重开', async () => {
    const { result, rerender } = renderMenu([fixedSource('document', [doc('a.pdf')])], '@a')
    await waitFor(() => expect(result.current.options).toHaveLength(1))

    // 包在 act 里：onKeyDown 会 setState（记下 dismiss 签名），裸露调用会在用例
    // 结束时才 flush，污染 stderr
    let verdict: string = ''
    act(() => {
      verdict = result.current.onKeyDown(key('Escape'))
    })
    expect(verdict).toBe('consumed')
    await waitFor(() => expect(result.current.open).toBe(false))

    rerender({ value: '@a' })
    expect(result.current.open).toBe(false)

    rerender({ value: '@ab' })
    await waitFor(() => expect(result.current.open).toBe(true))
  })
})

describe('use-mention-menu：键盘裁决', () => {
  it('组还 pending 时 Enter 显式空转：吃掉键、不选中、不落到发送', async () => {
    const { source } = deferredSource('case')
    const { result, onPick } = renderMenu([source], '@起')
    expect(result.current.onKeyDown(key('Enter'))).toBe('consumed')
    expect(onPick).not.toHaveBeenCalled()
    // Tab 同理（Tab 要是漏出去，焦点会离开输入框）
    expect(result.current.onKeyDown(key('Tab'))).toBe('consumed')
    expect(onPick).not.toHaveBeenCalled()
  })

  it('就绪后 Enter 选中高亮行，并把 token 一起交回调用方', async () => {
    const { result, onPick } = renderMenu([fixedSource('document', [doc('起诉状.pdf'), doc('证据清单.pdf')])], '@起诉')
    await waitFor(() => expect(result.current.options).toHaveLength(2))
    expect(result.current.highlight).toEqual({ key: 'document', index: 0 })

    expect(result.current.onKeyDown(key('Enter'))).toBe('consumed')
    expect(onPick).toHaveBeenCalledTimes(1)
    const [insert, token] = onPick.mock.calls[0] as [ReturnType<typeof makeMentionInsert>, { query: string }]
    expect(insert.label).toBe('起诉状.pdf')
    // 出站块只有一种格式：文书就是「已引用文件」
    expect(insert.clipboardText).toBe('[已引用文件：起诉状.pdf (contract_id=5, subpath="1-一审/起诉状.pdf")]')
    expect(token.query).toBe('起诉')
  })

  it('↑/↓ 在共享高亮上环形移动', async () => {
    const { result } = renderMenu([fixedSource('document', [doc('a.pdf'), doc('b.pdf')])], '@')
    await waitFor(() => expect(result.current.options).toHaveLength(2))
    // 每次按键都包 act：方向键会 setHighlight（state 更新）
    await act(async () => {
      expect(result.current.onKeyDown(key('ArrowDown'))).toBe('consumed')
    })
    expect(result.current.highlight).toEqual({ key: 'document', index: 1 })
    await act(async () => {
      result.current.onKeyDown(key('ArrowDown'))
    })
    expect(result.current.highlight).toEqual({ key: 'document', index: 0 })
    await act(async () => {
      result.current.onKeyDown(key('ArrowUp'))
    })
    expect(result.current.highlight).toEqual({ key: 'document', index: 1 })
  })

  it('IME 合成期间一律 pass（选词 Enter 不属于菜单）', async () => {
    const { result, onPick } = renderMenu([fixedSource('document', [doc('a.pdf')])], '@a')
    await waitFor(() => expect(result.current.options).toHaveLength(1))
    expect(result.current.onKeyDown(key('Enter', { isComposing: true }))).toBe('pass')
    expect(result.current.onKeyDown(key('ArrowDown', { isComposing: true }))).toBe('pass')
    expect(onPick).not.toHaveBeenCalled()
  })

  it('Shift+Enter 是换行，不是选中', async () => {
    const { result, onPick } = renderMenu([fixedSource('document', [doc('a.pdf')])], '@a')
    await waitFor(() => expect(result.current.options).toHaveLength(1))
    expect(result.current.onKeyDown(key('Enter', { shiftKey: true }))).toBe('pass')
    expect(onPick).not.toHaveBeenCalled()
  })

  it('普通字符键 pass（让输入法/浏览器自己处理）', async () => {
    const { result } = renderMenu([fixedSource('document', [doc('a.pdf')])], '@a')
    // 先等异步源落地：否则用例结束时 setState 落在 act 外，污染输出日志
    await waitFor(() => expect(result.current.options).toHaveLength(1))
    expect(result.current.onKeyDown(key('a'))).toBe('pass')
  })

  it('菜单未开时任何键都 pass（不能拦住正常发送）', () => {
    const { result } = renderMenu([fixedSource('document', [])], '你好')
    expect(result.current.open).toBe(false)
    expect(result.current.onKeyDown(key('Enter'))).toBe('pass')
  })

  it('光标不在 token 里（中间是空白）时菜单关闭', () => {
    const { result } = renderMenu([fixedSource('document', [])], '@起诉 状')
    expect(result.current.open).toBe(false)
  })
})
