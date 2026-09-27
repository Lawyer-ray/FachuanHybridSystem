/**
 * 登录页。
 *
 * 视觉：编辑 / 时装杂志风（近黑画布 + 单色 + 黄铜点缀），样式集中在 auth.css，
 * 刻意不用模糊光斑与玻璃拟态。本页固定深色，不跟随全局明暗主题。
 *
 * 结构：品牌栏 + 表单栏（窄屏单列）+ 底部走马灯。表单栏的登录方式由
 * login-methods 注册表驱动——账号密码只是其中一种，扫码 / 网页授权都按 kind
 * 派发到对应渲染器，因此以后新增登录方式不需要改这里的分支结构。
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

/** 底部走马灯内容：能力关键词，纯装饰 */
const TICKER = ['案件管理', '文书生成', '合同审查', '材料预处理', '法律检索', 'OA 立案', '财务台账']

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
    <div className="fc-auth">
      <div aria-hidden className="fc-grain" />

      <div className="fc-body">
        <LoginBrandPanel />

        <main className="fc-form">
          <div className="fc-form__inner">
            {/* 窄屏没有品牌栏，标识在这里补一行 */}
            <div className="fc-form__mobile-mark">
              <span className="fc-mark">法穿</span>
              <span className="fc-mark__meta">AI Copilot</span>
            </div>

            <p className="fc-eyebrow">登录 / Sign in</p>
            <h2 className="fc-form__title">欢迎回来</h2>
            <p className="fc-form__sub">使用账号密码，或已绑定的社交身份登录。</p>

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

            <p className="fc-form__legal">
              仅限授权用户使用。扫码登录需先在「账号绑定」中完成社交身份绑定。
            </p>
          </div>
        </main>
      </div>

      {/* 走马灯：内容渲染两遍，配合 translateX(-50%) 无缝循环 */}
      <div aria-hidden className="fc-ticker">
        <div className="fc-ticker__track">
          {[0, 1].map((copy) => (
            <div className="fc-ticker__item" key={copy}>
              {TICKER.map((word) => (
                <span key={word}>{word}</span>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
