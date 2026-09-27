import { describe, expect, it } from 'vitest'
import { resolveCallbackError, sanitizeRedirect } from './social-callback-domain'
import { SOCIAL_LOGIN_ERROR_TEXT } from './social-types'

describe('sanitizeRedirect', () => {
  it('放行站内相对路径', () => {
    expect(sanitizeRedirect('/')).toBe('/')
    expect(sanitizeRedirect('/material-prep')).toBe('/material-prep')
    expect(sanitizeRedirect('/material-prep/abc-123')).toBe('/material-prep/abc-123')
  })

  it('放行带 query 的相对路径', () => {
    expect(sanitizeRedirect('/search?q=test&sort=desc')).toBe('/search?q=test&sort=desc')
  })

  it('拒绝协议相对 URL（浏览器会当绝对地址）', () => {
    expect(sanitizeRedirect('//evil.com')).toBe('/')
    expect(sanitizeRedirect('//evil.com/path')).toBe('/')
  })

  it('拒绝带协议的绝对地址', () => {
    expect(sanitizeRedirect('https://evil.com')).toBe('/')
    expect(sanitizeRedirect('http://evil.com/path')).toBe('/')
  })

  it('拒绝危险 scheme', () => {
    expect(sanitizeRedirect('javascript:alert(1)')).toBe('/')
    expect(sanitizeRedirect('data:text/html,<script>')).toBe('/')
  })

  it('空值回落首页', () => {
    expect(sanitizeRedirect(null)).toBe('/')
    expect(sanitizeRedirect('')).toBe('/')
  })
})

describe('resolveCallbackError', () => {
  it('已知错误码映射为可读文案', () => {
    expect(resolveCallbackError('state_expired')).toBe(SOCIAL_LOGIN_ERROR_TEXT.state_expired)
    expect(resolveCallbackError('provider_denied')).toBe(SOCIAL_LOGIN_ERROR_TEXT.provider_denied)
  })

  it('空错误码返回空串（供调用方区分"没报错"）', () => {
    expect(resolveCallbackError(null)).toBe('')
    expect(resolveCallbackError('')).toBe('')
  })

  it('未知错误码归一为通用失败，不透出后端细节', () => {
    expect(resolveCallbackError('some_internal_traceback_xyz')).toBe(SOCIAL_LOGIN_ERROR_TEXT.exchange_failed)
  })

  it('所有文案都非空', () => {
    for (const [code, text] of Object.entries(SOCIAL_LOGIN_ERROR_TEXT)) {
      expect(text.length, code).toBeGreaterThan(0)
    }
  })
})
