import type { components } from '@/types/api-schema'

/** 登录用户（/organization/me 的精简形状；该端点返回生成物 LawyerOut，这里取消费子集）。
 *  生成物 LawyerOut 的 real_name 为必有（organization 版 ModelSchema 口径），而
 *  store/social 回填等占位对象只有 id/username，real_name 故作可选。头像/真名
 *  供头像位消费（navbar 菜单、AI 对话气泡），未设置时回退名字首字。 */
export type User = Pick<components['schemas']['LawyerOut'], 'id' | 'username' | 'avatar_url'> &
  Partial<Pick<components['schemas']['LawyerOut'], 'real_name'>>

/** 登录入参（POST /token/pair 的 requestBody）。
 *  生成物 schema 名随后端密码绑定改造更新：现为 PasswordBoundTokenObtainPairInputSchema */
export type LoginRequest = components['schemas']['PasswordBoundTokenObtainPairInputSchema']
