import { describe, expect, it } from 'vitest'

import { oldestDbId, parseMessageId, ratableMessageId } from './message-id'

describe('parseMessageId', () => {
  it('db- 前缀解析为主键', () => {
    expect(parseMessageId('db-12')).toBe(12)
    expect(parseMessageId('db-1')).toBe(1)
  })

  it('实时气泡（local-）不可解析 —— 回归：旧代码 Number(local-1.slice(3)) 得到 NaN', () => {
    expect(parseMessageId('local-1')).toBeNull()
    expect(parseMessageId('local-27')).toBeNull()
  })

  it('坏前缀/非数字/0 都不解析', () => {
    expect(parseMessageId('db-abc')).toBeNull()
    expect(parseMessageId('db-0')).toBeNull()
    expect(parseMessageId('db--3')).toBeNull()
    expect(parseMessageId('')).toBeNull()
    expect(parseMessageId('12')).toBeNull()
  })
})

describe('ratableMessageId', () => {
  it('serverId 优先（历史回放显式带上）', () => {
    expect(ratableMessageId({ id: 'local-3', serverId: 9 })).toBe(9)
  })

  it('无 serverId 时从 db- id 反推', () => {
    expect(ratableMessageId({ id: 'db-7' })).toBe(7)
  })

  it('实时气泡不可评分（UI 据此置灰）', () => {
    expect(ratableMessageId({ id: 'local-5' })).toBeNull()
  })

  it('非法 serverId 不采用', () => {
    expect(ratableMessageId({ id: 'local-5', serverId: 0 })).toBeNull()
    expect(ratableMessageId({ id: 'local-5', serverId: -2 })).toBeNull()
  })
})

describe('oldestDbId', () => {
  it('取第一条已落库消息（跳过实时气泡）', () => {
    expect(oldestDbId([{ id: 'local-9' }, { id: 'db-31' }, { id: 'db-40' }])).toBe(31)
  })

  it('全部未落库时返回 null（调用方置 noMoreHistory）', () => {
    expect(oldestDbId([{ id: 'local-1' }, { id: 'local-2' }])).toBeNull()
    expect(oldestDbId([])).toBeNull()
  })
})
