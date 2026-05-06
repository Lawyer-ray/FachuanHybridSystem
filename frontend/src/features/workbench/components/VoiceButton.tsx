/** 语音输入按钮 */

import { Mic, MicOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface VoiceButtonProps {
  isSupported: boolean
  isListening: boolean
  onStart: () => void
  onStop: () => void
  disabled?: boolean
}

export function VoiceButton({
  isSupported,
  isListening,
  onStart,
  onStop,
  disabled,
}: VoiceButtonProps) {
  if (!isSupported) return null

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            'relative inline-flex',
            isListening &&
              'after:absolute after:inset-0 after:rounded-md after:ring-2 after:ring-destructive/60 after:animate-pulse after:pointer-events-none',
          )}
        >
          <Button
            type="button"
            size="icon"
            variant={isListening ? 'destructive' : 'ghost'}
            onClick={isListening ? onStop : onStart}
            disabled={disabled}
            className="shrink-0"
          >
            {isListening ? <MicOff className="size-4" /> : <Mic className="size-4" />}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent side="top">
        {isListening ? '停止录音' : '语音输入'}
      </TooltipContent>
    </Tooltip>
  )
}
