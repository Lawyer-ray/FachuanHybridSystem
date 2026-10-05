/**
 * 个人设置 → 账号绑定页的「通行密钥」区块。
 *
 * 列表（名称/注册域/最近使用）+ 添加（Touch ID 注册流程）+ 重命名（行内
 * 编辑）+ 删除（吊销该设备）。与社交绑定并列：两者共同构成「无密码登录
 * 手段」，但通行密钥不依赖任何第三方平台。
 *
 * 重要约束（区块底部文案同步提示用户）：WebAuthn 凭据按注册时的域名隔离，
 * localhost 与 app.xlaw.top 各自独立，注册与登录必须用同一域名访问。
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
import { passkeyApi, PASSKEY_CREDENTIALS_KEY, type PasskeyCredentialRow } from '../passkey-api'
import { credentialToRegistrationJSON, toCreationOptions } from '../passkey-coding'

function registeredAtText(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : `注册于 ${date.toLocaleDateString('zh-CN')}`
}

function usedAtText(iso: string | null): string {
  if (!iso) return '从未使用'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : `最近使用 ${date.toLocaleDateString('zh-CN')}`
}

export function PasskeySection() {
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState('')
  const [supported, setSupported] = useState(false)
  const [renamingId, setRenamingId] = useState<number | null>(null)
  const [draftName, setDraftName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<PasskeyCredentialRow | null>(null)

  const credentialsQuery = useQuery({
    queryKey: PASSKEY_CREDENTIALS_KEY,
    queryFn: () => passkeyApi.list(),
  })
  const rows = credentialsQuery.data ?? []

  useEffect(() => {
    let mounted = true
    // 有平台认证器（Touch ID 等）才给添加入口；列表仍展示（其他设备可注册过）
    const check = async () => {
      if (typeof window === 'undefined' || !window.PublicKeyCredential) return false
      try {
        return await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
      } catch {
        return false
      }
    }
    void check().then((ok) => {
      if (mounted) setSupported(ok)
    })
    return () => {
      mounted = false
    }
  }, [])

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: PASSKEY_CREDENTIALS_KEY })

  const add = async () => {
    setAdding(true)
    setAddError('')
    try {
      const options = await passkeyApi.registerOptions()
      const credential = await navigator.credentials.create(toCreationOptions(options))
      if (!credential) throw new Error('创建通行密钥被取消')
      await passkeyApi.registerVerify(
        credentialToRegistrationJSON(
          credential as unknown as Parameters<typeof credentialToRegistrationJSON>[0],
        ),
      )
      toast.success('通行密钥已添加')
      invalidate()
    } catch (err) {
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        // 用户取消 Touch ID 属正常操作，不算错误
        return
      }
      setAddError(err instanceof Error ? err.message : '通行密钥添加失败，请稍后重试')
    } finally {
      setAdding(false)
    }
  }

  const rename = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => passkeyApi.rename(id, name),
    onSuccess: () => {
      setRenamingId(null)
      toast.success('已重命名')
      invalidate()
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : '重命名失败'),
  })

  const remove = useMutation({
    mutationFn: (id: number) => passkeyApi.remove(id),
    onSuccess: () => {
      setDeleteTarget(null)
      toast.success('已删除，该设备无法再用通行密钥登录')
      invalidate()
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : '删除失败'),
  })

  return (
    <section className="mt-8">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold">
          <KeyRound className="size-4 text-muted-foreground" />
          通行密钥
        </h2>
        {supported && (
          <Button type="button" size="sm" disabled={adding} onClick={() => void add()}>
            {adding ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                等待验证…
              </>
            ) : (
              '添加通行密钥'
            )}
          </Button>
        )}
      </div>
      <p className="mt-2 text-[12.5px] leading-[1.8] text-muted-foreground">
        通行密钥用 Touch ID / Windows Hello 代替密码登录，私钥只存在于你的设备里。
        凭据按注册时的域名隔离：本机用 localhost 注册的密钥，换用其他域名访问时需重新添加。
      </p>

      {credentialsQuery.isLoading && (
        <div className="mt-4 flex items-center justify-center gap-2 rounded-xl border bg-card py-8 text-[12.5px] text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          正在加载…
        </div>
      )}

      {credentialsQuery.isError && (
        <div className="mt-4 flex flex-col items-center gap-3 rounded-xl border bg-card py-8">
          <p className="text-[12.5px] text-muted-foreground">加载通行密钥失败，请检查网络后重试</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void credentialsQuery.refetch()}
          >
            重新加载
          </Button>
        </div>
      )}

      {!credentialsQuery.isLoading && !credentialsQuery.isError && rows.length === 0 && (
        <div className="mt-4 rounded-xl border bg-card px-5 py-8 text-center text-[12.5px] text-muted-foreground">
          {supported ? '还没有通行密钥，点右上角「添加通行密钥」用本设备创建' : '当前浏览器不支持通行密钥'}
        </div>
      )}

      {!credentialsQuery.isLoading && !credentialsQuery.isError && rows.length > 0 && (
        <div className="mt-4 overflow-hidden rounded-xl border bg-card">
          {rows.map((row, index) => (
            <div
              key={row.id}
              className={`flex items-center gap-3 px-5 py-[14px] ${index > 0 ? 'border-t border-border' : ''}`}
            >
              <div className="min-w-0 flex-1">
                {renamingId === row.id ? (
                  <Input
                    autoFocus
                    value={draftName}
                    onChange={(event) => setDraftName(event.target.value)}
                    onBlur={() => {
                      const name = draftName.trim()
                      if (name && name !== row.name) rename.mutate({ id: row.id, name })
                      else setRenamingId(null)
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') event.currentTarget.blur()
                      if (event.key === 'Escape') setRenamingId(null)
                    }}
                    className="h-7 max-w-[240px] text-[13px]"
                  />
                ) : (
                  <div className="text-[13.5px] font-medium">{row.name}</div>
                )}
                <div className="mt-[2px] truncate text-[11.5px] text-muted-foreground">
                  {[registeredAtText(row.created_at), usedAtText(row.last_used_at), row.rp_id]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setRenamingId(row.id)
                  setDraftName(row.name)
                }}
              >
                重命名
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setDeleteTarget(row)}>
                删除
              </Button>
            </div>
          ))}
        </div>
      )}

      {addError && <p className="mt-3 text-[12px] text-destructive">{addError}</p>}

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除通行密钥「{deleteTarget?.name ?? ''}」？</AlertDialogTitle>
            <AlertDialogDescription>
              删除后该设备将无法再用通行密钥登录本系统，需要重新注册。账号密码与其他登录方式不受影响。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleteTarget) remove.mutate(deleteTarget.id)
              }}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
