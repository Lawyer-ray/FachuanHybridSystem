/**
 * Auth Feature Module
 * 认证模块统一导出
 *
 * 导出所有认证相关的组件、hooks、类型、schemas 和 API
 */

// Components
export { LoginForm } from './components/LoginForm'
export { RegisterForm } from './components/RegisterForm'
export { PendingApproval } from './components/PendingApproval'
export { ThemeToggle } from './components/ThemeToggle'

// Hooks
export { useAuth } from './hooks/use-auth'
export { useLoginMutation, useRegisterMutation, useLogoutMutation } from './hooks/use-auth-mutations'

// Types
export * from './types'

// Schemas
export { loginSchema, registerSchema } from './schemas'
export type { LoginFormData, RegisterFormData } from './schemas'

// API
export { authApi } from './api'
