/**
 * 多选菜单里的一行：`[☑/☐] 名字（默认徽标）+ 说明 | [模型 ▾]`。
 *
 * 从 AnswerAgentMenu 拆出——行里同时有两件事（勾选、模型），加上不可用/满额两种
 * 置灰原因和默认徽标，塞回菜单外壳会把那个文件推过 350 行软红线，而它自己只剩
 * 触发器摘要与上限这些外壳职责。
 *
 * ## 「默认」徽标怎么说清是哪一家
 *
 * 右上会话级后端名改成标题后缀后，「本会话默认是谁」只剩这里能看出来。徽标取
 * 「名字 + `默认` chip」而不取「`默认 · 名字`」：名字就在左边一厘米处，再抄一遍
 * 会把行挤破（288px 的菜单还要塞无审批徽标与模型下拉）。
 *
 * 但这一行勾选区的 `aria-label` 会覆盖子元素名，屏幕上看得见的「默认」对屏幕阅读器
 * 是隐形的——所以默认那一行的无障碍名里直接带上「会话默认」，徽标再挂 `title`
 * 供悬停确认。（同一覆盖也让「无审批」徽标读不到，那是既有问题，不在本次收敛范围内。）
 *
 * ## 模型下拉与勾选框是**并列**的两个可点区域
 *
 * 按钮里套按钮是非法 HTML（浏览器会把内层甩出外层，点击行为随之错乱），所以行是
 * `div[role=option]`，里面两个真按钮：左侧勾选区（`aria-checked`）与右侧模型
 * 下拉。两个 area 的禁用理由不同（行不可用 / 没勾就不必选模型），所以各自算了
 * 再传下去。
 */

import { Check } from 'lucide-react'

import { MAX_ANSWERS } from '../domain'
import type { AgentBackendOption } from '../types'
import { noApprovalWarn } from '../store/backends'
import { AgentModelPicker } from './AgentModelPicker'
import { NoApprovalBadge } from './NoApprovalBadge'

/** 左侧勾选区（视觉上 12px 见方，与既有 AgentBackendPicker 一致：只画对勾不画方框） */
const CHECK_CLASS = 'mt-0.5 flex h-3 w-3 flex-none items-center justify-center'

export function AgentRow({
  option,
  picked,
  isDefault,
  blockedByLimit,
  model,
  onToggle,
  onSelectModel,
  onRowPicked,
}: {
  option: AgentBackendOption
  /** 这一行是否已勾选 */
  picked: boolean
  /** 是否是会话默认后端（名字后面挂「默认」徽标） */
  isDefault: boolean
  /** 已选满且这一行没被选中：点不动 */
  blockedByLimit: boolean
  /** 这一行已指定的模型（空串 = 未指定，用 `option.default_model` 预填） */
  model: string
  onToggle: (kind: string) => void
  onSelectModel: (kind: string, model: string) => void
  /** 勾选成功后收起菜单（模型下拉是独立控件，不受此影响） */
  onRowPicked: () => void
}) {
  const blocked = !option.available || blockedByLimit
  // 徽标会被这个 aria-label 盖掉，所以「默认」必须并进无障碍名，不能只靠视力
  const checkboxName = isDefault ? `${option.label}，会话默认` : option.label
  const title = !option.available
    ? option.reason
    : blockedByLimit
      ? `最多同时问 ${MAX_ANSWERS} 个 AI`
      : option.description

  return (
    <div
      role="option"
      aria-selected={picked}
      aria-disabled={blocked}
      data-testid={`agent-row-${option.kind}`}
      className={`flex w-full items-center gap-1.5 rounded-[7px] px-2 py-1.5 transition-colors ${
        blocked ? 'opacity-55' : 'hover:bg-secondary'
      } ${picked ? 'bg-secondary/60' : ''}`}
    >
      <button
        type="button"
        className={`flex min-w-0 flex-1 items-start gap-1.5 text-left ${blocked ? 'cursor-not-allowed' : ''}`}
        disabled={blocked}
        aria-label={checkboxName}
        aria-checked={picked}
        role="checkbox"
        onClick={() => {
          onToggle(option.kind)
          onRowPicked()
        }}
        title={title}
      >
        <span className={CHECK_CLASS}>{picked && <Check className="h-3 w-3 text-foreground" aria-hidden />}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[12.5px] font-medium text-foreground">
            {option.label}
            {isDefault && (
              <span
                className="ml-1 rounded-[4px] border border-border px-1 text-[10px] font-normal text-muted-foreground"
                title={`会话默认 AI：${option.label}（本轮不选任何 AI 时由它单独作答）`}
              >
                默认
              </span>
            )}
            {/* 没有审批闸门必须在**勾选之前**就看到：勾上它等于放弃高危工具的人工确认 */}
            {noApprovalWarn(option) && <NoApprovalBadge className="ml-1" />}
          </span>
          <span className="block text-[11px] leading-snug text-muted-foreground">
            {option.available ? option.description : option.reason}
          </span>
        </span>
      </button>
      <AgentModelPicker
        models={option.models ?? []}
        value={model}
        defaultModel={option.default_model ?? ''}
        label={option.label}
        // 没勾的行选了模型也不会跑，置灰；不可用的行同理
        disabled={!picked || !option.available}
        disabledHint={
          option.available
            ? '先勾选这一行，再选它用哪个模型'
            : option.reason || '该后端当前不可用'
        }
        onChange={(next) => onSelectModel(option.kind, next)}
      />
    </div>
  )
}
