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
import { Loader2, Save, X, Plus, Trash2 } from 'lucide-react'
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
      cause_of_action: null,
      current_stage: null,
      target_amount: null,
      preservation_amount: null,
      effective_date: null,
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
        cause_of_action: caseData.cause_of_action ?? null,
        current_stage: caseData.current_stage ?? null,
        target_amount: caseData.target_amount ?? null,
        preservation_amount: caseData.preservation_amount ?? null,
        effective_date: caseData.effective_date ?? null,
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
      if (data.cause_of_action !== caseData?.cause_of_action) update.cause_of_action = data.cause_of_action
      if (data.current_stage !== caseData?.current_stage) update.current_stage = data.current_stage
      if (data.target_amount !== caseData?.target_amount) update.target_amount = data.target_amount
      if (data.preservation_amount !== caseData?.preservation_amount) update.preservation_amount = data.preservation_amount
      if (data.effective_date !== caseData?.effective_date) update.effective_date = data.effective_date

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
          cause_of_action: data.cause_of_action,
          current_stage: data.current_stage,
          target_amount: data.target_amount,
          preservation_amount: data.preservation_amount,
          effective_date: data.effective_date,
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
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="text-sm" aria-label="Breadcrumb">
        <ol className="flex items-center gap-1.5">
          <li>
            <span
              className="text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
              onClick={() => navigate(PATHS.ADMIN_CASES)}
            >
              案件
            </span>
          </li>
          <li className="text-muted-foreground">/</li>
          {isEditMode && caseData ? (
            <>
              <li>
                <span
                  className="text-muted-foreground hover:text-foreground cursor-pointer transition-colors truncate max-w-[200px] inline-block align-bottom"
                  onClick={() => navigate(generatePath.caseDetail(caseId!))}
                >
                  {caseData.name}
                </span>
              </li>
              <li className="text-muted-foreground">/</li>
              <li className="text-foreground">编辑</li>
            </>
          ) : (
            <li className="text-foreground">新建</li>
          )}
        </ol>
      </nav>

      {/* Basic Info Form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{isEditMode ? '编辑案件信息' : '案件信息'}</CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                {/* name */}
                <FormField control={form.control} name="name" render={({ field }) => (
                  <FormItem>
                    <FormLabel>案件名称 <span className="text-destructive">*</span></FormLabel>
                    <FormControl>
                      <Input placeholder="请输入案件名称" disabled={isPending} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                {/* case_type */}
                <FormField control={form.control} name="case_type" render={({ field }) => (
                  <FormItem>
                    <FormLabel>案件类型</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value ?? ''} disabled={isPending}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="请选择案件类型" />
                        </SelectTrigger>
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

                {/* status */}
                <FormField control={form.control} name="status" render={({ field }) => (
                  <FormItem>
                    <FormLabel>状态</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value} disabled={isPending}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="请选择状态" />
                        </SelectTrigger>
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

                {/* cause_of_action */}
                <FormField control={form.control} name="cause_of_action" render={({ field }) => (
                  <FormItem>
                    <FormLabel>案由</FormLabel>
                    <FormControl>
                      <CauseSelector
                        value={field.value ?? null}
                        onChange={field.onChange}
                        caseType={watchCaseType}
                        disabled={isPending}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                {/* current_stage */}
                <FormField control={form.control} name="current_stage" render={({ field }) => (
                  <FormItem>
                    <FormLabel>当前阶段</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value ?? ''} disabled={isPending}>
                      <FormControl>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="请选择阶段" />
                        </SelectTrigger>
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

                {/* target_amount */}
                <FormField control={form.control} name="target_amount" render={({ field }) => (
                  <FormItem>
                    <FormLabel>标的金额</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        placeholder="请输入标的金额"
                        disabled={isPending}
                        value={field.value ?? ''}
                        onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                {/* preservation_amount */}
                <FormField control={form.control} name="preservation_amount" render={({ field }) => (
                  <FormItem>
                    <FormLabel>保全金额</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        placeholder="请输入保全金额"
                        disabled={isPending}
                        value={field.value ?? ''}
                        onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />

                {/* effective_date */}
                <FormField control={form.control} name="effective_date" render={({ field }) => (
                  <FormItem>
                    <FormLabel>生效日期</FormLabel>
                    <FormControl>
                      <Input
                        type="date"
                        disabled={isPending}
                        value={field.value ?? ''}
                        onChange={(e) => field.onChange(e.target.value || null)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
              </div>

              {/* Dynamic lists - create mode only */}
              {!isEditMode && (
                <div className="space-y-6">
                  {/* Parties */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-medium">当事人</h3>
                      <Button type="button" variant="outline" size="sm" onClick={() => appendParty({ client_id: 0, legal_status: '' })}>
                        <Plus className="mr-1 size-3" /> 添加
                      </Button>
                    </div>
                    {partyFields.map((field, index) => (
                      <div key={field.id} className="flex items-end gap-3">
                        <FormField control={form.control} name={`parties.${index}.client_id`} render={({ field: f }) => (
                          <FormItem className="flex-1">
                            {index === 0 && <FormLabel>客户ID</FormLabel>}
                            <FormControl>
                              <Input
                                type="number"
                                placeholder="客户ID"
                                value={f.value || ''}
                                onChange={(e) => f.onChange(e.target.value ? Number(e.target.value) : 0)}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )} />
                        <FormField control={form.control} name={`parties.${index}.legal_status`} render={({ field: f }) => (
                          <FormItem className="flex-1">
                            {index === 0 && <FormLabel>诉讼地位</FormLabel>}
                            <Select onValueChange={f.onChange} value={f.value ?? ''}>
                              <FormControl>
                                <SelectTrigger className="w-full">
                                  <SelectValue placeholder="选择地位" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {Object.entries(LEGAL_STATUS_LABELS).map(([v, l]) => (
                                  <SelectItem key={v} value={v}>{l.zh}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </FormItem>
                        )} />
                        <Button type="button" variant="ghost" size="icon" onClick={() => removeParty(index)}>
                          <Trash2 className="text-muted-foreground size-4" />
                        </Button>
                      </div>
                    ))}
                  </div>

                  {/* Assignments */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-medium">指派律师</h3>
                      <Button type="button" variant="outline" size="sm" onClick={() => appendAssignment({ lawyer_id: 0 })}>
                        <Plus className="mr-1 size-3" /> 添加
                      </Button>
                    </div>
                    {assignmentFields.map((field, index) => (
                      <div key={field.id} className="flex items-end gap-3">
                        <FormField control={form.control} name={`assignments.${index}.lawyer_id`} render={({ field: f }) => (
                          <FormItem className="flex-1">
                            {index === 0 && <FormLabel>律师ID</FormLabel>}
                            <FormControl>
                              <Input
                                type="number"
                                placeholder="律师ID"
                                value={f.value || ''}
                                onChange={(e) => f.onChange(e.target.value ? Number(e.target.value) : 0)}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )} />
                        <Button type="button" variant="ghost" size="icon" onClick={() => removeAssignment(index)}>
                          <Trash2 className="text-muted-foreground size-4" />
                        </Button>
                      </div>
                    ))}
                  </div>

                  {/* Authorities */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-medium">主管机关</h3>
                      <Button type="button" variant="outline" size="sm" onClick={() => appendAuthority({ name: '', authority_type: '' })}>
                        <Plus className="mr-1 size-3" /> 添加
                      </Button>
                    </div>
                    {authorityFields.map((field, index) => (
                      <div key={field.id} className="flex items-end gap-3">
                        <FormField control={form.control} name={`authorities.${index}.name`} render={({ field: f }) => (
                          <FormItem className="flex-1">
                            {index === 0 && <FormLabel>机关名称</FormLabel>}
                            <FormControl>
                              <Input placeholder="机关名称" {...f} value={f.value ?? ''} />
                            </FormControl>
                          </FormItem>
                        )} />
                        <FormField control={form.control} name={`authorities.${index}.authority_type`} render={({ field: f }) => (
                          <FormItem className="flex-1">
                            {index === 0 && <FormLabel>机关性质</FormLabel>}
                            <Select onValueChange={f.onChange} value={f.value ?? ''}>
                              <FormControl>
                                <SelectTrigger className="w-full">
                                  <SelectValue placeholder="选择性质" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {Object.entries(AUTHORITY_TYPE_LABELS).map(([v, l]) => (
                                  <SelectItem key={v} value={v}>{l.zh}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </FormItem>
                        )} />
                        <Button type="button" variant="ghost" size="icon" onClick={() => removeAuthority(index)}>
                          <Trash2 className="text-muted-foreground size-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex flex-col-reverse gap-3 md:flex-row md:justify-end">
                <Button type="button" variant="outline" onClick={() => navigate(PATHS.ADMIN_CASES)} disabled={isPending}>
                  <X className="mr-1 size-4" /> 取消
                </Button>
                <Button type="submit" disabled={isPending}>
                  {isPending ? (
                    <><Loader2 className="mr-1 size-4 animate-spin" /> 保存中...</>
                  ) : (
                    <><Save className="mr-1 size-4" /> 保存</>
                  )}
                </Button>
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>

      {/* Editable sections in edit mode */}
      {isEditMode && caseData && (
        <>
          <CasePartySection parties={caseData.parties ?? []} editable caseId={caseData.id} />
          <CaseAssignmentSection assignments={caseData.assignments ?? []} editable caseId={caseData.id} />
          <CaseLogSection logs={caseData.logs ?? []} editable caseId={caseData.id} />
          <CaseNumberSection caseNumbers={caseData.case_numbers ?? []} editable caseId={caseData.id} />
          <AuthoritySection authorities={caseData.supervising_authorities ?? []} editable caseId={caseData.id} />
        </>
      )}

      {/* Fee Calculator */}
      <FeeCalculator
        targetAmount={watchTargetAmount}
        preservationAmount={watchPreservationAmount}
        caseType={watchCaseType}
        causeOfAction={watchCauseOfAction ?? undefined}
      />
    </div>
  )
}

export default CaseForm
