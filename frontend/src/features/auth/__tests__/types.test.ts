/**
 * Auth Types Tests
 * 测试错误代码常量和消息映射的完整性
 */

import { ErrorCodes, errorMessages } from '../types'

describe('Auth ErrorCodes', () => {
  it('defines all expected error codes', () => {
    expect(ErrorCodes.USERNAME_EXISTS).toBe('USERNAME_EXISTS')
    expect(ErrorCodes.INVALID_CREDENTIALS).toBe('INVALID_CREDENTIALS')
    expect(ErrorCodes.ACCOUNT_PENDING).toBe('ACCOUNT_PENDING')
    expect(ErrorCodes.NOT_AUTHENTICATED).toBe('NOT_AUTHENTICATED')
    expect(ErrorCodes.PERMISSION_DENIED).toBe('PERMISSION_DENIED')
    expect(ErrorCodes.USER_NOT_FOUND).toBe('USER_NOT_FOUND')
  })

  it('has exactly 6 error codes', () => {
    expect(Object.keys(ErrorCodes)).toHaveLength(6)
  })
})

describe('Auth errorMessages', () => {
  it('maps every ErrorCodes value to a non-empty string', () => {
    for (const code of Object.values(ErrorCodes)) {
      const msg = errorMessages[code]
      expect(msg).toBeDefined()
      expect(typeof msg).toBe('string')
      expect(msg.length).toBeGreaterThan(0)
    }
  })

  it('has a message for each ErrorCode key', () => {
    expect(Object.keys(errorMessages)).toHaveLength(Object.keys(ErrorCodes).length)
  })

  it('uses Chinese messages', () => {
    expect(errorMessages[ErrorCodes.USERNAME_EXISTS]).toContain('用户名')
    expect(errorMessages[ErrorCodes.INVALID_CREDENTIALS]).toContain('密码')
    expect(errorMessages[ErrorCodes.ACCOUNT_PENDING]).toContain('审批')
    expect(errorMessages[ErrorCodes.NOT_AUTHENTICATED]).toContain('登录')
    expect(errorMessages[ErrorCodes.PERMISSION_DENIED]).toContain('权限')
    expect(errorMessages[ErrorCodes.USER_NOT_FOUND]).toContain('用户')
  })
})
