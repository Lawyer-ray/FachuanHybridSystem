/**
 * 登录页左侧品牌栏（窄屏隐藏，由登录卡上方的精简品牌头替代）。
 * 纯展示，无交互。
 */
export function LoginBrandPanel() {
  return (
    <aside className="relative hidden overflow-hidden border-r border-border bg-secondary/50 lg:flex lg:w-[44%] lg:max-w-[540px] lg:flex-col lg:justify-between lg:p-12">
      {/* 柔光装饰，仅视觉，不承载信息 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 -right-20 h-[360px] w-[360px] rounded-full bg-foreground/[0.04] blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-32 -left-24 h-[320px] w-[320px] rounded-full bg-foreground/[0.03] blur-3xl"
      />

      <div className="relative flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-foreground text-[15px] font-bold text-background">
          法
        </span>
        <span className="text-[15px] font-semibold tracking-tight">
          法穿 <span className="font-medium text-muted-foreground">AI Copilot</span>
        </span>
      </div>

      <div className="relative max-w-[360px]">
        <h2 className="text-[26px] leading-[1.35] font-semibold tracking-[-0.02em]">一站式律师办案协同平台</h2>
        <p className="mt-3 text-[13px] leading-[1.8] text-muted-foreground">
          材料预处理、案件台账与 AI 辅助工具统一入口。支持账号密码登录，也支持绑定社交账号后扫码登录。
        </p>
      </div>

      <p className="relative text-[11.5px] text-muted-foreground/80">仅限授权用户使用</p>
    </aside>
  )
}
