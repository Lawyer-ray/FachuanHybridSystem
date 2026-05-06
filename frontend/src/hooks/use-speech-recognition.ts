/** Web Speech API 语音识别 Hook */

import { useCallback, useEffect, useRef, useState } from 'react'

const ERROR_MESSAGES: Record<string, string> = {
  'not-allowed': '麦克风权限被拒绝，请在浏览器设置中允许',
  'no-speech': '未检测到语音，请再试一次',
  'audio-capture': '未检测到麦克风设备',
  'network': '语音识别服务不可用',
}

interface UseSpeechRecognitionOptions {
  lang?: string
  continuous?: boolean
  interimResults?: boolean
}

export function useSpeechRecognition(options: UseSpeechRecognitionOptions = {}) {
  const { lang = 'zh-CN', continuous = true, interimResults = true } = options

  const [isListening, setIsListening] = useState(false)
  const [interimTranscript, setInterimTranscript] = useState('')
  const [finalTranscript, setFinalTranscript] = useState('')
  const [error, setError] = useState<string | null>(null)

  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const isStoppingRef = useRef(false)
  const accumulatedRef = useRef('')

  const isSupported =
    typeof window !== 'undefined' &&
    ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)

  // 创建实例（仅一次）
  const getRecognition = useCallback((): SpeechRecognition | null => {
    if (!isSupported) return null
    if (recognitionRef.current) return recognitionRef.current

    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition
    const recognition = new Ctor()
    recognition.lang = lang
    recognition.continuous = continuous
    recognition.interimResults = interimResults

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = ''
      let final = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          final += result[0].transcript
        } else {
          interim += result[0].transcript
        }
      }
      if (final) {
        accumulatedRef.current += final
        setFinalTranscript(accumulatedRef.current)
      }
      setInterimTranscript(interim)
    }

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === 'no-speech' && continuous) return
      const message = ERROR_MESSAGES[event.error] || `语音识别出错: ${event.error}`
      setError(message)
      setIsListening(false)
    }

    recognition.onend = () => {
      if (isStoppingRef.current) {
        isStoppingRef.current = false
        setIsListening(false)
        setInterimTranscript('')
      } else if (continuous) {
        try {
          recognition.start()
        } catch {
          setIsListening(false)
        }
      } else {
        setIsListening(false)
        setInterimTranscript('')
      }
    }

    recognitionRef.current = recognition
    return recognition
  }, [isSupported, lang, continuous, interimResults])

  const start = useCallback(() => {
    const recognition = getRecognition()
    if (!recognition) return
    isStoppingRef.current = false
    setError(null)
    try {
      recognition.start()
      setIsListening(true)
    } catch {
      // already started
    }
  }, [getRecognition])

  const stop = useCallback(() => {
    const recognition = recognitionRef.current
    if (!recognition) return
    isStoppingRef.current = true
    recognition.stop()
  }, [])

  const reset = useCallback(() => {
    accumulatedRef.current = ''
    setFinalTranscript('')
    setInterimTranscript('')
    setError(null)
  }, [])

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort()
    }
  }, [])

  return {
    isSupported,
    isListening,
    interimTranscript,
    finalTranscript,
    error,
    start,
    stop,
    reset,
  }
}
