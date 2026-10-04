import type { components } from '@/types/api-schema'

/** 登录用户（/organization/me 的精简形状；该端点返回生成物 LawyerOut，这里取消费子集）。
 *  生成物 LawyerOut 的 real_name 为必有（organization 版 ModelSchema 口径），而
 *  store/social 回填等占位对象只有 id/username 且本域不消费 real_name，故不取。 */
export type User = Pick<components['schemas']['LawyerOut'], 'id' | 'username'>

/** 登录入参（POST /token/pair 的 requestBody）。
 *  生成物 schema 名随后端密码绑定改造更新：现为 PasswordBoundTokenObtainPairInputSchema */
export type LoginRequest = components['schemas']['PasswordBoundTokenObtainPairInputSchema']
