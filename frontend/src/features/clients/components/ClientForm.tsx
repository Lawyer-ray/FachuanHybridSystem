/**
 * ClientForm - 当事人表单组件
 * 新建模式：企业搜索 + 智能解析 + 表单
 * 编辑模式：表单 + 财产线索 Tab + 证件管理 Tab
 */

import { useEffect, useCallback, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Save, X, Upload, CheckCircle2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Form, FormField, FormItem, FormLabel, FormControl, FormMessage, FormDescription,
} from '@/components/ui/form'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

import { useClient } from '../hooks/use-client'
import { useClientMutations } from '../hooks/use-client-mutations'
import { clientApi } from '../api'
import { EnterpriseSearch } from './EnterpriseSearch'
import { TextParser } from './TextParser'
import { PropertyClueList } from './PropertyClueList'
import { IdentityDocManager } from './IdentityDocManager'
import { generatePath } from '@/routes/paths'
import type { ClientType, ClientFormMode, ClientInput, EnterprisePrefillData } from '../types'
import { CLIENT_TYPE_LABELS } from '../types'

export interface ClientFormProps {
  clientId?: string
  mode: ClientFormMode
}

const clientTypeValues = ['natural', 'legal', 'non_legal_org'] as const

const clientFormSchema = z
  .object({
    name: z.string().min(1, '姓名不能为空'),
    client_type: z.enum(clientTypeValues, { message: '请选择当事人类型' }),
    id_number: z.string().optional(),
    phone: z.string().optional(),
    address: z.string().optional(),
    legal_representative: z.string().optional(),
    legal_representative_id_number: z.string().optional(),
    is_our_client: z.boolean(),
  })
  .refine(
    (data) => data.client_type === 'natural' || !!data.legal_representative,
    { message: '此字段为必填项', path: ['legal_representative'] },
  )

type ClientFormData = z.infer<typeof clientFormSchema>

export function ClientForm({ clientId, mode }: ClientFormProps) {
  const navigate = useNavigate()
  const isEditMode = mode === 'edit'

  const { data: client, isLoading: isLoadingClient, error: clientError } = useClient(clientId || '')
  const { createClient, updateClient } = useClientMutations()

  const form = useForm<ClientFormData>({
    resolver: zodResolver(clientFormSchema),
    defaultValues: {
      name: '', client_type: 'natural', id_number: '', phone: '',
      address: '', legal_representative: '', legal_representative_id_number: '', is_our_client: true,
    },
  })

  const clientType = form.watch('client_type')
  const showLegalRep = clientType !== 'natural'
  const idNumberLabel = clientType === 'natural' ? '身份证号' : '统一社会信用代码'
  const legalRepLabel = clientType === 'non_legal_org' ? '负责人' : '法定代表人'

  // OA 凭证检查
  const { data: oaCredential } = useQuery({
    queryKey: ['oa-credential'],
    queryFn: () => clientApi.checkOaCredential(),
    staleTime: 10 * 60 * 1000,
  })

  // 新建模式下的证件上传
  const [pendingDocs, setPendingDocs] = useState<{ docType: string; file: File }[]>([])
  const docFileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isEditMode && client) {
      form.reset({
        name: client.name, client_type: client.client_type,
        id_number: client.id_number || '', phone: client.phone || '',
        address: client.address || '', legal_representative: client.legal_representative || '',
        legal_representative_id_number: client.legal_representative_id_number || '',
        is_our_client: client.is_our_client,
      })
    }
  }, [isEditMode, client, form])

  // 企业预填回调
  const handleEnterprisePrefill = useCallback((data: EnterprisePrefillData) => {
    if (data.name) form.setValue('name', data.name, { shouldValidate: true })
    if (data.client_type) form.setValue('client_type', data.client_type as ClientFormData['client_type'], { shouldValidate: true })
    if (data.id_number) form.setValue('id_number', data.id_number, { shouldValidate: true })
    if (data.legal_representative) form.setValue('legal_representative', data.legal_representative, { shouldValidate: true })
    if (data.address) form.setValue('address', data.address, { shouldValidate: true })
    if (data.phone) form.setValue('phone', data.phone, { shouldValidate: true })
  }, [form])

  // 文本解析回调
  const handleTextParsed = useCallback((data: Partial<ClientInput>) => {
    if (data.name) form.setValue('name', data.name, { shouldValidate: true })
    if (data.client_type) form.setValue('client_type', data.client_type, { shouldValidate: true })
    if (data.id_number) form.setValue('id_number', data.id_number, { shouldValidate: true })
    if (data.phone) form.setValue('phone', data.phone || '', { shouldValidate: true })
    if (data.address) form.setValue('address', data.address || '', { shouldValidate: true })
    if (data.legal_representative) form.setValue('legal_representative', data.legal_representative || '', { shouldValidate: true })
    if (data.legal_representative_id_number) form.setValue('legal_representative_id_number', data.legal_representative_id_number || '', { shouldValidate: true })
  }, [form])

  // 身份证号验证（自然人输入时自动校验）
  const idCardTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  const idNumber = form.watch('id_number')
  useEffect(() => {
    if (clientType !== 'natural' || !idNumber || idNumber.length !== 18) return
    clearTimeout(idCardTimerRef.current)
    idCardTimerRef.current = setTimeout(async () => {
      try {
        const res = await clientApi.validateIdCard(idNumber)
        if (!res.valid) {
          form.setError('id_number', { message: res.message })
        } else {
          form.clearErrors('id_number')
        }
      } catch { /* ignore network errors */ }
    }, 800)
    return () => clearTimeout(idCardTimerRef.current)
  }, [idNumber, clientType, form])

  const onSubmit = (data: ClientFormData) => {
    const submitData: ClientInput = {
      name: data.name,
      client_type: data.client_type as ClientType,
      id_number: data.id_number || null,
      phone: data.phone || null,
      address: data.address || null,
      legal_representative: data.client_type !== 'natural' ? data.legal_representative || null : null,
      legal_representative_id_number: data.client_type !== 'natural' ? data.legal_representative_id_number || null : null,
      is_our_client: data.is_our_client,
    }

    if (isEditMode && clientId) {
      updateClient.mutate({ id: clientId, data: submitData }, {
        onSuccess: (c) => { toast.success('保存成功'); navigate(generatePath.clientDetail(c.id)) },
        onError: (e) => toast.error(e instanceof Error ? e.message : '保存失败'),
      })
    } else if (pendingDocs.length > 0) {
      // 创建当事人并同时上传证件
      clientApi.createWithDocs(
        submitData,
        pendingDocs.map(d => d.docType),
        pendingDocs.map(d => d.file),
      ).then((c) => {
        toast.success('创建成功')
        navigate(generatePath.clientDetail(c.id))
      }).catch((e) => {
        toast.error(e instanceof Error ? e.message : '创建失败')
      })
    } else {
      createClient.mutate(submitData, {
        onSuccess: (c) => { toast.success('创建成功'); navigate(generatePath.clientDetail(c.id)) },
        onError: (e) => toast.error(e instanceof Error ? e.message : '创建失败'),
      })
    }
  }

  if (isEditMode && isLoadingClient) {
    return <div className="flex items-center justify-center py-12"><Loader2 className="text-muted-foreground size-8 animate-spin" /></div>
  }
  if (isEditMode && clientError) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive mb-4">加载当事人数据失败</p>
        <Button variant="outline" onClick={() => navigate(-1)}>返回</Button>
      </div>
    )
  }

  const isPending = createClient.isPending || updateClient.isPending

  // 表单区域（新建和编辑共用）
  const formContent = (
    <Card>
      <CardHeader><CardTitle className="text-base">{isEditMode ? '编辑当事人信息' : '当事人信息'}</CardTitle></CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid gap-4 lg:grid-cols-2">
              <FormField control={form.control} name="name" render={({ field }) => (
                <FormItem>
                  <FormLabel>姓名 <span className="text-destructive">*</span></FormLabel>
                  <FormControl><Input placeholder="请输入姓名或公司名称" disabled={isPending} className="h-11" {...field} /></FormControl>
                  <FormMessage />
                </FormItem>
              )} />

              <FormField control={form.control} name="client_type" render={({ field }) => (
                <FormItem>
                  <FormLabel>类型 <span className="text-destructive">*</span></FormLabel>
                  <Select onValueChange={field.onChange} value={field.value} disabled={isPending}>
                    <FormControl><SelectTrigger className="h-11 w-full"><SelectValue placeholder="请选择当事人类型" /></SelectTrigger></FormControl>
                    <SelectContent>
                      {Object.entries(CLIENT_TYPE_LABELS).map(([v, l]) => (
                        <SelectItem key={v} value={v} className="min-h-11">{l}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )} />

              <FormField control={form.control} name="id_number" render={({ field }) => (
                <FormItem>
                  <FormLabel>{idNumberLabel}</FormLabel>
                  <FormControl><Input placeholder={`请输入${idNumberLabel}`} disabled={isPending} className="h-11" {...field} /></FormControl>
                  <FormMessage />
                </FormItem>
              )} />

              <FormField control={form.control} name="phone" render={({ field }) => (
                <FormItem>
                  <FormLabel>手机号</FormLabel>
                  <FormControl><Input placeholder="请输入手机号" type="tel" disabled={isPending} className="h-11" {...field} /></FormControl>
                  <FormMessage />
                </FormItem>
              )} />

              <FormField control={form.control} name="address" render={({ field }) => (
                <FormItem className="lg:col-span-2">
                  <FormLabel>地址</FormLabel>
                  <FormControl><Input placeholder="请输入地址" disabled={isPending} className="h-11" {...field} /></FormControl>
                  <FormMessage />
                </FormItem>
              )} />

              {showLegalRep && (
                <FormField control={form.control} name="legal_representative" render={({ field }) => (
                  <FormItem>
                    <FormLabel>{legalRepLabel} <span className="text-destructive">*</span></FormLabel>
                    <FormControl><Input placeholder={`请输入${legalRepLabel}姓名`} disabled={isPending} className="h-11" {...field} /></FormControl>
                    <FormDescription>{clientType === 'non_legal_org' ? '非法人组织必须填写负责人' : '法人必须填写法定代表人'}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )} />
              )}

              {showLegalRep && (
                <FormField control={form.control} name="legal_representative_id_number" render={({ field }) => (
                  <FormItem>
                    <FormLabel>{legalRepLabel}身份证号</FormLabel>
                    <FormControl><Input placeholder={`请输入${legalRepLabel}身份证号`} disabled={isPending} className="h-11" {...field} /></FormControl>
                    <FormMessage />
                  </FormItem>
                )} />
              )}
            </div>

            <div className="flex flex-col-reverse gap-3 md:flex-row md:justify-end">
              <Button type="button" variant="outline" onClick={() => navigate(-1)} disabled={isPending} className="h-11 min-w-[120px]">
                <X className="mr-2 size-4" />取消
              </Button>
              <Button type="submit" disabled={isPending} className="h-11 min-w-[120px]">
                {isPending ? <><Loader2 className="mr-2 size-4 animate-spin" />保存中...</> : <><Save className="mr-2 size-4" />保存</>}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  )

  // 新建模式
  if (!isEditMode) {
    return (
      <div className="space-y-4">
        {/* OA 凭证状态 */}
        {oaCredential?.has_credential && (
          <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-700">
            <CheckCircle2 className="size-4" />
            <span>已配置律所 OA 凭证，可使用 OA 相关功能</span>
          </div>
        )}

        {/* 智能辅助区域 */}
        <EnterpriseSearch onPrefill={handleEnterprisePrefill} />
        <TextParser onParsed={handleTextParsed} />
        {formContent}

        {/* 证件上传（可选，创建时一并上传） */}
        <Card>
          <CardHeader><CardTitle className="text-base">证件上传（可选）</CardTitle></CardHeader>
          <CardContent>
            <p className="text-muted-foreground mb-3 text-sm">可在创建当事人时一并上传证件，节省后续操作。</p>
            <input
              ref={docFileRef}
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) {
                  setPendingDocs(prev => [...prev, { docType: 'id_card', file }])
                }
                e.target.value = ''
              }}
            />
            <Button type="button" variant="outline" size="sm" onClick={() => docFileRef.current?.click()}>
              <Upload className="mr-1.5 size-4" />添加证件
            </Button>
            {pendingDocs.length > 0 && (
              <div className="mt-3 space-y-2">
                {pendingDocs.map((doc, i) => (
                  <div key={i} className="bg-muted/50 flex items-center justify-between rounded px-3 py-2 text-sm">
                    <div className="flex items-center gap-2">
                      <Upload className="size-4" />
                      <span>{doc.file.name}</span>
                      <span className="text-muted-foreground text-xs">({(doc.file.size / 1024).toFixed(0)} KB)</span>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => setPendingDocs(prev => prev.filter((_, j) => j !== i))}>
                      <X className="size-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  // 编辑模式 — Tab 布局
  return (
    <div className="space-y-4">
      <Tabs defaultValue="form" className="w-full">
        <TabsList className="w-full justify-start">
          <TabsTrigger value="form">基本信息</TabsTrigger>
          <TabsTrigger value="clues">财产线索</TabsTrigger>
          <TabsTrigger value="docs">证件管理</TabsTrigger>
        </TabsList>

        <TabsContent value="form" className="mt-4 space-y-4">
          {formContent}
        </TabsContent>

        <TabsContent value="clues" className="mt-4">
          {client && <PropertyClueList clientId={client.id} />}
        </TabsContent>

        <TabsContent value="docs" className="mt-4">
          {client && (
            <IdentityDocManager
              clientId={clientId!}
              clientType={client.client_type}
              docs={client.identity_docs}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default ClientForm
