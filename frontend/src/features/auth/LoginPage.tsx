/**
 * 登录页。
 *
 * 视觉：白底极简（灰阶 + 单一黄铜点缀），样式自包含于 login.css。
 * 单栏左对齐、发丝线分隔，视觉重心让给账密表单。
 *
 * 开场 MG「奇点 · Super Intelligence」v3（≈9.7s，国际大片规格）：
 * 深空粒子场 → 螺旋卷入（弧线加速而非直线）→ 奇点蓄能爆发（暖闪 + 三层
 * 冲击波 + 抛射粒子 + 巨字残影）→「法穿」带景深模糊炸出 → SUPER
 * INTELLIGENCE 逐字母点亮后坍缩为 SI COPILOT（长名缩写的动效叙事）
 * → 整组飞向左上角铭牌，表单登台。
 *
 * 播放策略：每次进入登录页都完整播放（用户定调——开场是秀场不是负担）；
 * 仅系统「减少动态效果」偏好会跳过（无障碍硬要求）。
 *
 * 结构：品牌字标（仅大屏视口左上铭牌；手机隐藏——浏览器标题栏已有）→
 * 眉标/标题 → 方式标签（仅桌面，手机没有「扫自己屏幕」的物理条件）→
 * 表单面板。登录方式由 login-methods 分组派发，新增方式无需改这里。
 */
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { useMediaQuery } from '../../hooks/use-media'
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
const INTRO_READY_MS = 8900
const INTRO_UNMOUNT_MS = 9700

/** 螺旋卷入的主演粒子：极径/初始角/卷入角均按黄金角确定性推导（重渲染不闪） */
const INTRO_DOTS = Array.from({ length: 30 }, (_, i) => ({
  a: `${((i * 137.508) % 360).toFixed(1)}deg`,
  r: `${(24 + ((i * 53) % 26)).toFixed(1)}vmin`,
  spin: `${(180 + ((i * 61) % 300)).toFixed(0)}deg`,
  d: `${(((i * 37) % 12) / 12 * 1.2).toFixed(2)}s`,
  s: 3 + ((i * 29) % 3),
  brass: i % 5 === 0,
}))

/** 深空背景粒子：更小更暗，只做氛围层 */
const INTRO_BG_DOTS = Array.from({ length: 22 }, (_, i) => ({
  dx: `${(((i * 73) % 100) - 50).toFixed(1)}vmin`,
  dy: `${(((i * 41) % 100) - 50).toFixed(1)}vmin`,
  bd: `${(-((i * 31) % 70) / 10).toFixed(1)}s`,
}))

/** 奇点爆发的抛射粒子：从中心向外的确定性向量 */
const INTRO_EJECTA = Array.from({ length: 12 }, (_, i) => {
  const angle = ((i * 30 + 15) * Math.PI) / 180
  const dist = 22 + (i % 3) * 9
  return { ex: `${(Math.cos(angle) * dist).toFixed(1)}vmin`, ey: `${(Math.sin(angle) * dist).toFixed(1)}vmin` }
})

/** 逐字母点亮的命名短语（空格由布局 gap 提供） */
const INTRO_PHRASE = ['SUPER', 'INTELLIGENCE']

/** 是否跳过开场：仅「减少动态效果」系统偏好会跳（无障碍），其余每次进页都播 */
function introSkipped(): boolean {
  if (typeof window === 'undefined') return true
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
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
  // 手机没有「用另一台设备扫自己屏幕」的物理条件，扫码标签与面板只在桌面出现
  const isDesktop = useMediaQuery('(min-width: 760px)')

  useEffect(() => {
    if (phase !== 'intro') return
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

  // 模式级标签：账密恒在；扫码标签仅桌面且有扫码型 Provider 时出现
  const tabs = useMemo<NonEmptyArray<LoginMethod>>(
    () => (groups.qrProviders.length > 0 ? [groups.password, QR_TAB] : [groups.password]),
    [groups],
  )
  const showTabs = isDesktop && tabs.length > 1
  // 手机恒为账密视图（tabs[0] 由 buildLoginMethodGroups 保证是账密）
  const active = isDesktop ? (tabs.find((tab) => tab.id === activeId) ?? tabs[0]) : tabs[0]

  // 「扫码登录」页内当前展示的二维码（单 Provider 时恒为它，无需切换器）
  const activeQr = groups.qrProviders.find((method) => method.id === activeQrId) ?? groups.qrProviders[0]

  return (
    <div className={`fc-auth${phase !== 'intro' ? ' fc-auth--ready' : ''}`}>
      {phase !== 'done' && (
        <div aria-hidden className={`fc-intro${phase === 'settling' ? ' fc-intro--out' : ''}`}>
          {/* 深空背景粒子：氛围层，点火前淡出 */}
          <div className="fc-intro__bg">
            {INTRO_BG_DOTS.map((dot, i) => (
              <span
                key={i}
                className="fc-intro__bgdot"
                style={{ '--dx': dot.dx, '--dy': dot.dy, '--bd': dot.bd } as CSSProperties}
              />
            ))}
          </div>

          {/* 螺旋卷入粒子：transform = rotate(初始角) + translateX(极径)，动画即黑洞吸积 */}
          <div className="fc-intro__dots">
            {INTRO_DOTS.map((dot, i) => (
              <span
                key={i}
                className={`fc-intro__dot${dot.brass ? ' fc-intro__dot--brass' : ''}`}
                style={{ '--a': dot.a, '--r': dot.r, '--spin': dot.spin, '--d': dot.d, '--s': `${dot.s}px` } as CSSProperties}
              />
            ))}
          </div>

          <div className="fc-intro__stage">
            <div className="fc-intro__corewrap">
              <span className="fc-intro__core" />
              <span className="fc-intro__wave fc-intro__wave--1" />
              <span className="fc-intro__wave fc-intro__wave--2" />
              <span className="fc-intro__wave fc-intro__wave--3" />
            </div>

            {/* 暖色过曝闪：白底上的"爆发一瞬"（纯白闪不可见，用黄铜薄雾） */}
            <span className="fc-intro__flash" />

            {/* 巨字残影：镜头景深，「法穿」炸出前的一瞬大轮廓 */}
            <span className="fc-intro__ghost">穿</span>

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
                      style={{ animationDelay: `${6.45 + (wi * 8 + ci) * 0.055}s` }}
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

          {/* 抛射粒子：奇点爆发甩出的火花 */}
          <div className="fc-intro__ejecta">
            {INTRO_EJECTA.map((p, i) => (
              <span key={i} className="fc-intro__spark" style={{ '--ex': p.ex, '--ey': p.ey } as CSSProperties} />
            ))}
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

        {showTabs && <LoginMethodSwitch methods={tabs} activeId={active.id} onChange={setActiveId} />}

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
