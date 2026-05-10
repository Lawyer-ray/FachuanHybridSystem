/**
 * CaseForm - 案件表单组件（新建/编辑共用）
 *
 * Requirements: 4.2-4.11, 5.3, 5.4, 10.3, 10.5, 10.6
 */

import { useEffect } from 'react'
import { useForm, useFieldArray } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router'
import { Loader2, Save, ArrowLeft, Plus, Trash2, FileCheck } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Form, FormField, FormItem, FormLabel, FormControl, FormMessage,
} from '@/components/ui/form'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

import { useCase } from '../hooks/use-case'
import { useCaseMutations } from '../hooks/use-case-mutations'
import { CauseSelector } from './CauseSelector'
import { FeeCalculator } from './FeeCalculator'
import { CasePartySection } from './CasePartySection'
import { CaseAssignmentSection } from './CaseAssignmentSection'
import { CaseLogSection } from './CaseLogSection'
import { CaseNumberSection } from './CaseNumberSection'
import { AuthoritySection } from './AuthoritySection'
import { generatePath, PATHS } from '@/routes/paths'
import {
  caseFormSchema,
  SIMPLE_CASE_TYPE_LABELS,
  CASE_STATUS_LABELS,
  CASE_STAGE_LABELS,
  LEGAL_STATUS_LABELS,
  AUTHORITY_TYPE_LABELS,
} from '../types'
import type { CaseCreateFull, CaseUpdate } from '../types'

export interface CaseFormProps {
  caseId?: string
  mode: 'create' | 'edit'
}

// Extended schema for create mode with dynamic lists
const createFormSchema = caseFormSchema.extend({
  parties: z.array(z.object({
    client_id: z.number({ error: '请输入客户ID' }).int().positive('请输入有效的客户ID'),
    legal_status: z.string().optional(),
  })).default([]),
  assignments: z.array(z.object({
    lawyer_id: z.number({ error: '请输入律师ID' }).int().positive('请输入有效的律师ID'),
  })).default([]),
  authorities: z.array(z.object({
    name: z.string().optional(),
    authority_type: z.string().optional(),
  })).default([]),
})

type CreateFormData = z.infer<typeof createFormSchema>

export function CaseForm({ caseId, mode }: CaseFormProps) {
  const navigate = useNavigate()
  const isEditMode = mode === 'edit'

  const { data: caseData, isLoading: isLoadingCase, error: caseError } = useCase(caseId || '')
  const { createCaseFull, updateCase } = useCaseMutations()

  // Always use createFormSchema - in edit mode the extra fields are just empty arrays
  const form = useForm<CreateFormData>({
    resolver: zodResolver(createFormSchema) as never,
    defaultValues: {
      name: '',
      case_type: undefined,
      status: 'active',
      is_filed: false,
      cause_of_action: null,
      current_stage: null,
      target_amount: null,
      preservation_amount: null,
      effective_date: null,
      specified_date: null,
      parties: [],
      assignments: [],
      authorities: [],
    },
  })

  const { fields: partyFields, append: appendParty, remove: removeParty } = useFieldArray({
    control: form.control,
    name: 'parties',
  })
  const { fields: assignmentFields, append: appendAssignment, remove: removeAssignment } = useFieldArray({
    control: form.control,
    name: 'assignments',
  })
  const { fields: authorityFields, append: appendAuthority, remove: removeAuthority } = useFieldArray({
    control: form.control,
    name: 'authorities',
  })

  // Pre-fill form in edit mode
  useEffect(() => {
    if (isEditMode && caseData) {
      form.reset({
        name: caseData.name,
        case_type: (caseData.case_type as CreateFormData['case_type']) ?? undefined,
        status: (caseData.status as 'active' | 'closed') ?? 'active',
        is_filed: caseData.is_filed ?? false,
        cause_of_action: caseData.cause_of_action ?? null,
        current_stage: caseData.current_stage ?? null,
        target_amount: caseData.target_amount ?? null,
        preservation_amount: caseData.preservation_amount ?? null,
        effective_date: caseData.effective_date ?? null,
        specified_date: caseData.specified_date ?? null,
        parties: [],
        assignments: [],
        authorities: [],
      })
    }
  }, [isEditMode, caseData, form])

  const watchTargetAmount = form.watch('target_amount')
  const watchPreservationAmount = form.watch('preservation_amount')
  const watchCaseType = form.watch('case_type')
  const watchCauseOfAction = form.watch('cause_of_action')

  const onSubmit = (data: CreateFormData) => {
    if (isEditMode && caseId) {
      // Build partial update with only changed fields
      const update: CaseUpdate = {}
      if (data.name !== caseData?.name) update.name = data.name
      if (data.case_type !== caseData?.case_type) update.case_type = data.case_type
      if (data.status !== caseData?.status) update.status = data.status
      if (data.is_filed !== caseData?.is_filed) update.is_filed = data.is_filed
      if (data.cause_of_action !== caseData?.cause_of_action) update.cause_of_action = data.cause_of_action
      if (data.current_stage !== caseData?.current_stage) update.current_stage = data.current_stage
      if (data.target_amount !== caseData?.target_amount) update.target_amount = data.target_amount
      if (data.preservation_amount !== caseData?.preservation_amount) update.preservation_amount = data.preservation_amount
      if (data.effective_date !== caseData?.effective_date) update.effective_date = data.effective_date
      if (data.specified_date !== caseData?.specified_date) update.specified_date = data.specified_date

      updateCase.mutate({ id: caseId, data: update }, {
        onSuccess: () => {
          toast.success('保存成功')
          navigate(generatePath.caseDetail(caseId))
        },
        onError: (e) => toast.error(e.message || '保存失败'),
      })
    } else {
      // Create mode - build full payload
      const payload: CaseCreateFull = {
        case: {
          name: data.name,
          case_type: data.case_type,
          status: data.status,
          is_filed: data.is_filed,
          cause_of_action: data.cause_of_action,
          current_stage: data.current_stage,
          target_amount: data.target_amount,
          preservation_amount: data.preservation_amount,
          effective_date: data.effective_date,
          specified_date: data.specified_date,
        },
        parties: data.parties?.filter(p => p.client_id).map(p => ({
          client_id: p.client_id,
          legal_status: p.legal_status,
        })),
        assignments: data.assignments?.filter(a => a.lawyer_id).map(a => ({
          lawyer_id: a.lawyer_id,
        })),
        supervising_authorities: data.authorities?.filter(a => a.name).map(a => ({
          name: a.name,
          authority_type: a.authority_type,
        })),
      }

      createCaseFull.mutate(payload, {
        onSuccess: (res) => {
          toast.success('创建成功')
          navigate(generatePath.caseDetail(String(res.case.id)))
        },
        onError: (e) => toast.error(e.message || '创建失败'),
      })
    }
  }

  if (isEditMode && isLoadingCase) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="text-muted-foreground size-8 animate-spin" />
      </div>
    )
  }

  if (isEditMode && caseError) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive mb-4">加载案件数据失败</p>
        <Button variant="outline" onClick={() => navigate(-1)}>返回</Button>
      </div>
    )
  }

  const isPending = createCaseFull.isPending || updateCase.isPending

  return (
    <div className="space-y-3">
      {/* Page Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <button
          type="button"
          className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => navigate(isEditMode && caseId ? generatePath.caseDetail(caseId) : PATHS.ADMIN_CASES)}
        >
          <ArrowLeft className="size-4" />
          <span className="text-sm font-medium">
            {isEditMode ? '编辑案件' : '新建案件'}
          </span>
        </button>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => navigate(isEditMode && caseId ? generatePath.caseDetail(caseId) : PATHS.ADMIN_CASES)}
            disabled={isPending}
          >
            取消
          </Button>
          <Button
            type="submit"
            size="sm"
            className="h-8 text-xs"
            form="case-form"
            disabled={isPending}
          >
            {isPending ? (
              <><Loader2 className="mr-1 size-3.5 animate-spin" /> 保存中...</>
            ) : (
              <><Save className="mr-1 size-3.5" /> 保存</>
            )}
          </Button>
        </div>
      </div>

      <Form {...form}>
        <form id="case-form" onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
          {/* 案件信息 — 3列紧凑网格 */}
          <Card className="py-4">
            <CardHeader className="px-4 py-0 pb-1.5">
              <CardTitle className="text-sm font-semibold">案件信息</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <div className="grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
                <FormField control={form.control} name="name" render={({ field }) => (
                  <FormItem className="lg:col-span-2">
                    <FormLabel>案件名称 <span className="text-destructive">*</span></FormLabel>
                    <FormControl>
                      <Input placeholder="请输入案件名称" disabled={isPending} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                  <FormField control={form.control} name="case_type" render={({ field }) => (
                    <FormItem>
                      <FormLabel>案件类型</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value ?? ''} disabled={isPending}>
                        <FormControl>
                          <SelectTrigger className="w-full"><SelectValue placeholder="请选择案件类型" /></SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {Object.entries(SIMPLE_CASE_TYPE_LABELS).map(([v, l]) => (
                            <SelectItem key={v} value={v}>{l.zh}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )} />

                  <FormField control={form.control} name="status" render={({ field }) => (
                    <FormItem>
                      <FormLabel>状态</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value} disabled={isPending}>
                        <FormControl>
                          <SelectTrigger className="w-full"><SelectValue placeholder="请选择状态" /></SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {Object.entries(CASE_STATUS_LABELS).map(([v, l]) => (
                            <SelectItem key={v} value={v}>{l.zh}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )} />

                  <FormField control={form.control} name="cause_of_action" render={({ field }) => (
                    <FormItem>
                      <FormLabel>案由</FormLabel>
                      <FormControl>
                        <CauseSelector value={field.value ?? null} onChange={field.onChange} caseType={watchCaseType} disabled={isPending} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )} />

                  <FormField control={form.control} name="current_stage" render={({ field }) => (
                    <FormItem>
                      <FormLabel>当前阶段</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value ?? ''} disabled={isPending}>
                        <FormControl>
                          <SelectTrigger className="w-full"><SelectValue placeholder="请选择阶段" /></SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {Object.entries(CASE_STAGE_LABELS).map(([v, l]) => (
                            <SelectItem key={v} value={v}>{l.zh}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )} />
                <FormField control={form.control} name="effective_date" render={({ field }) => (
                  <FormItem>
                    <FormLabel>生效日期</FormLabel>
                    <FormControl>
                      <Input type="date" disabled={isPending} value={field.value ?? ''} onChange={(e) => field.onChange(e.target.value || null)} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                <FormField control={form.control} name="specified_date" render={({ field }) => (
                  <FormItem>
                    <FormLabel>指定日期</FormLabel>
                    <FormControl>
                      <Input type="date" disabled={isPending} value={field.value ?? ''} onChange={(e) => field.onChange(e.target.value || null)} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                <FormField control={form.control} name="target_amount" render={({ field }) => (
                  <FormItem>
                    <FormLabel>标的金额</FormLabel>
                    <FormControl>
                      <Input type="number" placeholder="请输入" disabled={isPending} value={field.value ?? ''} onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                <FormField control={form.control} name="preservation_amount" render={({ field }) => (
                  <FormItem>
                    <FormLabel>保全金额</FormLabel>
                    <FormControl>
                      <Input type="number" placeholder="请输入" disabled={isPending} value={field.value ?? ''} onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                <FormField control={form.control} name="is_filed" render={({ field }) => (
                  <FormItem className="flex flex-row items-center gap-2.5 space-y-0 pt-5">
                    <FormControl>
                      <Switch checked={field.value ?? false} onCheckedChange={field.onChange} disabled={isPending} />
                    </FormControl>
                    <div className="flex items-center gap-1.5">
                      <FileCheck className="size-3.5 text-muted-foreground" />
                      <FormLabel className="text-xs font-normal cursor-pointer">已建档</FormLabel>
                    </div>
                    <FormMessage />
                  </FormItem>
                )} />
              </div>

              <div className="mt-2.5">
                <FeeCalculator
                  targetAmount={watchTargetAmount}
                  preservationAmount={watchPreservationAmount}
                  caseType={watchCaseType}
                  causeOfAction={watchCauseOfAction ?? undefined}
                  embedded
                />
              </div>
            </CardContent>
          </Card>

          {/* Create mode: 当事人 + 律师并排 */}
          {!isEditMode && (
            <>
              <div className="grid gap-3 lg:grid-cols-2">
                <Card className="py-4">
                  <CardHeader className="px-4 py-0 pb-1.5">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-semibold">当事人</CardTitle>
                      <Button type="button" variant="outline" size="xs" className="h-6 px-2 text-[11px]" onClick={() => appendParty({ client_id: 0, legal_status: '' })}>
                        <Plus className="size-3 mr-0.5" /> 添加
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="px-4 pb-4 space-y-1.5">
                    {partyFields.length === 0 && <p className="text-muted-foreground text-xs">暂无当事人</p>}
                    {partyFields.map((field, index) => (
                      <div key={field.id} className="flex items-end gap-2">
                        <FormField control={form.control} name={`parties.${index}.client_id`} render={({ field: f }) => (
                          <FormItem className="flex-1">
                            <FormControl>
                              <Input type="number" placeholder="客户ID" className="h-8 text-xs" value={f.value || ''} onChange={(e) => f.onChange(e.target.value ? Number(e.target.value) : 0)} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )} />
                        <FormField control={form.control} name={`parties.${index}.legal_status`} render={({ field: f }) => (
                          <FormItem className="flex-1">
                            <Select onValueChange={f.onChange} value={f.value ?? ''}>
                              <FormControl>
                                <SelectTrigger className="h-8 text-xs w-full"><SelectValue placeholder="诉讼地位" /></SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {Object.entries(LEGAL_STATUS_LABELS).map(([v, l]) => (
                                  <SelectItem key={v} value={v}>{l.zh}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </FormItem>
                        )} />
                        <Button type="button" variant="ghost" size="icon-xs" onClick={() => removeParty(index)}>
                          <Trash2 className="text-muted-foreground size-3" />
                        </Button>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card className="py-4">
                  <CardHeader className="px-4 py-0 pb-1.5">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-semibold">指派律师</CardTitle>
                      <Button type="button" variant="outline" size="xs" className="h-6 px-2 text-[11px]" onClick={() => appendAssignment({ lawyer_id: 0 })}>
                        <Plus className="size-3 mr-0.5" /> 添加
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="px-4 pb-4 space-y-1.5">
                    {assignmentFields.length === 0 && <p className="text-muted-foreground text-xs">暂未指派律师</p>}
                    {assignmentFields.map((field, index) => (
                      <div key={field.id} className="flex items-end gap-2">
                        <FormField control={form.control} name={`assignments.${index}.lawyer_id`} render={({ field: f }) => (
                          <FormItem className="flex-1">
                            <FormControl>
                              <Input type="number" placeholder="律师ID" className="h-8 text-xs" value={f.value || ''} onChange={(e) => f.onChange(e.target.value ? Number(e.target.value) : 0)} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )} />
                        <Button type="button" variant="ghost" size="icon-xs" onClick={() => removeAssignment(index)}>
                          <Trash2 className="text-muted-foreground size-3" />
                        </Button>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </div>

              <Card className="py-4">
                <CardHeader className="px-4 py-0 pb-1.5">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-semibold">主管机关</CardTitle>
                    <Button type="button" variant="outline" size="xs" className="h-6 px-2 text-[11px]" onClick={() => appendAuthority({ name: '', authority_type: '' })}>
                      <Plus className="size-3 mr-0.5" /> 添加
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="px-4 pb-4 space-y-1.5">
                  {authorityFields.length === 0 && <p className="text-muted-foreground text-xs">暂无主管机关</p>}
                  {authorityFields.map((field, index) => (
                    <div key={field.id} className="flex items-end gap-2">
                      <FormField control={form.control} name={`authorities.${index}.name`} render={({ field: f }) => (
                        <FormItem className="flex-1">
                          <FormControl>
                            <Input placeholder="机关名称" className="h-8 text-xs" {...f} value={f.value ?? ''} />
                          </FormControl>
                        </FormItem>
                      )} />
                      <FormField control={form.control} name={`authorities.${index}.authority_type`} render={({ field: f }) => (
                        <FormItem className="flex-1">
                          <Select onValueChange={f.onChange} value={f.value ?? ''}>
                            <FormControl>
                              <SelectTrigger className="h-8 text-xs w-full"><SelectValue placeholder="机关性质" /></SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {Object.entries(AUTHORITY_TYPE_LABELS).map(([v, l]) => (
                                <SelectItem key={v} value={v}>{l.zh}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </FormItem>
                      )} />
                      <Button type="button" variant="ghost" size="icon-xs" onClick={() => removeAuthority(index)}>
                        <Trash2 className="text-muted-foreground size-3" />
                      </Button>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </>
          )}
        </form>
      </Form>

      {/* Edit mode: related sections */}
      {isEditMode && caseData && (
        <>
          <div className="grid gap-3 lg:grid-cols-2">
            <Card className="py-3">
              <CardContent className="px-4">
                <div className="text-xs font-medium text-muted-foreground mb-1.5">案件当事人</div>
                <CasePartySection parties={caseData.parties ?? []} editable caseId={caseData.id} />
              </CardContent>
            </Card>

            <Card className="py-3">
              <CardContent className="px-4">
                <div className="text-xs font-medium text-muted-foreground mb-1.5">律师指派</div>
                <CaseAssignmentSection assignments={caseData.assignments ?? []} editable caseId={caseData.id} />
              </CardContent>
            </Card>
          </div>

          <Card className="py-3">
            <CardContent className="px-4">
              <div className="text-xs font-medium text-muted-foreground mb-1.5">案件日志</div>
              <CaseLogSection logs={caseData.logs ?? []} editable caseId={caseData.id} />
            </CardContent>
          </Card>

          <div className="grid gap-3 lg:grid-cols-2">
            <Card className="py-3">
              <CardContent className="px-4">
                <div className="text-xs font-medium text-muted-foreground mb-1.5">案号</div>
                <CaseNumberSection caseNumbers={caseData.case_numbers ?? []} editable caseId={caseData.id} />
              </CardContent>
            </Card>

            <Card className="py-3">
              <CardContent className="px-4">
                <div className="text-xs font-medium text-muted-foreground mb-1.5">主管机关</div>
                <AuthoritySection authorities={caseData.supervising_authorities ?? []} editable caseId={caseData.id} />
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

export default CaseForm
