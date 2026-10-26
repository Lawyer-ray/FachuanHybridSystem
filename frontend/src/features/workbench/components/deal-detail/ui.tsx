import type { ReactNode } from 'react'
import { Link } from 'react-router'

import type { MetaPart, StepState } from './detail-domain'

/**
 * 详情页子域共用的小原件。视觉语言沿用列表页/抽屉（zinc 灰阶 + 唯一红只给「今天」），
 * 圆角 12 / 细边 / 轻阴影的卡片是 52 号原型的直译。
 */

export function Card({ id, className = '', children }: { id?: string; className?: string; children: ReactNode }) {
  return (
    <section id={id} className={'rounded-[12px] border border-border bg-card shadow-sm ' + className}>
      {children}
    </section>
  )
}

/** 创建类按钮：outline 默认 / dark 主动作；sm 用于节内 */
export function ActionButton({
  dark,
  sm,
  title,
  onClick,
  children,
}: {
  dark?: boolean
  sm?: boolean
  title?: string
  onClick: () => void
  children: ReactNode
}) {
  const size = sm ? 'h-[27px] px-2.5 text-[11.5px] ' : 'h-[31px] px-[13px] text-[12.5px] '
  const tone = dark
    ? 'border-foreground bg-foreground font-semibold text-background hover:opacity-85'
    : 'border-border bg-card font-[550] text-secondary-foreground hover:border-input hover:bg-secondary'
  return (
    <button
      type="button"
      title={title}
      className={'inline-flex flex-none items-center rounded-[8px] border whitespace-nowrap transition-all ' + size + tone}
      onClick={onClick}
    >
      {children}
    </button>
  )
}

/** 中性小标签（已结 / 在办 / 角色） */
export function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-[6px] border border-border bg-secondary px-2 text-[11px] leading-[1.6] font-semibold whitespace-nowrap text-secondary-foreground">
      {children}
    </span>
  )
}

/** 案号 chip */
export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-[6px] border border-border-light bg-background px-2 text-[11.5px] leading-[1.7] font-semibold text-secondary-foreground tabular-nums">
      {children}
    </span>
  )
}

/** 程序状态点：已结=灰实心、在办=黑空心、未启动=虚线圈 */
export function StateDot({ state, size = 11 }: { state: StepState; size?: number }) {
  const cls =
    state === 'done'
      ? 'bg-muted-foreground/60'
      : state === 'cur'
        ? 'border-[2.5px] border-foreground'
        : 'border-[1.5px] border-dashed border-border'
  return <span className={'inline-block flex-none rounded-full ' + cls} style={{ width: size, height: size }} />
}

/** 键值行（合同要素 / 右栏金额）：键固定宽、值 tabular；给 href 时值渲染为新标签页链接（如 OA 编号） */
export function KV({
  k,
  v,
  kw = 60,
  full,
  muted,
  href,
}: {
  k: string
  v: string
  kw?: number
  full?: boolean
  muted?: boolean
  href?: string
}) {
  return (
    <div className={'flex items-baseline gap-3 py-[5px] text-[13px] ' + (full ? 'col-span-full' : '')}>
      <span className="flex-none text-[12.5px] text-muted-foreground" style={{ width: kw }}>
        {k}
      </span>
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="min-w-0 font-[550] break-all underline underline-offset-3 tabular-nums transition-colors hover:text-foreground"
        >
          {v}
        </a>
      ) : (
        <span className={'min-w-0 break-all tabular-nums ' + (muted ? 'leading-[1.7] text-muted-foreground' : 'font-[550]')}>{v}</span>
      )}
    </div>
  )
}

/** 右栏节：细线分隔、小号大写字距标题 */
export function RailSection({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <div className="border-t border-border-light px-[18px] pt-3.5 pb-[15px] first:border-t-0 first:pt-[15px]">
      <div className="mb-[9px] flex items-center gap-2">
        <h4 className="text-[11px] font-[650] tracking-[0.07em] text-muted-foreground/80">{title}</h4>
        {action && <span className="ml-auto">{action}</span>}
      </div>
      {children}
    </div>
  )
}

/** 右栏文字小动作（＋ 新增） */
export function RailAction({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" className="text-[11px] text-muted-foreground transition-colors hover:text-foreground" onClick={onClick}>
      {children}
    </button>
  )
}

/** 行内复制小字按钮（右栏电话 / 证号） */
export function CopyText({ text, label = '复制', onCopy }: { text: string; label?: string; onCopy: (text: string) => void }) {
  return (
    <button
      type="button"
      className="flex-none px-0.5 text-[10.5px] text-muted-foreground/70 transition-colors hover:text-foreground"
      onClick={() => onCopy(text)}
    >
      {label}
    </button>
  )
}

/** meta 片段串：「<b>机构</b> · 收案 2025-03-17 · 标的 <b>¥…</b>」，窄屏允许折行 */
export function MetaLine({ parts, className = '' }: { parts: MetaPart[]; className?: string }) {
  return (
    <div className={className}>
      {parts.map((p, i) => (
        <span key={(p.k ?? '') + p.v} className="whitespace-nowrap max-[680px]:whitespace-normal">
          {i > 0 && <span className="mx-[7px] text-border">·</span>}
          {p.k && <span>{p.k} </span>}
          {p.strong ? <b className="font-[620] text-secondary-foreground">{p.v}</b> : p.v}
        </span>
      ))}
    </div>
  )
}

/** 详情页错误态（争议解决 / 非诉共用）：错误信息 + 重试 + 返回列表 */
export function DetailError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <main className="app-page-enter mx-auto max-w-lg px-6 pt-[80px]">
      <div className="rounded-[14px] border border-destructive/30 bg-destructive/5 px-5 py-4 text-center text-sm text-destructive">
        {error}
        <button type="button" className="ml-3 cursor-pointer underline underline-offset-3" onClick={onRetry}>
          重试
        </button>
        <Link to="/projects" className="ml-3 cursor-pointer underline underline-offset-3">
          返回列表
        </Link>
      </div>
    </main>
  )
}
