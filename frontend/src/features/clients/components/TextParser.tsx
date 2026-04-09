/**
 * TextParser - 智能解析组件（文本粘贴 + 图片上传/粘贴）
 */

import { useState, useCallback, useRef } from 'react'
import {
  FileText, Loader2, CheckCircle2, Wand2, Image, X,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

import { clientApi } from '../api'
import type { ClientInput } from '../types'

interface Props {
  onParsed: (data: Partial<ClientInput>) => void
}

const FIELD_LABELS: Record<string, string> = {
  name: '姓名/公司名称',
  id_number: '身份证号/统一社会信用代码',
  phone: '联系方式',
  address: '地址',
  legal_representative: '法定代表人',
  client_type: '当事人类型',
}

const expandAnim = {
  initial: { height: 0, opacity: 0 },
  animate: { height: 'auto', opacity: 1, transition: { height: { duration: 0.25 }, opacity: { duration: 0.2, delay: 0.05 } } },
  exit: { height: 0, opacity: 0, transition: { opacity: { duration: 0.15 }, height: { duration: 0.2, delay: 0.05 } } },
}

export function TextParser({ onParsed }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [text, setText] = useState('')
  const [isParsing, setIsParsing] = useState(false)
  const [isRecognizing, setIsRecognizing] = useState(false)
  const [result, setResult] = useState<Record<string, string> | null>(null)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleParseText = useCallback(async () => {
    const t = text.trim()
    if (!t) { toast.error('请输入文本内容'); return }
    setIsParsing(true)
    setResult(null)
    try {
      const res = await clientApi.parseText(t)
      if (res.success && res.client) {
        setResult(res.client)
      } else {
        toast.error(res.error || '未能解析出有效信息')
      }
    } catch {
      toast.error('解析失败，请重试')
    } finally {
      setIsParsing(false)
    }
  }, [text])

  const handleRecognizeImage = useCallback(async (file: File) => {
    setIsRecognizing(true)
    setResult(null)
    try {
      const res = await clientApi.recognizeIdentityDoc(file)
      if (res.success && res.extracted_data) {
        const r: Record<string, string> = {}
        if (res.extracted_data.name) r.name = res.extracted_data.name
        if (res.extracted_data.id_number) r.id_number = res.extracted_data.id_number
        if (res.extracted_data.address) r.address = res.extracted_data.address
        if (res.extracted_data.legal_representative) r.legal_representative = res.extracted_data.legal_representative
        setResult(r)
        toast.success('识别成功，请确认结果')
      } else {
        toast.error(res.error || '识别失败，请重试')
      }
    } catch {
      toast.error('识别失败，请检查网络')
    } finally {
      setIsRecognizing(false)
    }
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImageFile(file)
    setImagePreview(URL.createObjectURL(file))
    handleRecognizeImage(file)
    e.target.value = ''
  }, [handleRecognizeImage])

  const clearImage = useCallback(() => {
    setImageFile(null)
    if (imagePreview) URL.revokeObjectURL(imagePreview)
    setImagePreview(null)
  }, [imagePreview])

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault()
        const file = item.getAsFile()
        if (file) {
          setImageFile(file)
          setImagePreview(URL.createObjectURL(file))
          handleRecognizeImage(file)
        }
        return
      }
    }
  }, [handleRecognizeImage])

  const handleApply = useCallback(() => {
    if (!result) return
    const data: Partial<ClientInput> = {}
    if (result.name) data.name = result.name
    if (result.id_number) data.id_number = result.id_number
    if (result.phone) data.phone = result.phone
    if (result.address) data.address = result.address
    if (result.legal_representative) data.legal_representative = result.legal_representative
    if (result.client_type) data.client_type = result.client_type as ClientInput['client_type']
    onParsed(data)
    toast.success('已填充到表单')
    setResult(null)
  }, [result, onParsed])

  const isLoading = isParsing || isRecognizing

  return (
    <div className="group relative overflow-hidden rounded-xl border border-slate-200/60 bg-gradient-to-br from-slate-50/80 via-white to-indigo-50/30 shadow-sm transition-shadow hover:shadow-md dark:border-slate-700/40 dark:from-slate-950/30 dark:via-gray-950 dark:to-indigo-950/20">
      {/* 顶部装饰线 */}
      <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-slate-400 via-indigo-400 to-slate-500" />

      {/* Header */}
      <button
        type="button"
        className="flex w-full items-center justify-between px-5 py-3.5"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div className="flex size-8 items-center justify-center rounded-lg bg-gradient-to-br from-slate-600 to-indigo-600 shadow-sm">
            <Wand2 className="size-4 text-white" />
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">智能解析</span>
              <Badge variant="secondary" className="border-slate-200/60 bg-slate-100/60 text-[11px] text-slate-700 dark:border-slate-700/40 dark:bg-slate-800/40 dark:text-slate-300">
                文本 / 图片
              </Badge>
            </div>
            <p className="text-muted-foreground mt-0.5 text-xs">粘贴文本或上传证件图片，AI 自动提取信息</p>
          </div>
        </div>
        <motion.div
          animate={{ rotate: expanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="text-muted-foreground"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </motion.div>
      </button>

      {/* Content */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div {...expandAnim} className="overflow-hidden">
            <div className="space-y-4 px-5 pb-5">
              {/* 文本输入区 */}
              <div className="space-y-2">
                <div className="rounded-lg border border-slate-200/60 bg-white/80 p-0.5 transition-colors focus-within:border-indigo-400 dark:border-slate-700/40 dark:bg-gray-900/60">
                  <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onPaste={handlePaste}
                    rows={4}
                    disabled={isLoading}
                    className="w-full resize-none rounded-md bg-transparent px-3 py-2.5 font-mono text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
                    placeholder="粘贴当事人信息文本，或直接粘贴/拖入身份证、营业执照图片..."
                  />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-muted-foreground text-xs">
                    支持粘贴文本自动提取，或粘贴 / 上传证件图片 OCR 识别
                  </p>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => fileRef.current?.click()}
                      disabled={isLoading}
                      className="h-8 border-slate-200/60 dark:border-slate-700/40"
                    >
                      <Image className="mr-1.5 size-3.5" />上传图片
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleParseText}
                      disabled={isLoading || !text.trim()}
                      className="h-8 bg-gradient-to-r from-slate-600 to-indigo-600 text-white shadow-sm hover:from-slate-700 hover:to-indigo-700"
                    >
                      {isParsing ? <Loader2 className="mr-1.5 size-3.5 animate-spin" /> : <FileText className="mr-1.5 size-3.5" />}
                      解析文本
                    </Button>
                  </div>
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".jpg,.jpeg,.png,.pdf"
                  className="hidden"
                  onChange={handleFileSelect}
                />
              </div>

              {/* 图片预览 */}
              <AnimatePresence>
                {imageFile && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    className="flex items-center gap-3 rounded-lg border border-slate-200/60 bg-white/70 p-3 dark:border-slate-700/40 dark:bg-gray-900/50"
                  >
                    {imagePreview && (
                      <img src={imagePreview} alt="预览" className="size-14 rounded-lg object-cover shadow-sm" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{imageFile.name}</p>
                      <p className="text-muted-foreground text-xs">{(imageFile.size / 1024).toFixed(0)} KB</p>
                    </div>
                    {isRecognizing ? (
                      <Loader2 className="size-5 animate-spin text-indigo-500" />
                    ) : (
                      <Button variant="ghost" size="icon" className="size-8" onClick={clearImage}>
                        <X className="size-4" />
                      </Button>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* 解析/识别结果 */}
              <AnimatePresence>
                {result && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="space-y-3 rounded-xl border border-green-200/60 bg-white/90 p-5 shadow-sm dark:border-green-900/40 dark:bg-gray-900/70"
                  >
                    <div className="flex items-center gap-2">
                      <div className="flex size-6 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/40">
                        <CheckCircle2 className="size-3.5 text-green-600 dark:text-green-400" />
                      </div>
                      <span className="text-sm font-semibold">解析成功</span>
                    </div>
                    <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                      {Object.entries(result).filter(([, v]) => v).map(([key, value]) => (
                        <div key={key} className="flex items-baseline gap-2 text-sm">
                          <span className="text-muted-foreground shrink-0 text-xs">{FIELD_LABELS[key] || key}</span>
                          <span className="font-medium">{value}</span>
                        </div>
                      ))}
                    </div>
                    <div className="flex justify-end gap-2 border-t pt-4">
                      <Button variant="outline" size="sm" onClick={() => setResult(null)}>取消</Button>
                      <Button size="sm" className="bg-gradient-to-r from-slate-600 to-indigo-600 text-white shadow-sm hover:from-slate-700 hover:to-indigo-700" onClick={handleApply}>
                        <CheckCircle2 className="mr-1.5 size-3.5" />确认填充
                      </Button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
