/**
 * 登录页。
 *
 * 结构：左侧品牌栏 + 右侧登录卡（窄屏单列）。右侧的登录方式由 login-methods
 * 注册表驱动——账号密码只是其中一种，扫码 / 网页授权都按 kind 派发到对应
 * 渲染器，因此以后新增登录方式不需要改这里的分支结构。
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import './auth.css'
import { useAuth } from './store'
import { socialAuthApi } from './social-api'
import { buildLoginMethods, PASSWORD_METHOD_ID, type LoginMethod } from './login-methods'
import { LoginBrandPanel } from './components/LoginBrandPanel'
import { LoginMethodSwitch } from './components/LoginMethodSwitch'
import { PasswordLoginForm } from './components/PasswordLoginForm'
import { SocialQrPanel } from './components/SocialQrPanel'
import { SocialRedirectPanel } from './components/SocialRedirectPanel'

export function LoginPage() {
  const init = useAuth((s) => s.init)
  const navigate = useNavigate()
  const [methods, setMethods] = useState<LoginMethod[]>(() => buildLoginMethods([]))
  const [activeId, setActiveId] = useState(PASSWORD_METHOD_ID)

  useEffect(() => {
    init()
  }, [init])

  // 已启用的登录方式由后端下发；拉不到就只留账密，不影响登录
  useEffect(() => {
    let alive = true
    void socialAuthApi.listProviders().then((list) => {
      if (alive) setMethods(buildLoginMethods(list))
    })
    return () => {
      alive = false
    }
  }, [])

  const active = methods.find((m) => m.id === activeId) ?? methods[0]

  return (
    <div className="relative flex min-h-screen bg-background">
      <LoginBrandPanel />

      <div className="au-wash flex flex-1 items-center justify-center px-4 py-10">
        <div className="au-rise w-full max-w-[380px]">
          {/* 窄屏没有左栏，品牌信息在卡片上方补一份 */}
          <div className="mb-6 text-center lg:hidden">
            <h1 className="text-[19px] font-semibold tracking-tight">
              法穿 <span className="font-medium text-foreground/70">AI Copilot</span>
            </h1>
            <p className="mt-1 text-[12.5px] text-muted-foreground">一站式律师办案协同平台</p>
          </div>

          <div className="au-glass rounded-2xl p-6">
            {methods.length > 1 && (
              <LoginMethodSwitch methods={methods} activeId={active.id} onChange={setActiveId} />
            )}

            {active.kind === 'password' && (
              <PasswordLoginForm onLoggedIn={() => navigate('/', { replace: true })} />
            )}
            {active.kind === 'embedded_qr' && active.provider && (
              <SocialQrPanel provider={active.provider} />
            )}
            {active.kind === 'redirect' && active.provider && (
              <SocialRedirectPanel provider={active.provider} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
