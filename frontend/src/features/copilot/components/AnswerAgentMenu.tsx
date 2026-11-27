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
 * （触发器摘要、上限计数、禁用态、关闭时机），否则三件事挤在一起必然撞 350 行软红线。
 *
 * ## 关闭时机：勾选**不**关，点外部空白 / Escape 才关
 *
 * 勾选不是「确认」——勾完 Pi 紧接着要给它选模型，勾 2 个以上还得来回给每一行配。
 * 勾一次关一次，用户就得重新开、重新找那一行。所以：
 *
 * - 点菜单内部任何地方（行、模型下拉、底部两句文案）都**不**关；
 * - 点菜单外部空白 → 关（`document` 上的 `pointerdown`，判 ref 的 `contains`）；
 * - `Escape` → 关并把焦点还给触发器（只做这一条键盘路径，不做 roving focus）；
 * - 再点一次触发器 → 关（它自己的 toggle，既有行为）。
 *
 * 用 `pointerdown` 而不是 `click`：`click` 在行内按钮的 `onClick` **之后**才冒到
 * `document`，那时菜单可能已被自己的状态更新卸载、`contains` 判不出东西；按住拖选
 * 时 `pointerdown` 也更贴直觉。
 *
 * ## 上限
 *
 * 选满 {@link MAX_ANSWERS} 后其余项置灰：超出的选择后端会直接 400，而那发生在
 * 用户已经敲了回车之后——置灰比报错便宜得多。
 *
 * ## 本菜单也是「新会话用谁」的唯一入口
 *
 * 顶栏那枚后端单选下拉已删：同一个后端清单在两处可选就是「逻辑重复」，而两处
 * 一旦不一致（右上已选 A、左下勾了 B），用户看到的本轮参与者与实际发生的会话
 * 归属就是两回事。现在归属由这里推导（见 store/turn.ts）：
 *
 * - 勾 1 个 → 本轮只问它，那个后端也就是新会话的 `agent_kind`；
 * - 勾 2 个以上 → 并排对比，会话归属第一个（顺序 = 栏的左右顺序）；
 * - 未勾 → 会话默认后端（下面的「默认」徽标）。
 *
 * 这条规则决定的不仅是这一轮，而是整个会话的后端（建完不可换）。它现在只写在
 * 触发器的 `title` 里，**不再占用菜单底部一行**：2026-11-27 用户反馈「文案太多太乱，
 * 解释说明都可以删」，那两行（归属规则 + 已选 N 个 · 最多 M 个）把菜单底部占
 * 得与列表一样重。视觉上只留一个极简计数 `已选 N/M`，规则靠悬停可达。
 *
 * 代价是「勾 2 个会归到第一个」在触屏上不可见。之所以能接受：勾了第 2 个时
 * 第 1 个本来就排在前面（顺序即栏序），而展现在多答界面上的会话归属会当场
 * 显示在顶栏——不是发现不了的隐性规则。
 *
 * ## 未选 = 单跑会话默认后端（此时触发按钮只剩图标）
 *
 * `selected` 为空数组时本轮只跑一个：会话默认后端。菜单里用「默认」徽标标出它
 * （清单第一项，与新建会话的默认同口径），律师能看出不选时到底是谁在答。
 *
 * 而那个「1 个 AI」的摘要文字被拿掉了：未选是**绝大多数轮次**的常态，写一个含糊的
 * 数量只占输入框宽度（约 60px），信息量还不如菜单里那一行。常态收成纯图标，
 * 选了才出文字（名字 / `N 个 AI`）——文字只在「本轮 ≠ 会话默认」时出现才有意义。
 * 由此，未选态的身份必须由 `aria-label` / `title` 承担（形如
 * 「本轮参与的 AI：会话默认（Pi）；点击选择」），不能只说一句「选择 AI」。
 */

import { useEffect, useRef, useState } from 'react'
import { GitCompare, ChevronDown } from 'lucide-react'

import { DEFAULT_AGENT_KIND, MAX_ANSWERS } from '../domain'
import type { AgentBackendOption } from '../types'
import { findBackend } from '../store/backends'
import { registerQoderByok } from '../api'
import { AgentLoginDialog } from './AgentLoginDialog'
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
  backendsState = 'ready',
  onToggle,
  onSelectModel,
  onRefreshBackends,
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
  /**
   * 清单拉取状态（`store/backends.ts` 的 `backendsState`）。
   *
   * `backends` 为空有三种原因，必须分开说：**正在拉**（短暂，不要归坏）、
   * **拉失败**（给重试）、**真的没有**。三者共用一个「暂不可用」时，用户看到的
   * 只是「系统坏了」，而且旧实现失败后整个页面生命周期都不会再拉。
   * 缺省 `ready`：只关心「有清单」的调用方（测试、只读宿主）不必关心这个状态。
   */
  backendsState?: 'idle' | 'loading' | 'ready' | 'error'
  onToggle: (kind: string) => void
  /** 给某一栏指定模型（空串 = 取消指定） */
  onSelectModel: (kind: string, model: string) => void
  /** 登录成功后重新拉一次清单（那一行从置灰变可选）；缺省 = 不刷新 */
  onRefreshBackends?: () => void
}) {
  const [open, setOpen] = useState(false)
  /** 正在登录的后端 kind（null = 没有弹窗）。登录入口在行内，弹窗挂在本组件末尾。 */
  const [loginKind, setLoginKind] = useState<string | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  // 关闭途径只有三条（勾选**不**在其中，见文件头）：外部 pointerdown、Escape、
  // 再点触发器（走它自己的 toggle）。监听只在 open 时挂着，关掉就摘。
  //
  // ref 挂在外壳（含触发器）而不是只挂浮层：只挂浮层的话，点触发器会先被判成
  // 「外部」关掉、再被 onClick 翻回打开，那枚按钮就再也关不掉菜单了。
  useEffect(() => {
    if (!open) return
    const onDown = (event: Event) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (rootRef.current?.contains(target)) return
      setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      // 浮层关掉后焦点不能留在已卸载的节点里：还给触发器，键盘用户不用从头 Tab
      triggerRef.current?.focus()
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  // 清单没拉到时也要能显示「这家是谁」：kind 原文比空白可读
  const names = selected.map((kind) => findBackend(backends, kind)?.label ?? kind)
  // 空串 = 未选（不显示摘要文字，只留图标）
  const summary = names.length === 0 ? '' : names.length === 1 ? (names.at(0) ?? '') : `${names.length} 个 AI`
  // 未选时「本轮到底谁在跑」只能靠菜单里的默认项：触发器上补一个默认后端名
  const fallbackKind = defaultKind || DEFAULT_AGENT_KIND
  const defaultLabel = findBackend(backends, fallbackKind)?.label ?? fallbackKind
  const active = selected.length > 1 || (selected.length === 1 && selected[0] !== defaultKind)
  const full = selected.length >= MAX_ANSWERS
  // 两句缩成一句：归属规则搬到这里（菜单里那行已删），但仍保留「最多 N 个」——
  // 它是产品上限，不是解释
  const usageTitle = `本轮问哪几个 AI（最多 ${MAX_ANSWERS} 个）。勾 1 个＝只问它、新会话也归它；勾多个＝并排对比、归属第一个。`

  const loginOption = loginKind ? findBackend(backends, loginKind) : undefined

  return (
    <>
    <div ref={rootRef} className="relative flex-none">
      <button
        ref={triggerRef}
        type="button"
        className={`${TRIGGER_CLASS} ${
          active ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
        }`}
        onClick={() => {
          // 空清单时顺手重拉一次：加载失败后旧实现永不重试，用户只能刷页。
          // 只在 `idle`/`error` 时拉——`ready` 且空是真的没有后端，重拉没意义。
          if (!open && backends.length === 0 && (backendsState === 'idle' || backendsState === 'error')) {
            onRefreshBackends?.()
          }
          setOpen((v) => !v)
        }}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={summary ? `本轮参与的 AI：${summary}` : `本轮参与的 AI：会话默认（${defaultLabel}）；点击选择`}
        title={
          disabled
            ? hint || '本轮正在进行，结束前不能改参与方'
            : summary
              ? usageTitle
              : `本轮不选 = 单跑会话默认 AI（${defaultLabel}）。${usageTitle}`
        }
      >
        <GitCompare className="h-4 w-4 flex-none" />
        {/* 未选 = 只有图标（省输入框宽度）；有摘要才连文字与下拉箭头一起出 */}
        {summary && (
          <>
            <span className="max-w-24 truncate">{summary}</span>
            <ChevronDown className="h-3 w-3 flex-none" aria-hidden />
          </>
        )}
      </button>
      {open && (
        <div
          role="listbox"
          aria-label="可选 AI（多选）"
          aria-multiselectable
          className="absolute bottom-full left-0 z-[120] mb-1 w-80 rounded-[10px] border border-border bg-popover p-1 shadow-md"
        >
          {backends.length === 0 && (
            <p className="px-2 py-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
              {backendsState === 'loading' ? (
                '正在拉取 AI 清单…'
              ) : backendsState === 'error' ? (
                <>
                  AI 清单没拉到
                  {onRefreshBackends && (
                    <button
                      type="button"
                      onClick={onRefreshBackends}
                      className="ml-1 rounded-[5px] border border-border px-1.5 py-0.5 text-foreground hover:bg-secondary"
                    >
                      重试
                    </button>
                  )}
                </>
              ) : (
                '后端清单为空，本轮使用默认 AI。'
              )}
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
              onLogin={(kind) => {
                // 先收起菜单：弹窗要占屏，菜单还浮在上面会盖住授权按钮
                setOpen(false)
                setLoginKind(kind)
              }}
              // 「接入我的模型」= 把 AI 平台里的网关注册成 qoder 的 BYOK provider，
              // 之后模型清单里会出现 <provider>/<model> 这一批（要重拉清单才看得到）
              onRegisterPlatform={
                option.kind === 'qoder'
                  ? () => {
                      void registerQoderByok()
                        .then(() => onRefreshBackends?.())
                        .catch(() => onRefreshBackends?.())
                    }
                  : undefined
              }
            />
          ))}
          {/* 只留计数：`已选 2/5` 一眼看完，不再写「个」与「最多」两个字 */}
          <p className="px-2 py-1 text-[11px] tabular-nums text-muted-foreground">
            已选 {selected.length}/{MAX_ANSWERS}
          </p>
        </div>
      )}
    </div>
    {loginKind && (
      <AgentLoginDialog
        kind={loginKind}
        label={loginOption?.label ?? loginKind}
        onClose={() => setLoginKind(null)}
        onDone={() => {
          setLoginKind(null)
          onRefreshBackends?.()
        }}
      />
    )}
    </>
  )
}
