/**
 * PropertyClueFormDialog - 财产线索新建/编辑对话框
 */

import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Paperclip, X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import {
  Form, FormField, FormItem, FormLabel, FormControl, FormMessage,
} from '@/components/ui/form'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

import { clientApi } from '../api'
import { usePropertyClueMutations } from '../hooks/use-property-clue-mutations'
import type { ClueType, PropertyClue } from '../types'
import { CLUE_TYPE_LABELS } from '../types'

const schema = z.object({
  clue_type: z.string().min(1, '请选择线索类型'),
  content: z.string().optional(),
})

type FormData = z.infer<typeof schema>

interface Props {
  clientId: number
  clue?: PropertyClue | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function PropertyClueFormDialog({ clientId, clue, open, onOpenChange }: Props) {
  const isEdit = !!clue
  const { createClue, updateClue, uploadAttachment } = usePropertyClueMutations(clientId)
  const [files, setFiles] = useState<File[]>([])

  const form = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { clue_type: 'bank', content: '' },
  })

  const clueType = form.watch('clue_type')

  // 编辑模式预填
  useEffect(() => {
    if (clue) {
      form.reset({ clue_type: clue.clue_type, content: clue.content })
    } else {
      form.reset({ clue_type: 'bank', content: '' })
      setFiles([])
    }
  }, [clue, form, open])

  // 新建时切换类型自动加载模板
  useEffect(() => {
    if (!isEdit && clueType && open) {
      clientApi.getContentTemplate(clueType).then((res) => {
        if (res.template && !form.getValues('content')) {
          form.setValue('content', res.template)
        }
      }).catch(() => {})
    }
  }, [clueType, isEdit, form, open])

  const isPending = createClue.isPending || updateClue.isPending

  const onSubmit = async (data: FormData) => {
    try {
      if (isEdit && clue) {
        await updateClue.mutateAsync({ clueId: clue.id, data: { clue_type: data.clue_type as ClueType, content: data.content } })
        toast.success('线索已更新')
      } else {
        const newClue = await createClue.mutateAsync({ clue_type: data.clue_type as ClueType, content: data.content })
        // 上传附件
        for (const file of files) {
          await uploadAttachment.mutateAsync({ clueId: newClue.id, file })
        }
        toast.success('线索已创建')
      }
      setFiles([])
      onOpenChange(false)
    } catch {
      toast.error('操作失败')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑财产线索' : '新建财产线索'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="clue_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>线索类型</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value} disabled={isPending}>
                    <FormControl>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {Object.entries(CLUE_TYPE_LABELS).map(([v, l]) => (
                        <SelectItem key={v} value={v}>{l}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="content"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>线索内容</FormLabel>
                  <FormControl>
                    <textarea
                      {...field}
                      rows={5}
                      disabled={isPending}
                      className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                      placeholder="请输入线索内容"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 新建时可添加附件 */}
            {!isEdit && (
              <div className="space-y-2">
                <FormLabel>附件</FormLabel>
                <div className="flex flex-wrap gap-2">
                  {files.map((f, i) => (
                    <span key={i} className="bg-muted inline-flex items-center gap-1 rounded px-2 py-1 text-xs">
                      <Paperclip className="size-3" />{f.name}
                      <button type="button" onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                </div>
                <Input
                  type="file"
                  multiple
                  onChange={(e) => {
                    if (e.target.files) setFiles([...files, ...Array.from(e.target.files)])
                    e.target.value = ''
                  }}
                  disabled={isPending}
                />
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
                取消
              </Button>
              <Button type="submit" disabled={isPending}>
                {isPending && <Loader2 className="mr-2 size-4 animate-spin" />}
                {isEdit ? '保存' : '创建'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
