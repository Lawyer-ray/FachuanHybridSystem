import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { projectDetail } from '@/app/paths'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { errMessage } from '@/lib/errors'

import { updateContract } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import type { ContractListItem, ContractUpdatePayload } from '../../types'
import { UnsavedChangesDialog } from '../deal-detail/UnsavedChangesDialog'
import { refetchContractAndCases } from '../deal-detail/refetch-contract'
import { useDocDirtyGuard } from '../deal-detail/use-doc-dirty-guard'
import { BasicFieldsSection } from './BasicFieldsSection'
import { FinanceFieldsSection } from './FinanceFieldsSection'
import {
  formFromContract,
  toUpdatePayload,
  validateForm,
  type FormErrors,
  type ProjectEditForm as FormModel,
} from './project-edit-form'

/**
 * 编辑表单本体（数据已到位后渲染，初值由父级的 `key` 收口）。
 *
 * 提交链路刻意做成「一次 PUT + 三件事」：
 * - **只发脏字段**（后端 `exclude_unset`：不传=不动，传 null=真清空）；
 * - 财务四字段出现就必须 `confirm_finance=true`，且后端要管理员——所以先弹一次
 *   确认，把「会记财务日志 / 需要管理员」讲在按钮之前；
 * - `status` 改「已归档」会把该项目下所有在办案件一起结案（不可逆），同样必须确认。
 */
export function ProjectEditForm({ contract }: { contract: ContractListItem }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [form, setForm] = useState<FormModel>(() => formFromContract(contract))
  const [errors, setErrors] = useState<FormErrors>({})
  const [saving, setSaving] = useState(false)
  /** 待确认的提交（财务改动 / 归档结案）：确认后才真的发请求 */
  const [pending, setPending] = useState<{
    payload: ContractUpdatePayload
    finance: boolean
    archive: boolean
  } | null>(null)

  const { payload, confirmFinance } = useMemo(() => toUpdatePayload(form, contract), [form, contract])
  const dirty = Object.keys(payload).length > 0
  const archiveNow = payload.status === 'archived' && contract.status !== 'archived'

  const doc = useDocDirtyGuard()
  const guardDirty = doc.guard
  const markDirty = doc.markDirty

  // 表单脏 → 同一套守卫（取消/返回时问一句）；关页签另走原生提示
  useEffect(() => {
    markDirty(dirty)
  }, [dirty, markDirty])
  useEffect(() => {
    if (!dirty) return
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])

  const onChange = useCallback((patch: Partial<FormModel>) => {
    setForm((prev) => ({ ...prev, ...patch }))
  }, [])

  const back = useCallback(() => {
    guardDirty(() => void navigate(projectDetail(contract.id)))
  }, [guardDirty, navigate, contract.id])

  const doSave = async (body: ContractUpdatePayload, finance: boolean) => {
    setSaving(true)
    try {
      const updated = await updateContract(contract.id, body, { confirmFinance: finance })
      // 先落缓存：返回详情页立刻是新值，不用等一次往返
      qc.setQueryData(workbenchKeys.contract(contract.id), updated)
      // 状态/案型会影响左栏案件卡，统一走这组刷新（与详情页写操作同口径）
      refetchContractAndCases(qc, contract.id)
      toast.success('已保存')
      markDirty(false)
      void navigate(projectDetail(contract.id), { replace: true })
    } catch (e) {
      // 后端 400「关键财务操作需二次确认」/403「修改财务数据需要管理员权限」原样透出
      toast.error(errMessage(e, '保存失败'), { duration: 8000 })
    } finally {
      setSaving(false)
    }
  }

  const submit = () => {
    const found = validateForm(form)
    setErrors(found)
    if (Object.keys(found).length > 0) {
      toast.error('还有字段需要修正')
      return
    }
    if (!dirty) return
    if (confirmFinance || archiveNow) {
      setPending({ payload, finance: confirmFinance, archive: archiveNow })
      return
    }
    void doSave(payload, false)
  }

  return (
    <main className="app-page-enter mx-auto max-w-[820px] px-[30px] pt-[26px] pb-24 max-[680px]:px-3 max-[680px]:pt-4">
      <nav className="mb-2 flex items-center gap-1.5 text-[12px] text-muted-foreground">
        {/* 面包屑也是「离开」：有未保存改动时同样要拦一下，否则它成了守卫的漏口 */}
        <Link
          to="/projects"
          className="hover:text-foreground"
          onClick={(e) => {
            e.preventDefault()
            guardDirty(() => void navigate('/projects'))
          }}
        >
          项目
        </Link>
        <span>/</span>
        <Link
          to={projectDetail(contract.id)}
          className="max-w-[360px] truncate hover:text-foreground"
          onClick={(e) => {
            e.preventDefault()
            back()
          }}
        >
          {contract.name}
        </Link>
        <span>/</span>
        <span className="text-secondary-foreground">编辑</span>
      </nav>

      <div className="mb-5 flex flex-wrap items-baseline gap-3">
        <h1 className="text-[21px] leading-[1.4] font-[740] tracking-[-0.02em]">编辑项目</h1>
        <span className="text-[12px] text-muted-foreground">
          只提交改动过的字段；没改的地方不会被覆盖
        </span>
      </div>

      <form
        className="flex flex-col gap-5 rounded-[12px] border border-border bg-card px-6 py-5 shadow-sm max-[680px]:px-4"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <BasicFieldsSection form={form} errors={errors} onChange={onChange} />
        <FinanceFieldsSection form={form} errors={errors} onChange={onChange} />

        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={!dirty || saving}>
            {saving && <Loader2 className="mr-1 size-3.5 animate-spin" />}
            保存
          </Button>
          <Button type="button" variant="outline" onClick={back} disabled={saving}>
            取消
          </Button>
          <span className="ml-auto text-[11.5px] text-muted-foreground/80">
            {dirty ? '有未保存的改动' : '没有改动'}
          </span>
        </div>
      </form>

      {/* 财务 / 归档的二次确认：把代价写在按钮之前，不做事后追认 */}
      <AlertDialog open={pending !== null} onOpenChange={(v) => !v && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending?.archive && pending?.finance
                ? '确认归档并修改收费？'
                : pending?.archive
                  ? '确认把项目归档？'
                  : '确认修改收费？'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pending?.finance && '改动收费会记一条财务日志，且需要管理员权限（否则会被后端拒绝）。'}
              {pending?.archive &&
                '归档会把本项目下所有在办案件一起结案，而且改回「在办」不会自动重开。'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>再看看</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (!pending) return
                const { payload: body, finance } = pending
                setPending(null)
                void doSave(body, finance)
              }}
            >
              确认保存
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <UnsavedChangesDialog
        open={doc.pending}
        onStay={doc.stay}
        onLeave={doc.leave}
        title="表单里还有没保存的改动"
        description="现在离开，刚才改的字段都不会保存。"
        stayLabel="继续编辑"
        leaveLabel="放弃改动"
      />
    </main>
  )
}
