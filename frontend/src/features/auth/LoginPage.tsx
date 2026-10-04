/**
 * 登录页。
 *
 * 视觉：白底极简（灰阶 + 单一黄铜点缀），样式自包含于 login.css。
 * 单栏左对齐、发丝线分隔，视觉重心让给账密表单；不再有品牌杂志栏与走马灯。
 *
 * 结构：品牌字标 → 眉标/标题 → 方式标签（账密/扫码）→ 表单面板 → 法条。
 * 登录方式由 login-methods 分组派发：账密与按钮型社交登录（GitHub/Google/微软）
 * 同页堆叠，扫码型（飞书）独立「扫码登录」标签页，新增方式无需改这里。
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import './login.css'
import { socialAuthApi, SOCIAL_PROVIDERS_KEY } from './social-api'
import {
  buildLoginMethodGroups,
  PASSWORD_METHOD_ID,
  QR_METHOD_ID,
  type LoginMethod,
  type NonEmptyArray,
} from './login-methods'
import { LoginMethodSwitch } from './components/LoginMethodSwitch'
import { PasswordLoginForm } from './components/PasswordLoginForm'
import { SocialQrPanel } from './components/SocialQrPanel'
import { SocialRedirectGroup } from './components/SocialRedirectGroup'

/** 「扫码登录」标签页：面板内再按 Provider 次级切换（当前只有飞书） */
const QR_TAB: LoginMethod = { id: QR_METHOD_ID, kind: 'embedded_qr', label: '扫码登录', provider: null }

export function LoginPage() {
  const navigate = useNavigate()
  const [activeId, setActiveId] = useState(PASSWORD_METHOD_ID)
  const [activeQrId, setActiveQrId] = useState('')

  // 已启用的登录方式由后端下发；走 react-query 带缓存（此前手写 effect，
  // 每次进登录页都重新请求且无失败痕迹）。拉不到就只留账密，不影响登录。
  const { data: providers = [] } = useQuery({
    queryKey: SOCIAL_PROVIDERS_KEY,
    queryFn: () => socialAuthApi.listProviders(),
    staleTime: 5 * 60_000,
  })
  const groups = useMemo(() => buildLoginMethodGroups(providers), [providers])

  // 模式级标签：账密恒在；有扫码型 Provider 才出现「扫码登录」（否则单视图无标签）
  const tabs = useMemo<NonEmptyArray<LoginMethod>>(
    () => (groups.qrProviders.length > 0 ? [groups.password, QR_TAB] : [groups.password]),
    [groups],
  )
  const active = tabs.find((tab) => tab.id === activeId) ?? tabs[0]

  // 「扫码登录」页内当前展示的二维码（单 Provider 时恒为它，无需切换器）
  const activeQr = groups.qrProviders.find((method) => method.id === activeQrId) ?? groups.qrProviders[0]

  return (
    <div className="fc-auth">
      <main className="fc-card">
        <header className="fc-mark">
          <strong>法穿</strong>
          <span className="fc-mark__meta">SI Copilot</span>
        </header>

        <p className="fc-eyebrow">登录 / Sign in</p>
        <h1 className="fc-title">欢迎回来</h1>
        <p className="fc-sub">使用账号密码，或已绑定的社交身份登录。</p>

        {tabs.length > 1 && (
          <LoginMethodSwitch methods={tabs} activeId={active.id} onChange={setActiveId} />
        )}

        {active.kind === 'password' && (
          <>
            <PasswordLoginForm onLoggedIn={() => { void navigate('/', { replace: true }) }} />
            {groups.redirectProviders.length > 0 && (
              <SocialRedirectGroup providers={groups.redirectProviders.map((method) => method.provider)} />
            )}
          </>
        )}
        {active.kind === 'embedded_qr' && activeQr && (
          <>
            {groups.qrProviders.length > 1 && (
              <LoginMethodSwitch
                methods={groups.qrProviders as NonEmptyArray<LoginMethod>}
                activeId={activeQr.id}
                onChange={setActiveQrId}
              />
            )}
            <SocialQrPanel provider={activeQr.provider} />
          </>
        )}

        <p className="fc-legal">
          仅限授权用户使用。社交登录需先在「账号绑定」中完成身份绑定。
        </p>
      </main>
    </div>
  )
}
