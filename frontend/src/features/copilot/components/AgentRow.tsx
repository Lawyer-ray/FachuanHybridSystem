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

/** 左侧勾选区（视觉上 12px 见方，与 AnswerAgentMenu 的行口径一致：只画对勾不画方框） */
const CHECK_CLASS = 'mt-0.5 flex h-3 w-3 flex-none items-center justify-center'

export function AgentRow({
  option,
  picked,
  isDefault,
  blockedByLimit,
  model,
  onToggle,
  onSelectModel,
  onLogin,
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
  /** 这一行需要登录时（`option.action === 'login'`）点「登录」的回调 */
  onLogin?: (kind: string) => void
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
      className={`flex w-full items-center gap-1.5 rounded-[7px] px-2 py-1 transition-colors ${
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
        // 勾选只改这一行的状态，不收起菜单：勾完往往还要在同一行选模型
        onClick={() => onToggle(option.kind)}
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
          {/* 单行截断：两行说明会把 8 个后端撑成一屏装不下，而完整内容在 title 里 */}
          <span className="block truncate text-[11px] leading-snug text-muted-foreground" title={title}>
            {option.available ? option.description : option.reason}
          </span>
        </span>
      </button>
      {/* 需要登录的行给一个**真按得动**的入口：只置灰不给动作，用户唯一的结论是
          「这个功能坏了」。按钮文案说清登的是哪一家（`action_label` 由后端给）。 */}
      {option.action === 'login' && onLogin && (
        <button
          type="button"
          onClick={() => onLogin(option.kind)}
          data-testid={`agent-login-${option.kind}`}
          className="flex-none rounded-[6px] border border-border px-1.5 py-0.5 text-[11px] text-foreground hover:bg-secondary"
          title={option.action_label || `登录 ${option.label}`}
        >
          {option.action_label || `登录 ${option.label}`}
        </button>
      )}
      {/* 模型下拉只在**勾上之后**出现：未勾的行它只是一个「置灰的按钮」，却把每行
          挤掉约 140px 宽与一行高度——8 个后端时整张菜单就是密密麻麻的灰块。
          勾选是「这一轮要问它」，模型是「它用哪个」，顺序本来就该是先勾后配。 */}
      {picked && (
        <AgentModelPicker
          models={option.models ?? []}
          value={model}
          defaultModel={option.default_model ?? ''}
          label={option.label}
          disabled={!option.available}
          disabledHint={option.reason || '该后端当前不可用'}
          onChange={(next) => onSelectModel(option.kind, next)}
        />
      )}
    </div>
  )
}
