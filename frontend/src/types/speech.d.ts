/* eslint-disable no-var */
/** Web Speech API 类型声明（TypeScript DOM lib 未包含） */

interface SpeechRecognitionEventMap {
  audioend: Event
  audiostart: Event
  end: Event
  error: SpeechRecognitionErrorEvent
  nomatch: SpeechRecognitionEvent
  result: SpeechRecognitionEvent
  soundend: Event
  soundstart: Event
  speechend: Event
  speechstart: Event
  start: Event
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean
  grammars: SpeechGrammarList
  interimResults: boolean
  lang: string
  maxAlternatives: number
  onaudioend: ((this: SpeechRecognition, ev: Event) => void) | null
  onaudiostart: ((this: SpeechRecognition, ev: Event) => void) | null
  onend: ((this: SpeechRecognition, ev: Event) => void) | null
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null
  onnomatch: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null
  onsoundend: ((this: SpeechRecognition, ev: Event) => void) | null
  onsoundstart: ((this: SpeechRecognition, ev: Event) => void) | null
  onspeechend: ((this: SpeechRecognition, ev: Event) => void) | null
  onspeechstart: ((this: SpeechRecognition, ev: Event) => void) | null
  onstart: ((this: SpeechRecognition, ev: Event) => void) | null
  abort(): void
  start(): void
  stop(): void
  addEventListener<K extends keyof SpeechRecognitionEventMap>(
    type: K,
    listener: (this: SpeechRecognition, ev: SpeechRecognitionEventMap[K]) => void,
  ): void
  removeEventListener<K extends keyof SpeechRecognitionEventMap>(
    type: K,
    listener: (this: SpeechRecognition, ev: SpeechRecognitionEventMap[K]) => void,
  ): void
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognition
  prototype: SpeechRecognition
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string
  readonly message: string
}

interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number
  readonly results: SpeechRecognitionResultList
}

declare var SpeechRecognition: SpeechRecognitionConstructor
declare var webkitSpeechRecognition: SpeechRecognitionConstructor
