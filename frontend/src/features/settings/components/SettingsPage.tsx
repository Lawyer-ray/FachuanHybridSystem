/**
 * 设置页：系统状态 + 账号绑定。
 *
 * 原 /settings/bindings（账号绑定页）已并入本页，旧路径重定向到 /settings 并
 * 保留 query（bound= 回调标记由绑定面板消费）。页面壳（main / 容器查询）在这里，
 * 内容分区各自独立成组件。
 */
import { Suspense } from 'react'
import { LoadingBlock } from '@/components/shared/AsyncState'
import { BindingsPanelLazy } from '@/features/auth'
import { SystemStatus } from './SystemStatus'

export function SettingsPage() {
  return (
    // 导航栏由 AppShell 常驻；入场过渡挂在 main 上，换页重挂才播一次。
    // @container：三卡栅格按页面净宽自适应（AI 助手并排让位时随之收拢）
    <main className="app-page-enter @container mx-auto max-w-[1040px] px-[32px] pt-[26px] pb-20 max-[760px]:px-[14px] max-[760px]:pt-[18px]">
      <h1 className="text-[22px] font-bold tracking-[-0.02em]">设置</h1>

      <section className="mt-5">
        <h2 className="text-[16px] font-semibold tracking-[-0.01em]">系统状态</h2>
        <p className="mb-3 mt-1.5 text-[12.5px] leading-[1.8] text-muted-foreground">
          后端服务、任务队列与 LLM 网关的实时状态。数据只在本页打开时读取，不在后台轮询。
        </p>
        <SystemStatus />
      </section>

      <section className="mt-8">
        {/* chunk 下载中：与页内其它加载态同构，只把字号压到本页的 12.5px 档 */}
        <Suspense fallback={<LoadingBlock text="正在加载…" className="py-10 text-[12.5px]" />}>
          <BindingsPanelLazy />
        </Suspense>
      </section>
    </main>
  )
}
