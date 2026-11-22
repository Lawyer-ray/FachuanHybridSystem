/**
 * 新对话的 agent 后端选择器：**唯一**能给新会话定 `agent_kind` 的地方。
 *
 * ## 只在还没有会话时出现
 *
 * `agent_kind` 是**会话级、不可更换**的属性（上下文归后端自己管：pi 有自己的
 * session 文件，换后端等于换脑子）。若已建会话仍给下拉，用户一改就会以为
 * 「换了」，实际下一轮还在旧后端跑——这种假切换比直接禁用难发现得多。
 *
 * 所以本组件只有一种形态：下拉。已有会话时由调用方（CopilotHeader）不渲染它，
 * 改为把 `agent_kind` 作为标题后缀显示（只读、不可点）。上一版在这里挂过一个
 * 「锁 + 后端名」的只读按钮，点了只弹一句「换不了」——它看着可点却没有可选的东西，
 * 用户直接判定「这个按钮没意义」（真实反馈），故整块删掉。
 *
 * 「有没有会话」由调用方判：会话列表缓存归宿主（useActiveSession），本组件不自查。
 *
 * ## 不可用项置灰
 *
 * `available=false` 的项保留在列表里但禁用，副标题显示原因（缺 SDK / 没配
 * LLM 平台）。直接不列会让用户以为「本系统没这个后端」，而真相是「这里缺
 * 东西」，后者可排查、可修。
 */

import { useCallback, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'

import { useCopilot } from '../store'
import { findBackend, noApprovalWarn } from '../store/backends'
import { NoApprovalBadge } from './NoApprovalBadge'

/** 关闭下拉的两种方式：选中 / 点外面；`null` 表示不选（只关闭） */
type CloseReason = string | null

export function AgentBackendPicker() {
  const backends = useCopilot((s) => s.backends)
  const selectedAgentKind = useCopilot((s) => s.selectedAgentKind)
  const selectAgentKind = useCopilot((s) => s.selectAgentKind)
  const [open, setOpen] = useState(false)

  const close = useCallback((reason: CloseReason) => {
    setOpen(false)
    if (reason) selectAgentKind(reason)
  }, [selectAgentKind])

  const active = selectedAgentKind ? findBackend(backends, selectedAgentKind) : undefined
  // 清单还没到（或拉取失败）时只显示 kind 原文：宁可显示 `pi` 也不显示空白
  const activeLabel = active?.label ?? selectedAgentKind

  return (
    <div className="relative flex-none">
      <button
        type="button"
        className={`flex h-7 max-w-44 items-center gap-1 rounded-[8px] px-2 text-[11.5px] transition-colors hover:bg-secondary hover:text-foreground ${
          open ? 'bg-secondary text-foreground' : 'text-muted-foreground'
        }`}
        onClick={() => setOpen((v) => !v)}
        aria-label={activeLabel ? `后端：${activeLabel}，点击更换` : '选择 agent 后端'}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="选择新对话使用的 agent 后端（建会话时确定，之后不可更换）"
      >
        <span className="truncate">{activeLabel || '选择后端'}</span>
        <ChevronDown className="h-3 w-3 flex-none" aria-hidden />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label="可选 agent 后端"
          className="absolute top-full right-0 z-[120] mt-1 w-64 rounded-[10px] border border-border bg-popover p-1 shadow-md"
        >
          {backends.length === 0 && (
            <p className="px-2 py-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
              后端清单暂不可用，将使用默认后端。
            </p>
          )}
          {backends.map((option) => {
            const isActive = option.kind === selectedAgentKind
            return (
              <button
                key={option.kind}
                type="button"
                role="option"
                aria-selected={isActive}
                aria-disabled={!option.available}
                disabled={!option.available}
                className={`flex w-full items-start gap-1.5 rounded-[7px] px-2 py-1.5 text-left transition-colors ${
                  option.available ? 'hover:bg-secondary' : 'cursor-not-allowed opacity-55'
                } ${isActive ? 'bg-secondary/60' : ''}`}
                onClick={() => close(option.kind)}
                title={option.available ? option.description : option.reason}
              >
                <span className="mt-0.5 flex h-3 w-3 flex-none items-center justify-center">
                  {isActive && <Check className="h-3 w-3 text-foreground" aria-hidden />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] font-medium text-foreground">
                    {option.label}
                    {noApprovalWarn(option) && <NoApprovalBadge className="ml-1" />}
                  </span>
                  <span className="block text-[11px] leading-snug text-muted-foreground">
                    {/* 不可用时优先说原因：这才是用户此刻需要的那句话 */}
                    {option.available ? option.description : option.reason}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
