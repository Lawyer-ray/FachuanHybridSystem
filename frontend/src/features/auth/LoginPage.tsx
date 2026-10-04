/**
 * 登录页。
 *
 * 视觉：白底极简（灰阶 + 单一黄铜点缀），样式自包含于 login.css。
 * 单栏左对齐、发丝线分隔，视觉重心让给账密表单。
 *
 * 开场 MG「奇点 · Super Intelligence」（≈6.2s）：星散墨点汇聚成奇点点火，
 * 「法穿」升起，SUPER INTELLIGENCE 逐字母点亮后收拢坍缩为 SI COPILOT
 * （长名缩写的动效叙事，点出 SI = Super Intelligence），整组飞向左上角
 * 铭牌后表单登台。每个浏览器会话只播一次（sessionStorage），
 * 「减少动态效果」直接跳最终页；想每次都播删掉 INTRO_SESSION_KEY 判断。
 *
 * 结构：品牌字标（仅大屏视口左上铭牌；手机隐藏——浏览器标题栏已有）→
 * 眉标/标题 → 方式标签（账密/扫码）→ 表单面板。登录方式由 login-methods
 * 分组派发，新增方式无需改这里。
 */
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
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

/** 开场动画时间轴（与 login.css 里 fc-intro 系列的 delay 保持同步） */
const INTRO_READY_MS = 5600
const INTRO_UNMOUNT_MS = 6250
const INTRO_SESSION_KEY = 'fachuan-login-intro-played'

/** 星散节点：黄金角确定性分布（不用随机数，重渲染/StrictMode 下稳定不闪） */
const INTRO_DOTS = Array.from({ length: 26 }, (_, i) => {
  const angle = i * 137.508 * (Math.PI / 180)
  const radius = 26 + ((i * 53) % 23) // 26–49 vmin
  return {
    dx: `${(Math.cos(angle) * radius).toFixed(2)}vmin`,
    dy: `${(Math.sin(angle) * radius).toFixed(2)}vmin`,
    d: `${(((i * 37) % 10) / 10) * 0.9}s`, // 0–0.9s 错峰，汇聚成流
    s: 3 + ((i * 29) % 3), // 3–5px
    brass: i % 5 === 0, // 每 5 颗一颗黄铜，品牌色若隐若现
  }
})

/** 逐字母点亮的命名短语（空格由布局 gap 提供） */
const INTRO_PHRASE = ['SUPER', 'INTELLIGENCE']

/** 是否跳过开场：读屏纯函数（副作用写在 effect 里，避免 StrictMode 双调用误标记） */
function introSkipped(): boolean {
  if (typeof window === 'undefined') return true
  try {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return true
    return sessionStorage.getItem(INTRO_SESSION_KEY) === '1'
  } catch {
    return true
  }
}

type IntroPhase = 'intro' | 'settling' | 'done'

export function LoginPage() {
  const navigate = useNavigate()
  const [activeId, setActiveId] = useState(PASSWORD_METHOD_ID)
  const [activeQrId, setActiveQrId] = useState('')
  const [phase, setPhase] = useState<IntroPhase>(() => (introSkipped() ? 'done' : 'intro'))

  useEffect(() => {
    if (phase !== 'intro') return
    try {
      sessionStorage.setItem(INTRO_SESSION_KEY, '1')
    } catch {
      /* 隐私模式下存不进就算了，代价是本会话重复播放 */
    }
    // settling：封面开始消散、表单级联登台（--ready）；done：卸载覆盖层
    const ready = setTimeout(() => setPhase('settling'), INTRO_READY_MS)
    const unmount = setTimeout(() => setPhase('done'), INTRO_UNMOUNT_MS)
    return () => {
      clearTimeout(ready)
      clearTimeout(unmount)
    }
  }, [phase])

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
    <div className={`fc-auth${phase !== 'intro' ? ' fc-auth--ready' : ''}`}>
      {phase !== 'done' && (
        <div aria-hidden className={`fc-intro${phase === 'settling' ? ' fc-intro--out' : ''}`}>
          {/* 星散节点：汇聚奇点的智能碎片 */}
          <div className="fc-intro__dots">
            {INTRO_DOTS.map((dot, i) => (
              <span
                key={i}
                className={`fc-intro__dot${dot.brass ? ' fc-intro__dot--brass' : ''}`}
                style={{ '--dx': dot.dx, '--dy': dot.dy, '--d': dot.d, '--s': `${dot.s}px` } as CSSProperties}
              />
            ))}
          </div>

          <div className="fc-intro__stage">
            <div className="fc-intro__corewrap">
              <span className="fc-intro__core" />
              <span className="fc-intro__wave" />
            </div>
            <div className="fc-intro__word">
              <span className="fc-intro__char">法</span>
              <span className="fc-intro__char fc-intro__char--2">穿</span>
            </div>
            <span className="fc-intro__rule" />
            <span className="fc-intro__phrase">
              {INTRO_PHRASE.map((word, wi) => (
                <span key={word} className="fc-intro__phrase-word">
                  {word.split('').map((ch, ci) => (
                    <span
                      key={ci}
                      className="fc-intro__letter"
                      style={{ animationDelay: `${3.45 + (wi * 8 + ci) * 0.055}s` }}
                    >
                      {ch}
                    </span>
                  ))}
                </span>
              ))}
            </span>
            <span className="fc-intro__meta">SI Copilot</span>
            <span className="fc-intro__est">EST. 2026 · 超级智能法律事务协同系统</span>
          </div>
        </div>
      )}

      <main className="fc-card">
        <header className="fc-mark">
          <strong>法穿</strong>
          <span className="fc-mark__meta">SI Copilot</span>
        </header>

        <p className="fc-eyebrow">登录 / Sign in</p>
        <h1 className="fc-title">欢迎回来</h1>

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
      </main>
    </div>
  )
}
