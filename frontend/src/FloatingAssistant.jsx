import { useEffect, useState } from 'react'
import { useVoiceChat } from './useVoiceChat'
import { MicIcon, SendIcon, StopIcon } from './utils'

// Quick-action starters for the 3 buttons the spec calls out. These get
// SENT immediately (like the main chat's QUICK_ACTIONS), except "What
// should I enter here?" which — per the system prompt — the assistant will
// respond to by asking which field, since it genuinely cannot see the
// citizen's screen (privacy-by-design, not a missing feature).
const QUICK_ACTIONS = [
  { key: 'field', label: 'What should I enter here?', starter: 'What should I enter here?' },
  { key: 'stuck', label: "I'm stuck", starter: "I'm stuck, can you help me?" },
  { key: 'next', label: 'What do I do next?', starter: 'What do I do next?' },
]

// A separate, self-contained conversation from the main chat — this is a
// quick-help companion, not meant to replace or merge with the main SEVA AI
// chat thread. It still goes through the exact same backend endpoints
// (/api/chat/text, /api/chat/voice), which means the exact same Phase 1
// hybrid RAG + Phase 2 process guidance + Phase 2 official links + Phase 3
// Part 2 language-switch handling — never a separate/bypassed chatbot.
//
// `openSignal`: bump this (e.g. a counter) from the parent to force the
// panel open — used when the user clicks "Open Official Portal" so the
// companion is right there when they switch back from the government site
// (Phase 3 Part 2 requirement: "provide a floating companion when the
// official portal is opened").
export default function FloatingAssistant({ lang, onLanguageChange, openSignal }) {
  const [isOpen, setIsOpen] = useState(false)
  const [inputText, setInputText] = useState('')
  const voice = useVoiceChat({ lang, onLanguageChange })

  useEffect(() => {
    if (openSignal) setIsOpen(true)
  }, [openSignal])

  function handleSend() {
    voice.sendText(inputText)
    setInputText('')
  }

  const statusLabel =
    voice.status === 'listening' ? 'Listening…' :
    voice.status === 'thinking' ? 'SEVA is thinking…' :
    voice.status === 'speaking' ? 'SEVA is speaking…' :
    'Tap to speak'

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        aria-label="Open Seva AI assistant"
        className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full bg-linear-to-br from-orange-400 to-green-500 text-white shadow-lg px-5 py-3.5 hover:brightness-105 transition-all"
      >
        <span className="text-xl leading-none">🤖</span>
        <span className="font-semibold text-sm">Seva AI</span>
      </button>
    )
  }

  return (
    <div
      className="fixed bottom-6 right-6 z-50 w-[min(92vw,380px)] max-h-[80vh] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden"
      role="dialog"
      aria-label="Seva AI floating assistant"
    >
      {/* Header — large, clear close button per accessibility requirement */}
      <div className="flex items-center justify-between px-4 py-3 bg-linear-to-br from-orange-400 to-green-500 text-white shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xl leading-none">🤖</span>
          <span className="font-bold text-base">Seva AI</span>
        </div>
        <button
          onClick={() => setIsOpen(false)}
          aria-label="Close Seva AI assistant"
          className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-white/20 text-2xl leading-none"
        >
          ×
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3 min-h-[120px]">
        {voice.messages.length === 0 && (
          <p className="text-base text-gray-700 font-medium">How can I help you?</p>
        )}
        {voice.messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-base leading-snug whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-green-600 text-white'
                  : msg.isError
                    ? 'bg-red-50 text-red-700 border border-red-100'
                    : 'bg-gray-100 text-gray-800'
              }`}
            >
              {msg.text}
              {msg.citations?.length > 0 && (
                <details className="mt-2 text-xs opacity-80">
                  <summary className="cursor-pointer">📚 Sources</summary>
                  <ul className="list-disc pl-4 mt-1">
                    {msg.citations.map((c, ci) => (
                      <li key={ci}>{c}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Voice status — always visible, plain wording, per accessibility requirement */}
      <div className="px-4 pb-1 shrink-0 flex items-center gap-2" aria-live="polite">
        <span
          className={`w-2 h-2 rounded-full ${
            voice.status === 'listening' ? 'bg-red-500 animate-pulse'
              : voice.status === 'speaking' ? 'bg-green-500 animate-pulse'
              : voice.status === 'thinking' ? 'bg-amber-400'
              : 'bg-gray-300'
          }`}
        />
        <span className="text-sm text-gray-500">{statusLabel}</span>
        {voice.status === 'speaking' && (
          <button
            onClick={voice.stopSpeaking}
            aria-label="Stop Seva AI speaking"
            className="ml-auto flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-full bg-red-50 text-red-600 hover:bg-red-100"
          >
            <StopIcon size={14} /> STOP
          </button>
        )}
      </div>

      {/* Quick actions — large, simple buttons for low-literacy/elderly users */}
      <div className="px-4 pb-2 flex flex-col gap-2 shrink-0">
        {QUICK_ACTIONS.map((qa) => (
          <button
            key={qa.key}
            onClick={() => voice.sendText(qa.starter)}
            disabled={voice.isSending}
            className="text-left text-base px-4 py-2.5 rounded-xl border border-gray-200 text-gray-700 hover:bg-green-50 hover:border-green-300 disabled:opacity-40 transition-colors font-medium"
          >
            {qa.label}
          </button>
        ))}
      </div>

      {/* Input row */}
      <div className="px-4 pb-3 flex items-center gap-2 shrink-0">
        <button
          onClick={voice.toggleRecording}
          aria-label={voice.isRecording ? 'Stop recording' : 'Ask a question by voice'}
          title={voice.isRecording ? 'Stop recording' : 'Tap to speak'}
          className={`w-11 h-11 rounded-full flex items-center justify-center shrink-0 transition-colors ${
            voice.isRecording ? 'bg-red-500 animate-pulse' : 'bg-green-600 hover:bg-green-700'
          }`}
        >
          <MicIcon recording={voice.isRecording} size={22} />
        </button>
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Ask a question..."
          disabled={voice.isRecording}
          aria-label="Type your question"
          className="flex-1 rounded-full border border-gray-200 bg-gray-50 px-4 py-2.5 text-base outline-none focus:border-green-400"
        />
        <button
          onClick={handleSend}
          disabled={voice.isSending || !inputText.trim()}
          aria-label="Send question"
          title="Send"
          className="w-11 h-11 rounded-full bg-green-600 hover:bg-green-700 disabled:opacity-40 flex items-center justify-center shrink-0"
        >
          <SendIcon size={20} />
        </button>
      </div>

      {/* Privacy note — always visible, not tucked away, per Phase 3 privacy requirement */}
      <div className="px-4 py-2.5 bg-gray-50 border-t border-gray-100 shrink-0">
        <p className="text-xs text-gray-500 leading-snug">
          🔒 Seva AI provides guidance only. Your information stays under your control — nothing is read
          from your screen automatically, and no forms are filled or submitted for you.
        </p>
      </div>
    </div>
  )
}
