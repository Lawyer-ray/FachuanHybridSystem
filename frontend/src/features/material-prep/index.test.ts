/**
 * material-prep 对外出口单测（node 环境）。
 *
 * 出口只承诺两件事，都写在同一处以防有人「顺手改成静态引」：
 * 1. resetMaterialPrepState 走动态 import（链路带 pdfjs-dist，静态引会把整个
 *    材料预处理域拖进首屏包），调用后阅读器状态真的被清空；
 * 2. 收件箱消息内容仍然经出口对外（home 的收件箱卡免于穿透内部目录）。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { InboxMessageContent, resetMaterialPrepState } from './index'
import { useReader } from './store'

describe('material-prep index 出口', () => {
  beforeEach(() => {
    useReader.getState().resetAll()
  })

  it('resetMaterialPrepState 清空阅读器会话状态（登出换账号不得残留上一位的材料）', async () => {
    useReader.setState({ openId: 42, assignOpen: true, selPages: [{ mi: 0, p: 0 }] })
    expect(useReader.getState().openId).toBe(42)

    await resetMaterialPrepState()

    expect(useReader.getState().openId).toBeNull()
    expect(useReader.getState().assignOpen).toBe(false)
    expect(useReader.getState().selPages).toEqual([])
    expect(useReader.getState().status).toBe('idle')
  })

  it('复用收件箱消息内容组件（home 不穿透内部目录）', () => {
    expect(typeof InboxMessageContent).toBe('function')
  })

  it('resetMaterialPrepState 返回 Promise（调用方可 await，不阻塞渲染）', async () => {
    await expect(resetMaterialPrepState()).resolves.toBeUndefined()
  })
})
