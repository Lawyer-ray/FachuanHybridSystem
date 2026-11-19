/**
 * 「这次跑哪几个 AI、各用哪个模型」多选菜单（从 ComposerToolbar 拆出，后者负责
 * 其余工具按钮）。
 *
 * ## 为什么是一个菜单而不是 N 个开关
 *
 * 可选后端是**部署级**的（`GET /agent/backends`，随注册表变），写死几个复选框
 * 按钮会在新后端注册后立刻过期。菜单按清单渲染，接第 4、5 个 agent 时前端零改动。
 *
 * ## 每行 = 勾选框 + 名字 + 模型下拉
 *
 * 勾选决定「这一轮问不问它」，模型下拉决定「它用哪个模型」——同一行两件事，因为
 * 它们都只对**这一轮**生效，拆成两个菜单会让「哪家的模型」只能靠位置猜。
 * 没勾的行模型下拉置灰（选了也不跑，允许改只会让人以为自己已经配好了）。
 *
 * 行渲染拆在 {@link AgentRow}、模型下拉在 AgentModelPicker：本文件只留菜单外壳
 * （触发器摘要、上限计数、禁用态），否则三件事挤在一起必然撞 350 行软红线。
 *
 * ## 上限
 *
 * 选满 {@link MAX_ANSWERS} 后其余项置灰：超出的选择后端会直接 400，而那发生在
 * 用户已经敲了回车之后——置灰比报错便宜得多。
 *
 * ## 未选 = 单跑会话默认后端
 *
 * `selected` 为空数组时本轮只跑一个：会话默认后端。菜单里用「默认」徽标标出它
 * （清单第一项，与新建会话的默认同口径），律师能看出不选时到底是谁在答。
 */

import { useCallback, useState } from 'react'
import { GitCompare, ChevronDown } from 'lucide-react'

import { DEFAULT_AGENT_KIND, MAX_ANSWERS } from '../domain'
import type { AgentBackendOption } from '../types'
import { findBackend } from '../store/backends'
import { AgentRow } from './AgentRow'

/** 触发按钮的统一外观（与 ComposerToolbar 的图标按钮同尺寸，但带文字） */
const TRIGGER_CLASS =
  'flex h-7 flex-none items-center gap-1 rounded-[8px] px-1.5 text-[11.5px] transition-colors disabled:opacity-40'

export function AnswerAgentMenu({
  backends,
  selected,
  models,
  defaultKind,
  disabled,
  hint,
  onToggle,
  onSelectModel,
}: {
  /** 可选后端清单（`GET /agent/backends`；没拉到时为空数组） */
  backends: AgentBackendOption[]
  /** 已选的 kind（顺序 = 栏的左右顺序；空数组 = 不指定，用会话默认后端） */
  selected: string[]
  /** 各栏指定的模型（`kind → 模型名`；没有键 = 平台默认） */
  models: Record<string, string>
  /** 会话默认后端（清单第一项；空串表示清单未到） */
  defaultKind: string
  /** 流式中 / 发送中 / 清单为空：不能改本轮参与方 */
  disabled: boolean
  /** 禁用原因（悬停提示；空串表示无补充） */
  hint: string
  onToggle: (kind: string) => void
  /** 给某一栏指定模型（空串 = 取消指定） */
  onSelectModel: (kind: string, model: string) => void
}) {
  const [open, setOpen] = useState(false)
  const close = useCallback(() => setOpen(false), [])

  // 清单没拉到时也要能显示「这家是谁」：kind 原文比空白可读
  const names = selected.map((kind) => findBackend(backends, kind)?.label ?? kind)
  const summary = names.length === 0 ? '1 个 AI' : names.length === 1 ? names[0]! : `${names.length} 个 AI`
  const active = selected.length > 1 || (selected.length === 1 && selected[0] !== defaultKind)
  const full = selected.length >= MAX_ANSWERS

  return (
    <div className="relative flex-none">
      <button
        type="button"
        className={`${TRIGGER_CLASS} ${
          active ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
        }`}
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`本轮参与的 AI：${summary}`}
        title={
          disabled
            ? hint || '本轮正在进行，结束前不能改参与方'
            : `选择这一轮问哪几个 AI（最多 ${MAX_ANSWERS} 个）以及各自用哪个模型。每多选一个就多跑一轮，token 与耗时随之增加。`
        }
      >
        <GitCompare className="h-4 w-4 flex-none" />
        <span className="max-w-24 truncate">{summary}</span>
        <ChevronDown className="h-3 w-3 flex-none" aria-hidden />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label="可选 AI（多选）"
          aria-multiselectable
          className="absolute bottom-full left-0 z-[120] mb-1 w-72 rounded-[10px] border border-border bg-popover p-1 shadow-md"
        >
          {backends.length === 0 && (
            <p className="px-2 py-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
              后端清单暂不可用，本轮使用默认 AI。
            </p>
          )}
          {backends.map((option) => (
            <AgentRow
              key={option.kind}
              option={option}
              picked={selected.includes(option.kind)}
              isDefault={option.kind === (defaultKind || DEFAULT_AGENT_KIND)}
              // 不可用 / 已选满（且没选中它）都点不动——两种原因不同，提示也不同
              blockedByLimit={!selected.includes(option.kind) && full}
              model={models[option.kind] ?? ''}
              onToggle={onToggle}
              onSelectModel={onSelectModel}
              onRowPicked={close}
            />
          ))}
          <p className="px-2 py-1 text-[11px] text-muted-foreground">
            已选 {selected.length} 个 · 最多 {MAX_ANSWERS} 个
          </p>
        </div>
      )}
    </div>
  )
}
