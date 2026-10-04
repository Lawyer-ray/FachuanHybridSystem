/**
 * 个人设置 · 账号绑定。
 *
 * 登录只放行「已绑定」的社交身份（不自动建号），所以这里是社交账号接入系统
 * 的唯一入口：先用账号密码登录，再在这里绑定平台账号。
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router'
import { parseISO } from 'date-fns'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { AppNavbar } from '@/components/shared/AppNavbar'
import { PageFade } from '@/components/shared/PageFade'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { socialBindingsApi, type BoundAccount, type SocialProviderInfo } from './social-api'
import { BINDINGS_KEY, CATALOG_KEY } from './constants'
import { BindProviderDialog } from './components/BindProviderDialog'

interface Row {
  provider: SocialProviderInfo
  account: BoundAccount | null
}

function boundAtText(iso: string): string {
  // parseISO 而非 new Date：naive / date-only 串不会被按 UTC 零点解析偏移
  const date = parseISO(iso)
  return Number.isNaN(date.getTime()) ? '' : `绑定于 ${date.toLocaleDateString('zh-CN')}`
}

export function BindingsPage() {
  const queryClient = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const [bindingProvider, setBindingProvider] = useState<SocialProviderInfo | null>(null)
  const [unbindTarget, setUnbindTarget] = useState<BoundAccount | null>(null)

  const bindingsQuery = useQuery({ queryKey: BINDINGS_KEY, queryFn: () => socialBindingsApi.list() })
  const catalogQuery = useQuery({ queryKey: CATALOG_KEY, queryFn: () => socialBindingsApi.catalog(), staleTime: 60_000 })

  // 回调页带 bound=<provider> 回来即绑定成功：提示一次并把标记从 URL 清掉，
  // 否则刷新页面会重复弹提示
  const boundParam = new URLSearchParams(location.search).get('bound')
  useEffect(() => {
    if (!boundParam) return
    const params = new URLSearchParams(location.search)
    params.delete('bound')
    const search = params.toString()
    void navigate({ pathname: location.pathname, search: search ? `?${search}` : '' }, { replace: true })
    toast.success('绑定成功，现在可以用它登录了')
    void queryClient.invalidateQueries({ queryKey: BINDINGS_KEY })
  }, [boundParam, location.pathname, location.search, navigate, queryClient])

  const unbind = useMutation({
    mutationFn: async (provider: string) => {
      const res = await socialBindingsApi.unbind(provider)
      if (!res.success) throw new Error(res.message || '解绑失败')
      return res
    },
    onSuccess: () => {
      setUnbindTarget(null)
      toast.success('已解绑')
      void queryClient.invalidateQueries({ queryKey: BINDINGS_KEY })
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : '解绑失败，请稍后重试'),
  })

  const rows = useMemo<Row[]>(() => {
    const byProvider = new Map((bindingsQuery.data ?? []).map((a) => [a.provider, a]))
    return (catalogQuery.data ?? []).map((provider) => ({
      provider,
      account: byProvider.get(provider.name) ?? null,
    }))
  }, [bindingsQuery.data, catalogQuery.data])

  const loading = bindingsQuery.isLoading || catalogQuery.isLoading
  // 接口失败必须显式报错：否则空列表会被当成「暂无可绑定的登录方式」，
  // 把请求路径写错这类问题藏起来（曾经就把 /settings/bindings 下的路径解析错误盖住了）
  const failed = bindingsQuery.isError || catalogQuery.isError

  return (
    <div className="min-h-screen bg-background">
      <AppNavbar onNotify={(msg) => toast.info(msg)} />

      <PageFade>
        <main className="mx-auto max-w-[720px] px-[32px] pt-[26px] pb-20 max-[760px]:px-[14px] max-[760px]:pt-[18px]">
          <h1 className="text-[22px] font-bold tracking-[-0.02em]">账号绑定</h1>
          <p className="mt-2 text-[12.5px] leading-[1.8] text-muted-foreground">
            绑定后即可在登录页用对应平台直接登录，无需输入密码。未绑定的社交账号无法登录，
            系统不会自动为其创建律师账号。
          </p>

          <div className="mt-5 overflow-hidden rounded-xl border bg-card">
            {loading && (
              <div className="flex items-center justify-center gap-2 py-10 text-[12.5px] text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                正在加载…
              </div>
            )}

            {!loading && failed && (
              <div className="flex flex-col items-center gap-3 py-10">
                <p className="text-[12.5px] text-muted-foreground">加载绑定信息失败，请检查网络后重试</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    void bindingsQuery.refetch()
                    void catalogQuery.refetch()
                  }}
                >
                  重新加载
                </Button>
              </div>
            )}

            {!loading && !failed && rows.length === 0 && (
              <p className="py-10 text-center text-[12.5px] text-muted-foreground">暂无可绑定的登录方式</p>
            )}

            {!loading &&
              !failed &&
              rows.map(({ provider, account }, index) => {
                // client_config 为 null 表示平台尚未配置启用，只展示灰态，不给绑定入口
                const available = provider.client_config !== null
                return (
                  <div
                    key={provider.name}
                    className={`flex items-center gap-3 px-5 py-[14px] ${
                      index > 0 ? 'border-t border-border' : ''
                    }`}
                  >
                    <span className="flex size-9 flex-none items-center justify-center rounded-[10px] bg-secondary text-[13px] font-semibold text-secondary-foreground">
                      {provider.display_name.slice(0, 1) || provider.name.slice(0, 1)}
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="text-[13.5px] font-medium">{provider.display_name}</div>
                      <div className="mt-[2px] truncate text-[11.5px] text-muted-foreground">
                        {account
                          ? [account.display_name || '已绑定', boundAtText(account.bound_at)].filter(Boolean).join(' · ')
                          : available
                            ? '未绑定'
                            : '该登录方式暂未开放'}
                      </div>
                    </div>

                    {account ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={unbind.isPending}
                        onClick={() => setUnbindTarget(account)}
                      >
                        解绑
                      </Button>
                    ) : available ? (
                      <Button type="button" size="sm" onClick={() => setBindingProvider(provider)}>
                        绑定
                      </Button>
                    ) : null}
                  </div>
                )
              })}
          </div>

          <p className="mt-3 text-[11.5px] leading-[1.7] text-muted-foreground">
            换绑同一平台的其他账号：先解绑当前账号，再绑定新的。解绑期间该平台无法登录，可继续用账号密码登录。
          </p>
        </main>
      </PageFade>

      <BindProviderDialog
        provider={bindingProvider}
        onOpenChange={(open) => {
          if (!open) setBindingProvider(null)
        }}
      />

      <AlertDialog
        open={unbindTarget !== null}
        onOpenChange={(open) => {
          if (!open) setUnbindTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认解绑{unbindTarget?.provider ?? ''}？</AlertDialogTitle>
            <AlertDialogDescription>
              解绑后该账号将无法登录本系统，需要重新绑定。账号密码登录不受影响。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (unbindTarget) unbind.mutate(unbindTarget.provider)
              }}
            >
              解绑
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
