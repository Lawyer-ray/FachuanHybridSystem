import { useState, useCallback, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Upload, FileText, X, Download, Loader2, Check, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { api } from '@/lib/api'
import { HTTPError } from 'ky'

interface MbidItem {
  mbid: string
  name: string
}

interface MbidCategory {
  category: string
  items: MbidItem[]
}

function StepDot({ num, label, active, done }: { num: number; label: string; active: boolean; done: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <div
        className={`size-8 rounded-full flex items-center justify-center text-xs font-semibold transition-all duration-300 ${
          done
            ? 'bg-foreground text-primary-foreground scale-100'
            : active
              ? 'bg-foreground text-primary-foreground ring-4 ring-foreground/10 scale-105'
              : 'bg-muted text-muted-foreground border border-border'
        }`}
      >
        {done ? <Check className="size-3.5" /> : num}
      </div>
      <span className={`text-sm font-medium transition-colors ${active || done ? 'text-foreground' : 'text-muted-foreground'}`}>
        {label}
      </span>
    </div>
  )
}

export function ElementConvertTool() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedMbid, setSelectedMbid] = useState<string>('')
  const [isConverting, setIsConverting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: mbidData, isLoading: isLoadingMbid } = useQuery({
    queryKey: ['doc-convert-mbid-list'],
    queryFn: () => api.get('doc-convert/mbid-list').json<{ categories: MbidCategory[] }>(),
    staleTime: 5 * 60_000,
  })

  const categories: MbidCategory[] = mbidData?.categories ?? []

  // Auto-select MBID when filename matches an option name
  useEffect(() => {
    if (!selectedFile || categories.length === 0) return
    const fileName = selectedFile.name.replace(/\.[^.]+$/, '') // strip extension
    for (const cat of categories) {
      for (const item of cat.items) {
        if (fileName.includes(item.name)) {
          setSelectedMbid(item.mbid)
          return
        }
      }
    }
  }, [selectedFile, categories])

  const step1Done = !!selectedFile
  const step2Done = !!selectedFile && !!selectedMbid
  const currentStep = step2Done ? 3 : step1Done ? 2 : 1

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const ext = file.name.toLowerCase().split('.').pop()
    if (!ext || !['docx', 'doc', 'pdf'].includes(ext)) {
      toast.error('仅支持 .docx、.doc、.pdf 格式')
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      toast.error('文件大小不能超过 20MB')
      return
    }
    setSelectedFile(file)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (!file) return
    const ext = file.name.toLowerCase().split('.').pop()
    if (!ext || !['docx', 'doc', 'pdf'].includes(ext)) {
      toast.error('仅支持 .docx、.doc、.pdf 格式')
      return
    }
    setSelectedFile(file)
  }, [])

  const handleConvert = useCallback(async () => {
    if (!selectedFile || !selectedMbid) return
    setIsConverting(true)
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('mbid', selectedMbid)

      const res = await api.post('doc-convert/convert', { body: formData, timeout: 120_000 })
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      // 生成文件名：将"传统"替换为"要素式"，否则在文件名前加"要素式"
      const baseName = selectedFile.name.replace(/\.[^.]+$/, '')
      const newName = baseName.replace('传统', '要素式')
      a.download = (newName === baseName ? '要素式' + baseName : newName) + '.docx'
      a.click()
      URL.revokeObjectURL(url)
      toast.success('转换完成，文件已下载')
    } catch (err) {
      if (err instanceof HTTPError) {
        const status = err.response.status
        try {
          const body = await err.response.json() as { detail?: string }
          if (status === 502) {
            toast.error(body.detail || '远端转换服务暂时不可用，请稍后重试')
          } else {
            toast.error(body.detail || `请求失败 (${status})`)
          }
        } catch {
          toast.error(status === 502
            ? '远端转换服务暂时不可用，请稍后重试'
            : `请求失败 (${status})`)
        }
      } else {
        toast.error(err instanceof Error ? err.message : '转换失败')
      }
    } finally {
      setIsConverting(false)
    }
  }, [selectedFile, selectedMbid])

  const selectedMbidName = categories
    .flatMap((c) => c.items)
    .find((i) => i.mbid === selectedMbid)?.name

  return (
    <div className="max-w-3xl mx-auto space-y-0">
      {/* Header */}
      <div className="text-center pb-6">
        <div className="inline-flex items-center gap-1.5 text-xs text-muted-foreground bg-muted px-3 py-1 rounded-full mb-3">
          <Sparkles className="size-3" />
          智能文书转换
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">要素式转换</h1>
        <p className="text-muted-foreground text-sm mt-1.5 max-w-md mx-auto">
          上传传统格式文书，系统自动识别并转换为要素式标准格式
        </p>
      </div>

      {/* Step progress */}
      <div className="flex items-center justify-center gap-6 py-5">
        <StepDot num={1} label="上传文书" active={currentStep === 1} done={step1Done} />
        <div className={`w-12 h-px transition-colors ${step1Done ? 'bg-foreground' : 'bg-border'}`} />
        <StepDot num={2} label="选择格式" active={currentStep === 2} done={step2Done} />
        <div className={`w-12 h-px transition-colors ${step2Done ? 'bg-foreground' : 'bg-border'}`} />
        <StepDot num={3} label="转换下载" active={currentStep === 3} done={false} />
      </div>

      {/* Step 1: Upload */}
      <div className="pt-2">
        <div className="text-xs font-medium text-muted-foreground mb-2.5 pl-1">第一步</div>
        <div
          className={`relative border-2 border-dashed rounded-xl px-5 py-5 flex items-center gap-4 cursor-pointer transition-all duration-200 ${
            selectedFile
              ? 'border-foreground/20 bg-muted/40'
              : 'border-border hover:border-foreground/30 hover:bg-muted/20'
          }`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
        >
          {selectedFile ? (
            <>
              <div className="size-11 rounded-lg bg-background border border-border flex items-center justify-center shrink-0 shadow-sm">
                <FileText className="size-5 text-foreground" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate">{selectedFile.name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {(selectedFile.size / 1024).toFixed(0)} KB · 点击更换文件
                </p>
              </div>
              <div className="flex items-center gap-2">
                <div className="size-6 rounded-full bg-foreground/5 flex items-center justify-center">
                  <Check className="size-3 text-foreground" />
                </div>
                <div
                  className="size-6 rounded-full hover:bg-muted flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
                  onClick={(e) => {
                    e.stopPropagation()
                    setSelectedFile(null)
                    setSelectedMbid('')
                    if (fileInputRef.current) fileInputRef.current.value = ''
                  }}
                >
                  <X className="size-3.5" />
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="size-11 rounded-lg bg-muted border border-border flex items-center justify-center shrink-0">
                <Upload className="size-5 text-muted-foreground" />
              </div>
              <div>
                <p className="text-sm font-medium">点击选择或拖拽文件到此处</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  支持 .docx、.doc、.pdf 格式，最大 20MB
                </p>
              </div>
            </>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".docx,.doc,.pdf"
          className="hidden"
          onChange={handleFileSelect}
        />
      </div>

      {/* Step 2: Format selection */}
      <div className={`pt-6 transition-opacity duration-300 ${step1Done ? 'opacity-100' : 'opacity-40 pointer-events-none'}`}>
        <div className="text-xs font-medium text-muted-foreground mb-2.5 pl-1">第二步</div>
        <Card className="border-border/80">
          <CardContent className="p-4 space-y-4 max-h-[400px] overflow-y-auto">
            {isLoadingMbid ? (
              <div className="flex items-center justify-center py-10 text-muted-foreground text-sm">
                <Loader2 className="mr-2 size-4 animate-spin" />
                加载格式列表...
              </div>
            ) : (
              categories.map((cat) => (
                <div key={cat.category}>
                  <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-2">
                    {cat.category}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {cat.items.map((item) => (
                      <button
                        key={item.mbid}
                        type="button"
                        onClick={() => setSelectedMbid(item.mbid)}
                        className={`px-3 py-1.5 rounded-lg text-xs transition-all duration-150 ${
                          selectedMbid === item.mbid
                            ? 'bg-foreground text-primary-foreground font-medium shadow-md shadow-foreground/20'
                            : 'bg-muted border border-border hover:border-foreground/20 hover:bg-muted/80'
                        }`}
                      >
                        {item.name}
                      </button>
                    ))}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Step 3: Convert action */}
      <div className={`pt-6 transition-opacity duration-300 ${step2Done ? 'opacity-100' : 'opacity-40 pointer-events-none'}`}>
        <div className="text-xs font-medium text-muted-foreground mb-2.5 pl-1">第三步</div>
        <Card className="border-border/80">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3 min-w-0">
                <div className="size-9 rounded-lg bg-muted border border-border flex items-center justify-center shrink-0">
                  <FileText className="size-4" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{selectedFile?.name}</p>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-0.5">
                    <span>转换为</span>
                    <span className="font-medium text-foreground">{selectedMbidName}</span>
                  </div>
                </div>
              </div>
              <Button
                onClick={handleConvert}
                disabled={isConverting}
                className="min-w-[130px] shadow-lg shadow-foreground/10"
              >
                {isConverting ? (
                  <>
                    <Loader2 className="mr-1.5 size-4 animate-spin" />
                    转换中...
                  </>
                ) : (
                  <>
                    <Download className="mr-1.5 size-4" />
                    转换并下载
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
