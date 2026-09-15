export interface User {
  id: number
  username: string
  real_name?: string
  [k: string]: unknown
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  success: boolean
  user?: User
  message?: string
}

export interface TokenPair {
  access: string
  refresh: string
}
