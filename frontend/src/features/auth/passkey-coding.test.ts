/**
 * passkey-coding 纯函数测试：base64url 编解码、服务器选项 → 浏览器入参映射、
 * 浏览器凭据 → 后端契约 JSON 映射（userHandle 空值、多字段透传）。
 */
import {
  base64urlToBytes,
  bytesToBase64url,
  credentialToAssertionJSON,
  credentialToRegistrationJSON,
  toCreationOptions,
  toRequestOptions,
} from './passkey-coding'

describe('base64url 编解码', () => {
  it('已知向量：Hello → SGVsbG8（无填充）', () => {
    expect(bytesToBase64url(new TextEncoder().encode('Hello').buffer as ArrayBuffer)).toBe('SGVsbG8')
  })

  it('roundtrip 还原原字节', () => {
    const raw = new Uint8Array([0, 1, 2, 250, 251, 255])
    const encoded = bytesToBase64url(raw.buffer as ArrayBuffer)
    expect(Array.from(base64urlToBytes(encoded))).toEqual(Array.from(raw))
  })

  it('解码容错带填充的输入', () => {
    expect(Array.from(base64urlToBytes('SGVsbG8='))).toEqual(Array.from(new TextEncoder().encode('Hello')))
  })

  it('URL 安全字母表：+/ 被替换为 -_', () => {
    // 字节 0xFB 0xEF 的传统 base64 含 + 和 /
    const encoded = bytesToBase64url(new Uint8Array([251, 239]).buffer as ArrayBuffer)
    expect(encoded).not.toMatch(/[+/=]/)
    expect(Array.from(base64urlToBytes(encoded))).toEqual([251, 239])
  })
})

describe('toRequestOptions（登录选项）', () => {
  it('challenge/rpId 正确映射，allowCredentials 转字节', () => {
    const result = toRequestOptions({
      rpId: 'localhost',
      challenge: 'NDI',
      timeout: 60_000,
      userVerification: 'preferred',
      allowCredentials: [{ id: 'NDI', transports: ['internal'] }],
    })
    const publicKey = result.publicKey!
    expect(publicKey.rpId).toBe('localhost')
    expect(Array.from(publicKey.challenge as Uint8Array)).toEqual([52, 50])
    expect(publicKey.allowCredentials).toHaveLength(1)
    expect(publicKey.userVerification).toBe('preferred')
  })
})

describe('toCreationOptions（注册选项）', () => {
  it('user.id 转字节，excludeCredentials 转字节', () => {
    const result = toCreationOptions({
      rp: { id: 'localhost', name: '法穿 SI Copilot' },
      user: { id: 'NDI', name: 'u1', displayName: '张三' },
      challenge: 'NDI',
      pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
      excludeCredentials: [{ id: 'NDI' }],
      authenticatorSelection: { residentKey: 'preferred' },
      attestation: 'none',
    })
    const publicKey = result.publicKey!
    expect(publicKey.rp).toEqual({ id: 'localhost', name: '法穿 SI Copilot' })
    expect(Array.from(publicKey.user.id as Uint8Array)).toEqual([52, 50])
    expect(publicKey.pubKeyCredParams).toEqual([{ type: 'public-key', alg: -7 }])
    expect(publicKey.excludeCredentials).toHaveLength(1)
    expect(publicKey.authenticatorSelection).toEqual({ residentKey: 'preferred' })
  })
})

describe('浏览器凭据 → 后端 JSON', () => {
  const encoder = new TextEncoder()

  it('注册凭据：attestation 必要字段转 base64url', () => {
    const json = credentialToRegistrationJSON({
      id: 'cred-id',
      rawId: encoder.encode('raw').buffer as ArrayBuffer,
      type: 'public-key',
      response: {
        clientDataJSON: encoder.encode('{}').buffer as ArrayBuffer,
        attestationObject: encoder.encode('att').buffer as ArrayBuffer,
      },
    })
    expect(json).toEqual({
      id: 'cred-id',
      rawId: 'cmF3',
      type: 'public-key',
      response: { clientDataJSON: 'e30', attestationObject: 'YXR0' },
    })
  })

  it('断言凭据：userHandle 为空时按 null 透传', () => {
    const json = credentialToAssertionJSON({
      id: 'cred-id',
      rawId: encoder.encode('raw').buffer as ArrayBuffer,
      type: 'public-key',
      response: {
        clientDataJSON: encoder.encode('{}').buffer as ArrayBuffer,
        authenticatorData: encoder.encode('auth').buffer as ArrayBuffer,
        signature: encoder.encode('sig').buffer as ArrayBuffer,
        userHandle: null,
      },
    })
    expect(json.response.userHandle).toBeNull()
    expect(json.response.authenticatorData).toBe('YXV0aA')
    expect(json.response.signature).toBe('c2ln')
  })

  it('断言凭据：userHandle 有值时编码', () => {
    const json = credentialToAssertionJSON({
      id: 'cred-id',
      rawId: encoder.encode('raw').buffer as ArrayBuffer,
      type: 'public-key',
      response: {
        clientDataJSON: encoder.encode('{}').buffer as ArrayBuffer,
        authenticatorData: encoder.encode('auth').buffer as ArrayBuffer,
        signature: encoder.encode('sig').buffer as ArrayBuffer,
        userHandle: encoder.encode('42').buffer as ArrayBuffer,
      },
    })
    expect(json.response.userHandle).toBe('NDI')
  })
})
