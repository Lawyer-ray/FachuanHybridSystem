/**
 * 登录页。
 *
 * 视觉：编辑 / 时装杂志风（近黑画布 + 单色 + 黄铜点缀），样式集中在 auth.css，
 * 刻意不用模糊光斑与玻璃拟态。本页固定深色，不跟随全局明暗主题。
 *
 * 结构（双栏 + 走马灯）：
 * - 品牌栏 = LoginBrandPanel（眉标 / 元信息带 / 主张 / 引言 / 目录）
 * - 表单栏 = 顶部章节带 + 居中的登录表单 + 底部章节带 + 大幅背景水印
 *   表单栏里再细分：登录方式由 login-methods 派发到 PasswordForm / QrPanel / RedirectPanel，
 *   因此新增登录方式不需要改这里的分支结构。
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import './auth.css'
import { socialAuthApi, SOCIAL_PROVIDERS_KEY } from './social-api'
import { buildLoginMethods, PASSWORD_METHOD_ID } from './login-methods'
import { LoginBrandPanel } from './components/LoginBrandPanel'
import { LoginMethodSwitch } from './components/LoginMethodSwitch'
import { PasswordLoginForm } from './components/PasswordLoginForm'
import { SocialQrPanel } from './components/SocialQrPanel'
import { SocialRedirectPanel } from './components/SocialRedirectPanel'

/** 底部走马灯内容：能力关键词，纯装饰 */
const TICKER = ['案件管理', '文书生成', '合同审查', '材料预处理', '法律检索', 'OA 立案', '财务台账']

export function LoginPage() {
  const navigate = useNavigate()
  const [activeId, setActiveId] = useState(PASSWORD_METHOD_ID)

  // 已启用的登录方式由后端下发；走 react-query 带缓存（此前手写 effect，
  // 每次进登录页都重新请求且无失败痕迹）。拉不到就只留账密，不影响登录。
  const { data: providers = [] } = useQuery({
    queryKey: SOCIAL_PROVIDERS_KEY,
    queryFn: () => socialAuthApi.listProviders(),
    staleTime: 5 * 60_000,
  })
  // 推断保留 NonEmptyArray（buildLoginMethods 恒非空），active 因此不需要判空
  const methods = useMemo(() => buildLoginMethods(providers), [providers])

  const active = methods.find((m) => m.id === activeId) ?? methods[0]

  return (
    <div className="fc-auth">
      <div aria-hidden className="fc-grain" />

      <div className="fc-body">
        <LoginBrandPanel />

        <main className="fc-form">
          {/* 表单竖直居中：不同高度的内容都能稳在视觉中线上 */}
          <div className="fc-form__middle">
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
                <PasswordLoginForm onLoggedIn={() => { void navigate('/', { replace: true }) }} />
              )}
              {active.kind === 'embedded_qr' && active.provider && (
                <SocialQrPanel provider={active.provider} />
              )}
              {active.kind === 'redirect' && active.provider && (
                <SocialRedirectPanel provider={active.provider} />
              )}

              <p className="fc-form__legal">
                仅限授权用户使用。社交登录需先在「账号绑定」中完成身份绑定。
              </p>
            </div>
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
