/**
 * 「回传后核对内容」勾选框（受控）。
 *
 * 样式与 `AssignModal` 底部「同时归档到案件文件夹」那个勾选逐字对齐——两个勾选项
 * 上下相邻，视觉上必须是同一种东西，否则律师会以为其中一个更重要。
 *
 * ## 两种模式：跟着案件走，还是跟着偏好走
 *
 * - **选中了既有案件（给了 `caseId`）**：勾选值以**该案的服务端策略**为准
 *   （`getPolicy`），切换即 `putPolicy`，写失败回滚到服务端值并 toast。之前这里
 *   只看模块级偏好：同事在服务端关掉了这个案的核对，弹窗里照样打着勾——界面在说
 *   一句它没有证据的话，客户回传时却什么也不核，而且没有任何报错。
 * - **还没选案件（无 `caseId`）**：案子都还不存在，没有服务端值可读、也没有案件
 *   可写，勾选就是律师的偏好（`use-assign-launch` 的模块级变量），归案成功后由
 *   `saveVerifyPolicy` 写进新建出来的案子。
 *
 * 两种模式下 `onChange` 都照常回调：模块级偏好要跟着律师的选择走，下次开弹窗才不
 * 弹回。区别只是有 `caseId` 时真正落库的是本组件的 `putPolicy`，而不是归案后的
 * `saveVerifyPolicy`（后者只管新建案件）。
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { getPolicy, putPolicy, type PolicyOut } from './api'

/** 该案策略的 query key：写成功后按它把服务端返回的全量写回缓存，界面自此显示真值。 */
function policyKey(caseId: number) {
  return ['doc-verify-policy', caseId] as const
}

/**
 * 勾选框对应的是「四类高风险文书**一起**核」（写入时 `doc_types: []` = 改全部），
 * 所以只有全开才算勾上：只有一部分开着时显示未勾，点它是把这四类一起开。
 */
function allEnabled(policy: PolicyOut): boolean {
  return policy.items.every((item) => item.enabled)
}

/** 勾选框本体：文案、外观、受控接线只有这一份，两种模式共用。 */
function ToggleBox({
  checked,
  disabled = false,
  onChange,
}: {
  checked: boolean
  disabled?: boolean
  onChange: (next: boolean) => void
}) {
  return (
    <label
      className={cn(
        'mt-1.5 flex items-start gap-2 text-[12.5px]',
        disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
      )}
    >
      <input
        type="checkbox"
        className="mt-0.5"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        回传后核对内容（起诉状 / 授权委托书 / 送达地址确认书 / 退费账户确认书）
        <span className="mt-0.5 block text-[11.5px] text-muted-foreground">
          勾选的文书在客户回传后逐页比对整本正文（扫描件走本地 OCR，40 页约 1 分钟）
        </span>
      </span>
    </label>
  )
}

export function PolicyToggle({
  caseId,
  checked,
  onChange,
}: {
  /** 选中的既有案件 id；新建案件时没有（没有服务端策略可读，也还没有案件可写） */
  caseId?: number
  /** 偏好值：无 `caseId` 时就是勾选值；有 `caseId` 时只在服务端值还没到手（或读失败）时兜底 */
  checked: boolean
  onChange: (next: boolean) => void
}) {
  // 还没选案件：没有服务端值、也没有案件可写，纯偏好（与改动前行为一致）。
  // 这一支不挂任何 hook —— 偏好模式不需要 QueryClient，单测可以直接渲染。
  if (caseId === undefined) return <ToggleBox checked={checked} onChange={onChange} />
  return <CasePolicyToggle caseId={caseId} preference={checked} onChange={onChange} />
}

/** 选中既有案件后：勾选值读该案的服务端策略，切换即写服务端。 */
function CasePolicyToggle({
  caseId,
  preference,
  onChange,
}: {
  caseId: number
  preference: boolean
  onChange: (next: boolean) => void
}) {
  const queryClient = useQueryClient()
  const policy = useQuery({
    queryKey: policyKey(caseId),
    queryFn: ({ signal }) => getPolicy(caseId, signal),
  })
  // 写入在途期间要显示的值（乐观）。带着 case id：切换案件后，上一个案子的在途值
  // 不会被当成这个案子的勾选态。
  const [optimistic, setOptimistic] = useState<{ caseId: number; enabled: boolean } | null>(null)
  const save = useMutation({
    // case id 跟着变量走（不是闭包）：切换案件后旧请求才回来时，回写缓存的仍是发起
    // 那次请求的案件，不会把 A 案的结果写进 B 案的 key。
    mutationFn: (input: { caseId: number; enabled: boolean }) =>
      putPolicy({ case_id: input.caseId, enabled: input.enabled, doc_types: [] }),
    onSuccess: (saved, input) => {
      // 先落到后端回传的真值，再摘掉乐观值（顺序反了会闪一下旧值）
      queryClient.setQueryData(policyKey(input.caseId), saved)
      setOptimistic(null)
    },
    onError: (error) => {
      // 摘掉乐观值即回滚：缓存里还是上一次读到的服务端值（不是「上一个 props」）
      setOptimistic(null)
      toast.error(`核对设置未保存：${errMessage(error, '未知错误')}`)
    },
  })

  // 服务端值：读到了才用它。还没读到（或读失败）时退回偏好——那是律师上一次的选择；
  // 而他一旦切换，写进去的是绝对值，不会把「不知道」当成「关着」写进库里。
  const serverEnabled = policy.data ? allEnabled(policy.data) : undefined
  const shown =
    (optimistic?.caseId === caseId ? optimistic.enabled : undefined) ?? serverEnabled ?? preference
  // 读服务端值期间禁点：拿偏好默认值去写库，会把同事在服务端做的设置悄悄改掉。
  const disabled = policy.isPending || save.isPending

  return (
    <>
      <ToggleBox
        checked={shown}
        disabled={disabled}
        onChange={(next) => {
          // 偏好照旧更新（新建案件直接读它；下次开弹窗按它，不弹回）
          onChange(next)
          // 禁点期间不写库：disabled 已经挡住用户点击，这里再挡一次程序化触发的事件
          if (disabled) return
          // 先跟着手走（不等往返），再发请求；成败都在 mutation 回调里落定
          setOptimistic({ caseId, enabled: next })
          save.mutate({ caseId, enabled: next })
        }}
      />
      {policy.isError && (
        <div className="mt-0.5 text-[11.5px] text-amber-700">
          本案核对设置读取失败：{errMessage(policy.error, '未知错误')}——勾选显示的是上次的选择
        </div>
      )}
    </>
  )
}
