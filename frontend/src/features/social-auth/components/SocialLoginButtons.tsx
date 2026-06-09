/* eslint-disable react-refresh/only-export-components */

import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'

import { socialAuthApi } from '../api'
import { Button } from '@/components/ui/button'
import { API_BASE_URL } from '@/lib/api'

const PROVIDER_ICONS: Record<string, string> = {
  wechat: '🟢',
  google: '🔵',
  feishu: '🟦',
  dingtalk: '🔷',
}

function SocialLoginButtons() {
  const { data, isLoading } = useQuery({
    queryKey: ['socialProviders'],
    queryFn: () => socialAuthApi.getProviders(),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-2">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!data?.providers?.length) return null

  return (
    <div className="space-y-4">
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-card px-2 text-muted-foreground">或者</span>
        </div>
      </div>
      {data.providers.map((provider) => (
        <Button
          key={provider.name}
          variant="outline"
          className="w-full"
          onClick={() => {
            window.location.href = `${API_BASE_URL.replace(/\/api\/v1\/?$/, '')}/social/${provider.name}/login/`
          }}
        >
          <span className="mr-2">{PROVIDER_ICONS[provider.name] || '🔗'}</span>
          {provider.display_name}登录
        </Button>
      ))}
    </div>
  )
}

export { SocialLoginButtons }
