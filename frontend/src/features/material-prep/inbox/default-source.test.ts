/**
 * 收件箱默认档位（node 环境）。
 *
 * 三条语义，缺一条都会让「进来默认邮箱」在真实使用里变味：
 * 1. 首次进入 = 邮箱（不是「全部」把邮箱与法院送达混成一条流）；
 * 2. 用户点过的档位在本次会话内记住——否则下午都在「一张网」追送达的人，
 *    去项目页看一眼再回来就被弹回邮箱；
 * 3. 程序改档（深链接放开筛选找目标消息）**不写偏好**——写进去就等于把默认值
 *    废掉：这次会话里每次回到收件箱都被钉在「全部」。
 *
 * 记忆是模块级变量（不落 localStorage），所以登出/换账号时必须能清掉，
 * `resetInboxSourcePreference` 就是那条出口。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import {
  DEFAULT_INBOX_SOURCE,
  rememberInboxSource,
  resetInboxSourcePreference,
  resolveInitialInboxSource,
} from './default-source'

beforeEach(() => {
  resetInboxSourcePreference()
})

describe('收件箱默认档位', () => {
  it('首次进入是邮箱，不是全部', () => {
    expect(DEFAULT_INBOX_SOURCE).toBe('imap')
    expect(resolveInitialInboxSource()).toBe('imap')
  })

  it('用户选过的档位在会话内记住', () => {
    rememberInboxSource('court_inbox')
    expect(resolveInitialInboxSource()).toBe('court_inbox')
  })

  it('再次选择会覆盖上一次', () => {
    rememberInboxSource('court_inbox')
    rememberInboxSource('imap')
    expect(resolveInitialInboxSource()).toBe('imap')
  })

  it('清空记忆后回到默认值（登出/换账号）', () => {
    rememberInboxSource('court_inbox')
    resetInboxSourcePreference()
    expect(resolveInitialInboxSource()).toBe('imap')
  })
})
