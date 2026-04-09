/**
 * Auth Feature Types
 * 认证模块类型定义
 */

/**
 * 用户信息
 */
export interface User {
  id: number
  username: string
  real_name: string | null
  phone: string | null
  is_admin: boolean
  is_active: boolean
}

/**
 * 登录请求
 */
export interface LoginRequest {
  username: string
  password: string
}

/**
 * 登录响应
 */
export interface LoginResponse {
  success: boolean
  user: User
  access: string
  refresh: string
}

/**
 * JWT Token Pair 响应
 */
export interface TokenPairResponse {
  access: string
  refresh: string
}

/**
 * Token 刷新响应
 */
export interface TokenRefreshResponse {
  access: string
}

/**
 * 注册请求
 */
export interface RegisterRequest {
  username: string
  password: string
  real_name: string
  phone?: string
}

/**
 * 注册响应
 */
export interface RegisterResponse {
  success: boolean
  user: User
  requires_approval: boolean
  message: string
}

/**
 * 待审批用户
 */
export interface PendingUser {
  id: number
  username: string
  real_name: string | null
  phone: string | null
  created_at: string | null
}

/**
 * 审批结果响应
 */
export interface ApprovalResponse {
  success: boolean
  message: string
}

/**
 * API 错误响应
 */
export interface ApiError {
  code: string
  message: string
  errors?: Record<string, string>
}

/**
 * 错误代码枚举
 */
export const ErrorCodes = {
  USERNAME_EXISTS: 'USERNAME_EXISTS',
  INVALID_CREDENTIALS: 'INVALID_CREDENTIALS',
  ACCOUNT_PENDING: 'ACCOUNT_PENDING',
  NOT_AUTHENTICATED: 'NOT_AUTHENTICATED',
  PERMISSION_DENIED: 'PERMISSION_DENIED',
  USER_NOT_FOUND: 'USER_NOT_FOUND',
} as const

/**
 * 错误消息映射
 */
export const errorMessages: Record<string, string> = {
  [ErrorCodes.USERNAME_EXISTS]: '用户名已存在，请更换用户名',
  [ErrorCodes.INVALID_CREDENTIALS]: '用户名或密码错误',
  [ErrorCodes.ACCOUNT_PENDING]: '账号待审批，请联系管理员',
  [ErrorCodes.NOT_AUTHENTICATED]: '请先登录',
  [ErrorCodes.PERMISSION_DENIED]: '权限不足',
  [ErrorCodes.USER_NOT_FOUND]: '用户不存在',
}
