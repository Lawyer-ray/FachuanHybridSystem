/** 登录用户（/organization/me 的精简形状） */
export interface User {
  id: number
  username: string
  real_name?: string
}

export interface LoginRequest {
  username: string
  password: string
}
