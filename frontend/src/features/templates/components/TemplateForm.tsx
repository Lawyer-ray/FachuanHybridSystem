import { useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router'
import { Upload, X, FileText, Briefcase, Archive } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { PATHS } from '@/routes/paths'
import type { Template, TemplateType } from '../types'
import {
  TEMPLATE_TYPE_LABELS,
  CONTRACT_SUB_TYPE_LABELS,
  CASE_SUB_TYPE_LABELS,
  ARCHIVE_SUB_TYPE_LABELS,
} from '../types'

const CASE_TYPES: Record<string, string> = {
  civil: '民事', administrative: '行政', criminal: '刑事',
  execution: '申请执行', bankruptcy: '破产', all: '通用',
}

const CASE_STAGES: Record<string, string> = {
  first_trial: '一审', second_trial: '二审', enforcement: '执行',
  labor_arbitration: '劳动仲裁', administrative_review: '行政复议',
  retrial: '再审', all: '通用',
}

const CONTRACT_TYPES: Record<string, string> = {
  civil: '民商事', criminal: '刑事', administrative: '行政',
  labor: '劳动仲裁', intl: '商事仲裁', special: '专项服务',
  advisor: '常法顾问', all: '通用',
}

const LEGAL_STATUSES: Record<string, string> = {
  plaintiff: '原告', defendant: '被告', third_party: '第三人',
  applicant: '申请人', respondent: '被申请人',
}

const MATCH_MODES: Record<string, string> = {
  any: '任意匹配', all: '全部包含', exact: '完全一致',
}

const TYPE_ICONS: Record<TemplateType, React.ElementType> = {
  contract: FileText,
  case: Briefcase,
  archive: Archive,
}

const TYPE_COLORS: Record<TemplateType, string> = {
  contract: 'border-blue-500 bg-blue-50 dark:bg-blue-950',
  case: 'border-purple-500 bg-purple-50 dark:bg-purple-950',
  archive: 'border-yellow-500 bg-yellow-50 dark:bg-yellow-950',
}

function getSubTypes(type: TemplateType): Record<string, string> {
  if (type === 'contract') return CONTRACT_SUB_TYPE_LABELS
  if (type === 'case') return CASE_SUB_TYPE_LABELS
  return ARCHIVE_SUB_TYPE_LABELS
}

interface TemplateFormProps {
  template?: Template
  onSubmit: (data: Partial<Template>) => void
}

export function TemplateForm({ template, onSubmit }: TemplateFormProps) {
  const navigate = useNavigate()
  const isEdit = !!template
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState(template?.name ?? '')
  const [isActive, setIsActive] = useState(template?.is_active ?? true)
  const [templateType, setTemplateType] = useState<TemplateType>(template?.template_type ?? 'contract')
  const [subType, setSubType] = useState(() => {
    if (template?.contract_sub_type) return template.contract_sub_type
    if (template?.case_sub_type) return template.case_sub_type
    if (template?.archive_sub_type) return template.archive_sub_type
    return Object.keys(getSubTypes(template?.template_type ?? 'contract'))[0] ?? ''
  })

  const [caseTypes, setCaseTypes] = useState<string[]>(template?.case_types ?? [])
  const [caseStages, setCaseStages] = useState<string[]>(template?.case_stages ?? [])
  const [contractTypes, setContractTypes] = useState<string[]>(template?.contract_types ?? [])
  const [legalStatuses, setLegalStatuses] = useState<string[]>(template?.legal_statuses ?? [])
  const [matchMode, setMatchMode] = useState(template?.legal_status_match_mode ?? 'any')
  const [institutions, setInstitutions] = useState(template?.applicable_institutions?.join(', ') ?? '')

  const [fileSource, setFileSource] = useState<'upload' | 'path' | 'existing'>(template?.file ? 'upload' : template?.file_path ? 'path' : 'upload')
  const [filePath, setFilePath] = useState(template?.file_path ?? '')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const handleTypeChange = useCallback((type: TemplateType) => {
    setTemplateType(type)
    setSubType(Object.keys(getSubTypes(type))[0] ?? '')
  }, [])

  const toggleArrayItem = useCallback((arr: string[], setArr: (v: string[]) => void, item: string) => {
    setArr(arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item])
  }, [])

  const handleSubmit = useCallback(() => {
    if (!name.trim()) return
    const data: Partial<Template> = {
      name: name.trim(),
      is_active: isActive,
      template_type: templateType,
      contract_sub_type: templateType === 'contract' ? subType : null,
      case_sub_type: templateType === 'case' ? subType : null,
      archive_sub_type: templateType === 'archive' ? subType : null,
      case_types: templateType === 'case' ? caseTypes : [],
      case_stages: templateType === 'case' ? caseStages : [],
      contract_types: templateType === 'contract' ? contractTypes : [],
      legal_statuses: legalStatuses,
      legal_status_match_mode: matchMode,
      applicable_institutions: institutions ? institutions.split(/[,，]/).map((s) => s.trim()).filter(Boolean) : [],
      file_path: fileSource === 'path' ? filePath : '',
    }
    onSubmit(data)
  }, [name, isActive, templateType, subType, caseTypes, caseStages, contractTypes, legalStatuses, matchMode, institutions, fileSource, filePath, onSubmit])

  const subTypes = getSubTypes(templateType)

  return (
    <div className="space-y-4">
      {/* 步骤指示器 */}
      <div className="flex items-center gap-0 px-10">
        {['基本信息', '模板类型', '适用范围', '文件配置'].map((step, i) => (
          <div key={step} className="flex items-center flex-1">
            <div className="flex items-center gap-2">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs ${
                i === 0 ? 'bg-primary text-primary-foreground' : 'bg-muted border border-border text-muted-foreground'
              }`}>
                {i + 1}
              </div>
              <span className="text-[13px]">{step}</span>
            </div>
            {i < 3 && <div className="flex-1 h-px bg-border mx-4" />}
          </div>
        ))}
      </div>

      {/* Card 1: 基本信息 */}
      <Card>
        <CardHeader className="py-3 px-4 border-b border-border">
          <CardTitle className="text-[13px] font-semibold">基本信息</CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-4 space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">
              模板名称 <span className="text-destructive">*</span>
            </Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：民事起诉状（通用）"
            />
          </div>
          <div className="flex items-center gap-3">
            <Switch checked={isActive} onCheckedChange={setIsActive} />
            <span className="text-[13px]">启用（保存后立即可用）</span>
          </div>
        </CardContent>
      </Card>

      {/* Card 2: 模板类型 */}
      <Card>
        <CardHeader className="py-3 px-4 border-b border-border">
          <CardTitle className="text-[13px] font-semibold">
            模板类型 <span className="text-destructive">*</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-4 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            {(Object.keys(TEMPLATE_TYPE_LABELS) as TemplateType[]).map((type) => {
              const Icon = TYPE_ICONS[type]
              const isSelected = templateType === type
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() => handleTypeChange(type)}
                  className={`flex flex-col gap-1 p-4 rounded-md border-2 text-left transition-all ${
                    isSelected ? TYPE_COLORS[type] + ' border-current' : 'border-border hover:border-foreground/20'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Icon className="size-4" />
                    <span className="text-sm font-semibold">{TEMPLATE_TYPE_LABELS[type]}</span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {type === 'contract' ? '合同、补充协议等' : type === 'case' ? '诉状、证据、授权委托等' : '案卷封面、归档登记表等'}
                  </span>
                </button>
              )
            })}
          </div>

          {/* 子类型 */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">
              子类型 <span className="text-destructive">*</span>
            </Label>
            <div className="flex flex-wrap gap-2">
              {Object.entries(subTypes).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSubType(key)}
                  className={`px-3.5 py-2 rounded-md border text-xs transition-all ${
                    subType === key
                      ? 'border-primary bg-primary/5 font-medium'
                      : 'border-border hover:border-foreground/20'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Card 3: 适用范围 */}
      <Card>
        <CardHeader className="py-3 px-4 border-b border-border">
          <CardTitle className="text-[13px] font-semibold">适用范围</CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-4 space-y-4">
          <p className="text-xs text-muted-foreground">
            设定此模板在什么条件下被推荐使用。留空表示通用模板。
          </p>

          {/* 合同类型（仅 contract 类型显示） */}
          {templateType === 'contract' && (
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">合同类型（可多选）</Label>
              <div className="flex flex-wrap gap-2">
                {Object.entries(CONTRACT_TYPES).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleArrayItem(contractTypes, setContractTypes, key)}
                    className={`px-3 py-1.5 rounded-md border text-xs transition-all ${
                      contractTypes.includes(key)
                        ? 'border-primary bg-primary/5 font-medium'
                        : 'border-border hover:border-foreground/20'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 案件类型 + 阶段（仅 case 类型显示） */}
          {templateType === 'case' && (
            <>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">案件类型（可多选）</Label>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(CASE_TYPES).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => toggleArrayItem(caseTypes, setCaseTypes, key)}
                      className={`px-3 py-1.5 rounded-md border text-xs transition-all ${
                        caseTypes.includes(key)
                          ? 'border-primary bg-primary/5 font-medium'
                          : 'border-border hover:border-foreground/20'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">案件阶段（可多选）</Label>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(CASE_STAGES).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => toggleArrayItem(caseStages, setCaseStages, key)}
                      className={`px-3 py-1.5 rounded-md border text-xs transition-all ${
                        caseStages.includes(key)
                          ? 'border-primary bg-primary/5 font-medium'
                          : 'border-border hover:border-foreground/20'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* 诉讼地位 */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">我方诉讼地位（可多选，不选=任意）</Label>
            <div className="flex flex-wrap gap-2">
              {Object.entries(LEGAL_STATUSES).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggleArrayItem(legalStatuses, setLegalStatuses, key)}
                  className={`px-3 py-1.5 rounded-md border text-xs transition-all ${
                    legalStatuses.includes(key)
                      ? 'border-primary bg-primary/5 font-medium'
                      : 'border-border hover:border-foreground/20'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* 匹配模式 */}
          {legalStatuses.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">诉讼地位匹配模式</Label>
              <div className="flex gap-4">
                {Object.entries(MATCH_MODES).map(([key, label]) => (
                  <label key={key} className="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input
                      type="radio"
                      name="match_mode"
                      value={key}
                      checked={matchMode === key}
                      onChange={() => setMatchMode(key)}
                      className="accent-primary"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* 适用机构 */}
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">适用机构（留空=不限）</Label>
            <Input
              value={institutions}
              onChange={(e) => setInstitutions(e.target.value)}
              placeholder="输入法院名称，多个用逗号分隔"
            />
          </div>
        </CardContent>
      </Card>

      {/* Card 4: 文件配置 */}
      <Card>
        <CardHeader className="py-3 px-4 border-b border-border">
          <CardTitle className="text-[13px] font-semibold">
            文件配置 <span className="text-destructive">*</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-4 space-y-3">
          <p className="text-xs text-muted-foreground">
            三选一：从模板库选择已有文件、上传新文件、或手动输入路径。
          </p>

          {/* 从模板库选择 */}
          <div className={`p-3.5 rounded-md border ${fileSource === 'existing' ? 'border-primary bg-primary/5' : 'border-border'}`}>
            <label className="flex items-center gap-2 cursor-pointer mb-2">
              <input
                type="radio"
                name="file_source"
                value="existing"
                checked={fileSource === 'existing'}
                onChange={() => setFileSource('existing')}
                className="accent-primary"
              />
              <span className="text-[13px] font-medium">从模板库选择</span>
              <span className="text-[11px] text-muted-foreground">（不复制文件，直接引用）</span>
            </label>
            <select
              disabled={fileSource !== 'existing'}
              className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm disabled:opacity-50"
            >
              <option value="">-- 请选择模板文件 --</option>
              <option value="case/pleading/民事起诉状通用.docx">case/pleading/民事起诉状通用.docx</option>
              <option value="case/pleading/民事答辩状.docx">case/pleading/民事答辩状.docx</option>
              <option value="contract/民商事合同通用范本.docx">contract/民商事合同通用范本.docx</option>
            </select>
          </div>

          {/* 上传文件 */}
          <div className={`p-3.5 rounded-md border ${fileSource === 'upload' ? 'border-primary bg-primary/5' : 'border-border'}`}>
            <label className="flex items-center gap-2 cursor-pointer mb-2">
              <input
                type="radio"
                name="file_source"
                value="upload"
                checked={fileSource === 'upload'}
                onChange={() => setFileSource('upload')}
                className="accent-primary"
              />
              <span className="text-[13px] font-medium">上传新文件</span>
              <span className="text-[11px] text-muted-foreground">（复制到模板目录）</span>
            </label>
            {fileSource === 'upload' && (
              <>
                <div
                  className="border-2 border-dashed rounded-md p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload className="mx-auto size-8 text-muted-foreground/50 mb-2" />
                  <p className="text-[13px] text-muted-foreground">点击选择或拖拽 .docx 文件到这里</p>
                  <p className="text-[11px] text-muted-foreground/70">支持 .docx 格式，最大 10MB</p>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".docx"
                  className="hidden"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
                />
                {selectedFile && (
                  <div className="mt-2 flex items-center justify-between p-2.5 bg-muted rounded-md text-xs">
                    <span>{selectedFile.name} <span className="text-muted-foreground">({Math.round(selectedFile.size / 1024)} KB)</span></span>
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-destructive" onClick={() => setSelectedFile(null)}>
                      <X className="size-3" />
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>

          {/* 手动输入路径 */}
          <div className={`p-3.5 rounded-md border ${fileSource === 'path' ? 'border-primary bg-primary/5' : 'border-border'}`}>
            <label className="flex items-center gap-2 cursor-pointer mb-2">
              <input
                type="radio"
                name="file_source"
                value="path"
                checked={fileSource === 'path'}
                onChange={() => setFileSource('path')}
                className="accent-primary"
              />
              <span className="text-[13px] font-medium">手动输入路径</span>
              <span className="text-[11px] text-muted-foreground">（相对于模板基础目录）</span>
            </label>
            <Input
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
              placeholder="例：case/pleading/起诉状.docx"
              disabled={fileSource !== 'path'}
            />
          </div>
        </CardContent>
      </Card>

      {/* 底部操作栏 */}
      <div className="flex items-center justify-end gap-2 pt-2">
        <Button variant="outline" onClick={() => navigate(PATHS.ADMIN_TEMPLATES)}>
          取消
        </Button>
        <Button onClick={handleSubmit} disabled={!name.trim()}>
          {isEdit ? '保存修改' : '保存模板'}
        </Button>
      </div>
    </div>
  )
}
