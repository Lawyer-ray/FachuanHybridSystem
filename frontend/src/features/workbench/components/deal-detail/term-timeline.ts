/**
 * 服务期进度条：把「服务期」与「服务事项」画在同一条时间轴上。
 *
 * **为什么值得一条独立的轴**：常法顾问的核心信息不是「到期了没」，而是
 * 「这一年服务了多少事、还剩多少时间」。纯文字「2025-10-22 → 2026-10-21」
 * 要读两遍才反应过来；一条进度条 + 事项刻度，一眼就知道密度与节奏。
 *
 * 联动是关键：事项（记服务事项/期限/开庭）按月落在同一条轴上，凸起的刻度
 * 越密说明那个月越忙；空档说明服务空转，律师自己也能看出要不要催客户。
 */

/** 轴上的一个刻度（某天有事项） */
export interface TermTick {
  /** 距起点的比例 0–1 */
  ratio: number
  /** 该刻度对应的事项数 */
  count: number
  today: boolean
}

export interface TermTimeline {
  /** 起点/终点（yyyy-mm-dd），用于展示 */
  start: string
  end: string
  /** 流逝比例 0–1（<0 未开始，>1 已超期） */
  progress: number
  /** 剩余天数（负数=已超期天数） */
  daysLeft: number
  /** 总天数 */
  totalDays: number
  /** 按天聚合成刻度（同一天多个事项合一根，count 表示密度） */
  ticks: TermTick[]
  /** 进入「到期预警」区间的起点比例（最后 20%），无预警时为 null */
  warnFrom: number | null
}

const DAY = 86_400_000

function toMs(d: string): number | null {
  const t = Date.parse(d)
  return Number.isNaN(t) ? null : t
}

function fmt(ms: number): string {
  const d = new Date(ms)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * 构造服务期时间轴。
 *
 * 参数全用 `yyyy-mm-dd` 字符串（与后端 `from`/`to` 同形），避免调用方各自
 * 处理 Date 时区——这里统一按本地日粒度处理，跨时区偏移不影响「第几天」。
 */
export function buildTermTimeline({
  from,
  to,
  today,
  eventDates = [],
  warnRatio = 0.2,
}: {
  from: string
  to: string
  /** 今天（yyyy-mm-dd），由调用方传入便于测试 */
  today: string
  /** 事项发生日（yyyy-mm-dd）；轴外的自动丢弃 */
  eventDates?: string[]
  /** 最后多少比例进入预警区，默认 20% */
  warnRatio?: number
}): TermTimeline | null {
  const startMs = toMs(from)
  const endMs = toMs(to)
  const nowMs = toMs(today)
  if (startMs === null || endMs === null || nowMs === null || endMs <= startMs) return null

  const total = endMs - startMs
  const totalDays = Math.round(total / DAY)
  const progress = Math.min(1, Math.max(0, (nowMs - startMs) / total))
  const daysLeft = Math.round((endMs - nowMs) / DAY)

  // 按天聚合：同一天多个事项合成一根，count 表示当天密度
  const byDay = new Map<string, number>()
  for (const raw of eventDates) {
    const ms = toMs(raw)
    if (ms === null || ms < startMs || ms > endMs) continue
    const key = fmt(ms)
    byDay.set(key, (byDay.get(key) ?? 0) + 1)
  }
  const todayKey = today
  const ticks: TermTick[] = [...byDay.entries()]
    .map(([day, count]) => ({
      ratio: (toMs(day)! - startMs) / total,
      count,
      today: day === todayKey,
    }))
    .sort((a, b) => a.ratio - b.ratio)

  return {
    start: from,
    end: to,
    progress,
    daysLeft,
    totalDays,
    ticks,
    warnFrom: warnRatio > 0 && warnRatio < 1 ? 1 - warnRatio : null,
  }
}

/** 「还剩 N 天」/「已超期 N 天」/「今天到期」 */
export function termHeadline(daysLeft: number): string {
  if (daysLeft === 0) return '今天到期'
  if (daysLeft < 0) return `已超期 ${Math.abs(daysLeft)} 天`
  return `还剩 ${daysLeft} 天`
}

/** 进度条的语义色：>30 天正常、<=30 天提醒、超期红、>=80% 也用提醒色 */
export function termTone(t: TermTimeline): 'normal' | 'warn' | 'over' {
  if (t.daysLeft < 0 || t.progress >= 1) return 'over'
  if (t.daysLeft <= 30) return 'warn'
  return 'normal'
}
