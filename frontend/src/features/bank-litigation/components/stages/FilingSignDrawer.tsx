/**
 * ⑥ 校验 —— 签章详情
 *
 * 抽屉里是**双图对照**：左印章、右签名，各自标绿标红。
 * 缩略图看不清「章盖歪了 2 毫米」「签名是复印的」这类事，所以每张图都能放大成全屏大图。
 */

import { Maximize2, X } from 'lucide-react'

import { DEMO_SIGN_CHECKS } from '../demo-data'
import { useState } from 'react'
import { ActionButton, InsetBlock, KeyValueRow, Pill } from '../ui'
import { cn } from '@/lib/utils'
import { DetailDrawer } from './DetailDrawer'

export function SignDrawer({ name, onClose }: { name: string | null; onClose: () => void }) {
  const d = name ? DEMO_SIGN_CHECKS.find((x) => x.docName === name) : null
  const ok = d ? d.sealOk && d.signOk : false
  /** 放大查看的那一张：seal / sign */
  const [zoom, setZoom] = useState<'seal' | 'sign' | null>(null)

  return (
    <>
      <DetailDrawer
        open={d != null}
        onClose={onClose}
        title={d?.docName ?? ''}
        subtitle={d ? `需盖：${d.needSeal}${d.needSign !== '—' ? ` · 需签：${d.needSign}` : ''}` : undefined}
        badge={d ? <Pill tone={ok ? 'green' : 'red'}>{ok ? '已通过' : '未通过'}</Pill> : null}
        footer={
          d ? (
            <>
              <ActionButton dark onClick={onClose}>
                标记为已核对
              </ActionButton>
              <ActionButton onClick={onClose}>要求重签</ActionButton>
              <ActionButton onClick={onClose}>推送 OA 盖章</ActionButton>
            </>
          ) : null
        }
      >
        {d ? (
          <div className="flex flex-col gap-3">
            <dl>
              <KeyValueRow label="印章识别">
                <span className={d.sealOk ? 'text-status-green' : 'text-status-red'}>
                  {d.sealOk ? '检测到对应印章' : '未检测到印章'}
                </span>
              </KeyValueRow>
              <KeyValueRow label="签名识别">
                <span className={d.signOk ? 'text-status-green' : 'text-status-red'}>
                  {d.signOk ? '检测到签名笔迹' : '签名区域为空'}
                </span>
              </KeyValueRow>
              <KeyValueRow label="核对说明">{d.note}</KeyValueRow>
            </dl>

            <InsetBlock>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">印章与签名区域 · 双图对照</span>
                <span className="ml-auto text-[10px] text-muted-foreground">点图放大</span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <ZoomThumb
                  label={d.sealOk ? '印章 ✓' : '无印章'}
                  ok={d.sealOk}
                  onZoom={() => setZoom('seal')}
                />
                <ZoomThumb
                  label={d.signOk ? '签名 ✓' : '无签名'}
                  ok={d.signOk}
                  onZoom={() => setZoom('sign')}
                />
              </div>
            </InsetBlock>

            {!ok ? (
              <InsetBlock className="border-status-red/40 bg-status-red-bg/50">
                <div className="text-[10.5px] font-medium text-status-red">这份不通过</div>
                <p className="mt-1 text-[10.5px] leading-[1.65] text-muted-foreground">{d.note}</p>
              </InsetBlock>
            ) : null}
          </div>
        ) : null}
      </DetailDrawer>

      <SignZoomOverlay
        open={zoom != null}
        docName={d?.docName ?? ''}
        kind={zoom}
        ok={zoom === 'seal' ? (d?.sealOk ?? false) : (d?.signOk ?? false)}
        onClose={() => setZoom(null)}
      />
    </>
  )
}

/** 缩略图：保持原框样式，右上角挂放大按钮 */
function ZoomThumb({ label, ok, onZoom }: { label: string; ok: boolean; onZoom: () => void }) {
  return (
    <div
      className={cn(
        'group relative grid aspect-[4/3] place-items-center rounded-[4px] border',
        ok ? 'border-status-green/40 bg-status-green-bg/50' : 'border-status-red/40 bg-status-red-bg/50',
      )}
    >
      <span className={cn('text-[10px]', ok ? 'text-status-green' : 'text-status-red')}>{label}</span>
      <button
        type="button"
        aria-label={`放大查看${label}`}
        onClick={onZoom}
        className="absolute top-1 right-1 grid size-5 place-items-center rounded-[5px] border border-border-light bg-card/90 text-muted-foreground transition-colors hover:text-foreground"
      >
        <Maximize2 className="size-2.5" />
      </button>
    </div>
  )
}

/** 全屏大图：占满视口，ESC 或点遮罩关闭 */
function SignZoomOverlay({
  open,
  docName,
  kind,
  ok,
  onClose,
}: {
  open: boolean
  docName: string
  kind: 'seal' | 'sign' | null
  ok: boolean
  onClose: () => void
}) {
  if (!open) return null
  const title = kind === 'seal' ? '印章区域 · 放大查看' : '签名区域 · 放大查看'

  return (
    <div className="fixed inset-0 z-[90] flex flex-col bg-foreground/70 p-6 backdrop-blur-[2px]" onClick={onClose}>
      <div className="flex flex-none items-center gap-2 text-background" onClick={(e) => e.stopPropagation()}>
        <span className="text-[12.5px] font-medium">{title}</span>
        <span className="text-[11px] opacity-70">{docName} · 300 dpi 扫描件</span>
        <button
          type="button"
          aria-label="关闭大图"
          onClick={onClose}
          className="ml-auto grid size-6 place-items-center rounded-[6px] bg-background/15 text-background transition-colors hover:bg-background/25"
        >
          <X className="size-3.5" />
        </button>
      </div>

      <div
        className="mt-3 grid min-h-0 flex-1 place-items-center rounded-[12px] border border-background/20 bg-card p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className={cn(
            'grid h-full w-full max-w-[720px] place-items-center rounded-[8px] border-2 border-dashed',
            ok ? 'border-status-green/50 bg-status-green-bg/40' : 'border-status-red/50 bg-status-red-bg/40',
          )}
        >
          <div className="text-center">
            <div className={cn('text-[18px] font-semibold', ok ? 'text-status-green' : 'text-status-red')}>
              {ok ? (kind === 'seal' ? '印章 ✓' : '签名 ✓') : kind === 'seal' ? '无印章' : '无签名'}
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {kind === 'seal' ? '公章 · 骑缝盖在第 1-4 页右侧' : '委托人签名区（第 2 页底部）'}
            </p>
            <p className="mt-3 max-w-[360px] text-[10.5px] leading-[1.65] text-muted-foreground">
              {ok
                ? '放大后仍是清晰图像，未发现复印痕迹或裁切边。'
                : '放大后确认该区域为空白 —— 这一份不能送法院，需重新签署后扫描上传。'}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
