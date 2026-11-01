/**
 * ④ 文书 —— 机器人执行录像
 *
 * 「派了个机器人去 OA 干活」这句话律师是不信的：他没见过那个浏览器。
 * 所以这里画一个**假的浏览器窗口**：地址栏、页面骨架、表单字段，
 * 按 DEMO_X3_BROWSER_FRAMES 逐帧点亮，最后一帧停在冲突命中、建卷按钮置灰。
 *
 * 帧是剧本化的（setTimeout 依次推进），但节奏对得上真实录屏：
 * 登录 → 检索 → 命中 → 阻断，5 帧约 6 秒。
 */

import { useEffect, useState } from 'react'
import { CircleDot, Lock } from 'lucide-react'

import { DEMO_X3_BROWSER_FRAMES } from '../demo-data'
import { ActionButton, InsetBlock, Pill, StepItem } from '../ui'
import { cn } from '@/lib/utils'
import { DetailDrawer } from './DetailDrawer'

/** 每帧停留时长：前两帧快、命中那帧慢一点，像人眼睛跟着看 */
const FRAME_MS = [900, 1100, 1300, 1600, 1400]

export function BotReplayDrawer({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  if (!open) return null

  return (
    <DetailDrawer
      open={open}
      onClose={onClose}
      width={640}
      title="机器人执行录像"
      subtitle={`服务端浏览器 · 11-01 10:22 — 10:24 · ${DEMO_X3_BROWSER_FRAMES.length} 帧`}
      badge={<Pill tone="red">停在利冲页</Pill>}
      footer={
        <ActionButton dark onClick={onClose}>
          下载录像 mp4
        </ActionButton>
      }
    >
      <BotReplayBody />
    </DetailDrawer>
  )
}

/** 帧播放在挂载时从第 1 帧开始；「重播」复位内部 state，不靠重挂载 */
function BotReplayBody() {
  const [frame, setFrame] = useState(0)
  const [playing, setPlaying] = useState(true)

  useEffect(() => {
    if (!playing) return
    if (frame >= DEMO_X3_BROWSER_FRAMES.length - 1) {
      setPlaying(false)
      return
    }
    const t = setTimeout(() => setFrame((f) => f + 1), FRAME_MS[frame] ?? 1000)
    return () => clearTimeout(t)
  }, [frame, playing])

  const cur = DEMO_X3_BROWSER_FRAMES[frame]!
  const hit = cur.tone === 'hit'

  return (
    <div className="flex flex-col gap-3">
      {/* 假浏览器窗口 */}
      <div className="overflow-hidden rounded-[10px] border border-border bg-background">
        <div className="flex items-center gap-2 border-b border-border-light bg-secondary/40 px-2.5 py-1.5">
          <span className="flex flex-none gap-1">
            <span className="size-[7px] rounded-full bg-status-red/60" />
            <span className="size-[7px] rounded-full bg-status-yellow/60" />
            <span className="size-[7px] rounded-full bg-status-green/60" />
          </span>
          <span className="flex h-[20px] min-w-0 flex-1 items-center gap-1.5 rounded-[5px] border border-border-light bg-card px-2">
            <Lock className="size-2.5 flex-none text-muted-foreground" />
            <span className="truncate text-[10px] text-muted-foreground">{cur.url}</span>
          </span>
        </div>

        {/* 页面骨架 + 逐帧点亮的字段 */}
        <div className="flex flex-col gap-1.5 px-3 py-2.5">
          <div className="text-[10px] text-muted-foreground">律所 OA · 当事人库</div>
          <div className="flex flex-col gap-1.5">
            {cur.fields.map((f, i) => (
              <div
                key={f}
                className={cn(
                  'flex items-center gap-2 rounded-[6px] border px-2 py-1.5 transition-colors duration-300',
                  hit
                    ? 'border-status-red/50 bg-status-red-bg/70'
                    : 'border-status-blue/40 bg-status-blue-bg/50',
                )}
                style={{ transitionDelay: `${i * 120}ms` }}
              >
                <CircleDot className={cn('size-3 flex-none', hit ? 'text-status-red' : 'text-status-blue')} />
                <span className={cn('text-[11px] font-medium', hit ? 'text-status-red' : 'text-status-blue')}>{f}</span>
              </div>
            ))}
          </div>

          {/* 建卷按钮：最后一帧置灰 */}
          <div className="mt-1 flex items-center gap-2">
            <span
              className={cn(
                'rounded-[6px] border px-2 py-1 text-[10.5px]',
                hit
                  ? 'border-border bg-secondary text-muted-foreground line-through'
                  : 'border-foreground bg-foreground text-background',
              )}
            >
              新建委托卷
            </span>
            {hit ? <span className="text-[10px] text-status-red">机器人已放弃点击</span> : null}
          </div>
        </div>
      </div>

      {/* 帧时间轴 */}
      <InsetBlock>
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] text-muted-foreground">
            第 {frame + 1} / {DEMO_X3_BROWSER_FRAMES.length} 帧
          </span>
          <span className="flex items-center gap-1">
            {DEMO_X3_BROWSER_FRAMES.map((f, i) => (
              <button
                key={f.url + i}
                type="button"
                aria-label={`跳到第 ${i + 1} 帧`}
                onClick={() => {
                  setPlaying(false)
                  setFrame(i)
                }}
                className={cn(
                  'h-1.5 rounded-full transition-all',
                  i === frame ? 'w-4 bg-foreground' : 'w-1.5 bg-border hover:bg-muted-foreground',
                )}
              />
            ))}
            <ActionButton
              sm
              onClick={() => {
                setFrame(0)
                setPlaying(true)
              }}
            >
              重播
            </ActionButton>
          </span>
        </div>
        <p className="mt-1.5 text-[11px] leading-[1.6] text-secondary-foreground">{cur.action}</p>
      </InsetBlock>

      <div>
        <div className="mb-1.5 text-[10.5px] text-muted-foreground">这一遍做了什么</div>
        <StepItem index={1} title="登录 OA" desc="配置账号，登录态 8 分钟内有效" state="done" />
        <StepItem index={2} title="逐方检索当事人库" desc="6 方比对，含证件号归一化" state="done" />
        <StepItem index={3} title="命中红色冲突" desc="李某某 与本所在办「离婚案」同证件号" state="blocked" />
        <StepItem index={4} title="停止建卷" desc="保留结果页快照，等律师决定" state="todo" />
      </div>
    </div>
  )
}
