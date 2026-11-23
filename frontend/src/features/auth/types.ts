/**
 * auth 域类型：跨模块共享的契约投影与视图形状集中在这里。
 *
 * 只收「被多个模块引用」的类型——实现文件因此不必反过来充当类型入口
 * （`social-api.ts` / `login-methods.ts` / `passkey-api.ts` 仍 re-export 本文件
 * 的对应名字，保持既有 import 路径不变）。
 * 只在单个实现模块内成对使用的类型留在原处：`passkey-coding.ts` 的四个
 * WebAuthn JSON 边界类型与它们的 mapper 同生共死，不搬。
 */
import type { components, operations } from '@/types/api-schema'

/** 登录用户（/organization/me 的精简形状；该端点返回生成物 LawyerOut，这里取消费子集）。
 *  生成物 LawyerOut 的 real_name 为必有（organization 版 ModelSchema 口径），而
 *  store/social 回填等占位对象只有 id/username，real_name 故作可选。头像/真名
 *  供头像位消费（navbar 菜单、AI 对话气泡），未设置时回退名字首字。 */
export type User = Pick<components['schemas']['LawyerOut'], 'id' | 'username' | 'avatar_url'> &
  Partial<Pick<components['schemas']['LawyerOut'], 'real_name'>>

/** 登录入参（POST /token/pair 的 requestBody）。
 *  生成物 schema 名随后端密码绑定改造更新：现为 PasswordBoundTokenObtainPairInputSchema */
export type LoginRequest = components['schemas']['PasswordBoundTokenObtainPairInputSchema']

/** 已启用的社交登录方式（GET /social/providers 的行，生成物 ProviderOut）。
 *  client_config 是渲染所需公开信息（app_id / authorize_url / 二维码尺寸等，
 *  生成物按 dict 收成字符串索引签名），不含密钥；provider-catalog 里为 null
 *  表示该平台尚未配置启用。 */
export type SocialProviderInfo = Omit<components['schemas']['ProviderOut'], 'login_mode'> & {
  /** 覆写收窄：生成物按后端 str 字段声明为裸 string；前端只实现两种渲染
   *  形态，收窄成字面量联合让分派漏分支在编译期暴露（未知值由 login-methods
   *  的 toKind 运行时兜底为 redirect，不会漏处理）。 */
  login_mode: 'redirect' | 'embedded_qr'
}

/** 授权会话（POST /social/{provider}/session 的响应）。
 *  生成物组件名 SessionOut 与 OA 归档等域共用同名单例，为钉死 social 契约
 *  按 operation 投影。success / message 生成物为必有（Schema 带默认值），与
 *  旧手写版的可选不同，以生成物为准——消费方均已做空串兜底。 */
export type SocialSession = operations['apps_social_auth_api_social_auth_api_create_session']['responses'][200]['content']['application/json']

/** 当前用户已绑定的社交账号（GET /social/bindings 的行，生成物 BoundAccountOut） */
export type BoundAccount = components['schemas']['BoundAccountOut']

/** 渲染形态：账密表单 / 内嵌二维码 / 整页跳转授权 */
export type LoginMethodKind = 'password' | 'embedded_qr' | 'redirect'

/** 登录方式：账密、「扫码登录」标签页与每个社交 Provider 的统一视图 */
export interface LoginMethod {
  /** `password` / `qr`（模式级）或 Provider 名（如 `feishu`） */
  id: string
  kind: LoginMethodKind
  label: string
  /** 账密与「扫码登录」标签页没有对应的 Provider */
  provider: SocialProviderInfo | null
}

/** 已注册通行密钥的展示行（不含公钥等内部字段） */
export interface PasskeyCredentialRow {
  id: number
  name: string
  rp_id: string
  created_at: string
  last_used_at: string | null
}
