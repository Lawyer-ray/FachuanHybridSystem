export interface SocialProviderInfo {
  name: string
  display_name: string
  client_config: Record<string, string> | null
}

export interface ProvidersListResponse {
  providers: SocialProviderInfo[]
}

export interface TokenExchangeResponse {
  success: boolean
  access: string
  refresh: string
  user_id: number | null
  username: string
  message: string
}
