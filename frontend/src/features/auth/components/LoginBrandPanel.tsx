/**
 * 登录页左侧品牌栏（窄屏隐藏，由登录卡上方的精简品牌头替代）。
 * 纯展示，无交互：深色渐变底 + 极光色斑 + 细网格 + 斜向扫光，
 * 视觉层全部来自 auth.css 的 au-* 类，颜色令牌仍走全局主题。
 */
export function LoginBrandPanel() {
  return (
    <aside className="au-sheen relative hidden overflow-hidden lg:flex lg:w-[44%] lg:max-w-[540px] lg:flex-col lg:justify-between lg:p-12">
      {/* 底色 + 极光 + 网格：纯装饰，不承载信息 */}
      <div aria-hidden className="absolute inset-0 bg-[linear-gradient(150deg,#0a0a1a_0%,#151038_46%,#061a2e_100%)]" />
      <div aria-hidden className="au-aurora">
        <span />
        <span />
        <span />
        <span />
      </div>
      <div aria-hidden className="au-grid" />

      <div className="au-fade relative z-10 flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-gradient-to-br from-indigo-400 via-violet-500 to-cyan-400 text-[15px] font-bold text-white shadow-lg shadow-indigo-500/30">
          法
        </span>
        <span className="text-[15px] font-semibold tracking-tight text-white">
          法穿 <span className="font-medium text-white/60">AI Copilot</span>
        </span>
      </div>

      <div className="au-fade relative z-10 max-w-[360px]" style={{ animationDelay: '120ms' }}>
        <h2 className="bg-gradient-to-br from-white via-indigo-100 to-cyan-200 bg-clip-text text-[26px] leading-[1.35] font-semibold tracking-[-0.02em] text-transparent">
          一站式律师办案协同平台
        </h2>
        <p className="mt-3 text-[13px] leading-[1.8] text-white/55">
          材料预处理、案件台账与 AI 辅助工具统一入口。支持账号密码登录，也支持绑定社交账号后扫码登录。
        </p>
      </div>

      <p className="au-fade relative z-10 text-[11.5px] text-white/40" style={{ animationDelay: '220ms' }}>
        仅限授权用户使用
      </p>
    </aside>
  )
}
