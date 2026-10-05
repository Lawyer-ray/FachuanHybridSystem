/**
 * WebAuthn 浏览器 API 的编解码层。
 *
 * 后端下发/接收的都是 base64url 字符串（WebAuthn JSON 约定），浏览器
 * navigator.credentials API 需要 ArrayBuffer；本模块是两者唯一的换算边界。
 *
 * 选项/凭据形状用本地最小 interface 而非 DOM lib 生成物：把前后端契约钉死
 * 在自己的类型里，DOM lib 版本差异只在调用 navigator.credentials 的边界
 * 用 cast 吸收（见 toRequestOptions / toCreationOptions 的返回断言）。
 */

/** 后端 register/options 下发的 PublicKeyCredentialCreationOptions JSON */
export interface PasskeyCreationOptionsJSON {
  rp: { id: string; name: string }
  user: { id: string; name: string; displayName: string }
  challenge: string
  pubKeyCredParams: { type: string; alg: number }[]
  timeout?: number
  excludeCredentials?: { id: string; transports?: string[] }[]
  authenticatorSelection?: Record<string, unknown>
  attestation?: string
}

/** 后端 login/options 下发的 PublicKeyCredentialRequestOptions JSON。
 *  认证选项的 rp 字段是扁平的 rpId（注册选项才是 rp: {id, name}）。 */
export interface PasskeyRequestOptionsJSON {
  rpId?: string
  challenge: string
  timeout?: number
  allowCredentials?: { id: string; transports?: string[] }[]
  userVerification?: string
}

/** 提交给后端 register/verify 的浏览器凭据 JSON */
export interface RegistrationResponseJSON {
  id: string
  rawId: string
  type: string
  response: { clientDataJSON: string; attestationObject: string }
}

/** 提交给后端 login/verify 的浏览器凭据 JSON */
export interface AssertionResponseJSON {
  id: string
  rawId: string
  type: string
  response: {
    clientDataJSON: string
    authenticatorData: string
    signature: string
    userHandle: string | null
  }
}

/** ArrayBuffer → base64url（无填充） */
export function bytesToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** base64url → 字节（容错无填充/带填充两种形态）。
 *  返回值钉死 Uint8Array<ArrayBuffer>：DOM 的 BufferSource 只收 ArrayBuffer 视图。 */
export function base64urlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const padding = (4 - (value.length % 4)) % 4
  const binary = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat(padding))
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

/** 浏览器注册结果 → 后端契约 JSON（attestation 只透传必要字段） */
export function credentialToRegistrationJSON(credential: {
  id: string
  rawId: ArrayBuffer
  type: string
  response: { clientDataJSON: ArrayBuffer; attestationObject: ArrayBuffer }
}): RegistrationResponseJSON {
  return {
    id: credential.id,
    rawId: bytesToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bytesToBase64url(credential.response.clientDataJSON),
      attestationObject: bytesToBase64url(credential.response.attestationObject),
    },
  }
}

/** 浏览器断言结果 → 后端契约 JSON（userHandle 空时按 null 透传） */
export function credentialToAssertionJSON(credential: {
  id: string
  rawId: ArrayBuffer
  type: string
  response: {
    clientDataJSON: ArrayBuffer
    authenticatorData: ArrayBuffer
    signature: ArrayBuffer
    userHandle: ArrayBuffer | null
  }
}): AssertionResponseJSON {
  return {
    id: credential.id,
    rawId: bytesToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bytesToBase64url(credential.response.clientDataJSON),
      authenticatorData: bytesToBase64url(credential.response.authenticatorData),
      signature: bytesToBase64url(credential.response.signature),
      userHandle: credential.response.userHandle ? bytesToBase64url(credential.response.userHandle) : null,
    },
  }
}

/** 服务器注册选项 → navigator.credentials.create 入参（base64url → bytes） */
export function toCreationOptions(server: PasskeyCreationOptionsJSON): CredentialCreationOptions {
  const publicKey: PublicKeyCredentialCreationOptions = {
    rp: server.rp,
    user: { ...server.user, id: base64urlToBytes(server.user.id) },
      challenge: base64urlToBytes(server.challenge),
      pubKeyCredParams: server.pubKeyCredParams.map((param) => ({
        type: param.type as PublicKeyCredentialParameters['type'],
        alg: param.alg,
      })),
    timeout: server.timeout,
    excludeCredentials: server.excludeCredentials?.map((cred) => ({
      id: base64urlToBytes(cred.id),
      type: 'public-key',
      transports: cred.transports as AuthenticatorTransport[],
    })),
    authenticatorSelection: server.authenticatorSelection,
    attestation: server.attestation as AttestationConveyancePreference | undefined,
  }
  return { publicKey }
}

/** 服务器登录选项 → navigator.credentials.get 入参 */
export function toRequestOptions(server: PasskeyRequestOptionsJSON): CredentialRequestOptions {
  const publicKey: PublicKeyCredentialRequestOptions = {
    rpId: server.rpId,
    challenge: base64urlToBytes(server.challenge),
    timeout: server.timeout,
    allowCredentials: server.allowCredentials?.map((cred) => ({
      id: base64urlToBytes(cred.id),
      type: 'public-key',
      transports: cred.transports as AuthenticatorTransport[],
    })),
    userVerification: (server.userVerification ?? 'preferred') as UserVerificationRequirement,
  }
  return { publicKey }
}
