import type { components } from '@/types/api-schema'

/** 登录用户（/organization/me 的精简形状；该端点返回生成物 LawyerOut，这里取消费子集） */
export type User = Pick<components['schemas']['LawyerOut'], 'id' | 'username' | 'real_name'>

/** 登录入参（POST /token/pair 的 requestBody，生成物 TokenObtainPairInputSchema） */
export type LoginRequest = components['schemas']['TokenObtainPairInputSchema']
