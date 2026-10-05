/**
 * 绑定某个平台的弹窗。
 *
 * 按 provider 的 login_mode 选渲染方式：内嵌二维码（飞书）或整页跳转（谷歌等）。
 * 与登录页的区别只有一处——授权会话走 bind-session，授权完成后后端把身份
 * 关联到当前登录用户，不会新建律师账号。
 */
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { socialBindingsApi, type SocialProviderInfo } from '../social-api'
/* 弹窗内嵌 SocialQrPanel / SocialRedirectPanel，其 fc-* 样式在 login.css 家族（表单/面板两层，登录页共用） */
import '../login.css'
import { SocialQrPanel } from './SocialQrPanel'
import { SocialRedirectPanel } from './SocialRedirectPanel'

interface Props {
  provider: SocialProviderInfo | null
  onOpenChange: (open: boolean) => void
}

export function BindProviderDialog({ provider, onOpenChange }: Props) {
  const name = provider?.display_name ?? ''
  return (
    <Dialog open={provider !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[380px]">
        <DialogHeader>
          <DialogTitle>绑定{name}</DialogTitle>
          <DialogDescription>
            绑定后可在登录页直接用{name}登录。一个平台只能绑定一个账号，换绑需先解绑。
          </DialogDescription>
        </DialogHeader>
        {provider &&
          (provider.login_mode === 'embedded_qr' ? (
            <SocialQrPanel
              provider={provider}
              // 直接传方法引用：这里若写成箭头函数，每次渲染都会换新引用，
              // 触发 SocialQrPanel 的 boot 重新执行，二维码会无限重建。
              createSession={socialBindingsApi.createBindSession}
              containerId="social-bind-qr-container"
            />
          ) : (
            <SocialRedirectPanel provider={provider} createSession={socialBindingsApi.createBindSession} />
          ))}
      </DialogContent>
    </Dialog>
  )
}
