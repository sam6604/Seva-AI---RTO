import { useRef, useState } from 'react'

const NAV_ITEMS = [{ key: 'home', label: 'Home', icon: '🚗' }]

// Order deliberately avoids putting English/Hindi first — the picker
// shouldn't nudge users toward either as a "default".
const LANGUAGES = [
  { code: 'ta-IN', label: 'தமிழ்' },
  { code: 'te-IN', label: 'తెలుగు' },
  { code: 'kn-IN', label: 'ಕನ್ನಡ' },
  { code: 'ml-IN', label: 'മലയാളം' },
  { code: 'mr-IN', label: 'मराठी' },
  { code: 'gu-IN', label: 'ગુજરાતી' },
  { code: 'bn-IN', label: 'বাংলা' },
  { code: 'pa-IN', label: 'ਪੰਜਾਬੀ' },
  { code: 'od-IN', label: 'ଓଡ଼ିଆ' },
  { code: 'ur-IN', label: 'اردو' },
  { code: 'hi-IN', label: 'हिन्दी' },
  { code: 'en-IN', label: 'English' },
]

const QUICK_ACTIONS = [
  { label: 'Apply for a driving license', starter: 'I want to apply for a driving license' },
  { label: 'Track an application', starter: 'How do I track my driving license application?' },
  { label: 'Check eligibility', starter: 'Am I eligible to apply for a learner’s license?' },
]

function playAudioBase64(base64) {
  const bytes = atob(base64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const blob = new Blob([arr], { type: 'audio/wav' })
  const audio = new Audio(URL.createObjectURL(blob))
  audio.play().catch(() => {}) // if autoplay is ever blocked, the message's own audio stays available to replay
  return audio
}

function MicIcon({ recording }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
      {recording ? (
        <rect x="6" y="6" width="12" height="12" rx="2" fill="white" stroke="none" />
      ) : (
        <>
          <rect x="9" y="2" width="6" height="12" rx="3" fill="white" stroke="none" />
          <path d="M5 10a7 7 0 0 0 14 0" strokeLinecap="round" />
          <path d="M12 19v3" strokeLinecap="round" />
        </>
      )}
    </svg>
  )
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
      <path d="M3 20l18-8L3 4v6l12 2-12 2z" />
    </svg>
  )
}

export default function App() {
  const [lang, setLang] = useState(null) // null until the user picks one on the language screen
  const [messages, setMessages] = useState([])
  const [history, setHistory] = useState([])
  const [inputText, setInputText] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [isGreeting, setIsGreeting] = useState(false)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])

  async function chooseLanguage(code) {
    setLang(code)
    setIsGreeting(true)
    try {
      const resp = await fetch('/api/greet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: code }),
      })
      const data = await resp.json()
      setMessages([{ role: 'assistant', text: data.reply_text, lang: data.language }])
      playAudioBase64(data.audio_base64)
    } catch {
      setMessages([{ role: 'assistant', text: 'Connection error — is the backend running?', lang: code }])
    } finally {
      setIsGreeting(false)
    }
  }

  async function sendText(text) {
    if (!text.trim() || isSending) return
    setMessages((m) => [...m, { role: 'user', text, lang: '' }])
    setInputText('')
    setIsSending(true)
    try {
      const resp = await fetch('/api/chat/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history, language: lang }),
      })
      const data = await resp.json()
      setHistory(data.history)
      setLang(data.language) // keep tracking language turn to turn in case it changes
      setMessages((m) => [
        ...m,
        { role: 'assistant', text: data.reply_text, lang: data.language, citations: data.citations },
      ])
      playAudioBase64(data.audio_base64)
    } catch {
      setMessages((m) => [...m, { role: 'assistant', text: 'Connection error — is the backend running?', lang: '' }])
    } finally {
      setIsSending(false)
    }
  }

  async function toggleRecording() {
    if (isRecording) {
      mediaRecorderRef.current?.stop()
      setIsRecording(false)
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data)
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setIsSending(true)
        try {
          const form = new FormData()
          form.append('audio', blob, 'input.webm')
          form.append('history', JSON.stringify(history))
          const resp = await fetch('/api/chat/voice', { method: 'POST', body: form })
          const data = await resp.json()
          setHistory(data.history)
          setLang(data.language) // voice always detects fresh from audio — follow whatever they actually spoke
          setMessages((m) => [
            ...m,
            { role: 'user', text: data.user_text, lang: data.language },
            { role: 'assistant', text: data.reply_text, lang: data.language, citations: data.citations },
          ])
          playAudioBase64(data.audio_base64)
        } catch {
          setMessages((m) => [...m, { role: 'assistant', text: 'Connection error — is the backend running?', lang: '' }])
        } finally {
          setIsSending(false)
        }
      }
      recorder.start()
      mediaRecorderRef.current = recorder
      setIsRecording(true)
    } catch {
      alert('Microphone access is needed to record your answer.')
    }
  }

  if (!lang) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#f7f8fa] p-6">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 max-w-lg w-full text-center">
          <div className="w-12 h-12 mx-auto rounded-full bg-linear-to-br from-orange-400 to-green-500 flex items-center justify-center text-white text-lg font-bold mb-4">
            S
          </div>
          <h1 className="text-lg font-semibold text-gray-900 mb-1">Choose your language</h1>
          <p className="text-sm text-gray-500 mb-6">भाषा चुनें · மொழியைத் தேர்ந்தெடுக்கவும் · భాషను ఎంచుకోండి</p>
          <div className="grid grid-cols-3 gap-3">
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                onClick={() => chooseLanguage(l.code)}
                disabled={isGreeting}
                className="rounded-xl border border-gray-200 py-3 text-sm font-medium text-gray-700 hover:border-green-400 hover:bg-green-50 disabled:opacity-40 transition-colors"
              >
                {l.label}
              </button>
            ))}
          </div>
          {isGreeting && <p className="text-xs text-gray-400 mt-4">Loading…</p>}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-[#f7f8fa]">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col p-4 shrink-0">
        <div className="flex items-center gap-2 px-2 py-3">
          <div className="w-8 h-8 rounded-full bg-linear-to-br from-orange-400 to-green-500 flex items-center justify-center text-white text-xs font-bold">
            S
          </div>
          <span className="font-semibold text-gray-900">Seva AI</span>
        </div>

        <nav className="mt-4 flex flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                item.key === 'home' ? 'bg-green-50 text-green-700 font-medium' : 'text-gray-500 hover:bg-gray-50'
              }`}
            >
              <span>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="flex-1" />

        <div className="flex flex-col gap-1 border-t border-gray-100 pt-3">
          <button className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-500 hover:bg-gray-50 text-left">
            <span>👤</span> Profile
          </button>
          <button className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-500 hover:bg-gray-50 text-left">
            <div className="w-6 h-6 rounded-full bg-gray-900 text-white text-[10px] flex items-center justify-center">
              N
            </div>
            Settings
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-8">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">👋 Seva AI</h1>
            <p className="text-gray-500 text-sm mt-1">Your Driving License & RTO assistant</p>
          </div>
          <div className="w-9 h-9 rounded-full bg-gray-100 text-gray-600 text-xs font-medium flex items-center justify-center">
            SA
          </div>
        </div>

        {/* Chat card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mb-6">
          <div className="flex items-start gap-3 mb-4">
            <div className="w-9 h-9 rounded-full bg-linear-to-br from-orange-400 to-green-500 flex items-center justify-center text-white text-sm font-bold shrink-0">
              S
            </div>
            <div>
              <p className="font-semibold text-gray-900">Hello! I'm Seva AI.</p>
              <p className="text-sm text-gray-500">Ask me anything about driving licenses or RTO services.</p>
            </div>
          </div>

          {messages.length > 0 && (
            <div className="flex flex-col gap-3 mb-4 max-h-96 overflow-y-auto pr-1">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${
                      msg.role === 'user' ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-800'
                    }`}
                  >
                    <p>{msg.text}</p>
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
              {isSending && <p className="text-xs text-gray-400">SEVA is thinking…</p>}
            </div>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={toggleRecording}
              className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 transition-colors ${
                isRecording ? 'bg-red-500 animate-pulse' : 'bg-green-600 hover:bg-green-700'
              }`}
              title={isRecording ? 'Stop recording' : 'Record your answer'}
            >
              <MicIcon recording={isRecording} />
            </button>
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendText(inputText)}
              placeholder="Ask about driving licenses or RTO services..."
              disabled={isRecording}
              className="flex-1 rounded-full border border-gray-200 bg-gray-50 px-4 py-2 text-sm outline-none focus:border-green-400"
            />
            <button
              onClick={() => sendText(inputText)}
              disabled={isSending || !inputText.trim()}
              className="w-10 h-10 rounded-full bg-green-600 hover:bg-green-700 disabled:opacity-40 flex items-center justify-center shrink-0"
              title="Send"
            >
              <SendIcon />
            </button>
          </div>

          <div className="flex flex-wrap gap-2 mt-3">
            {QUICK_ACTIONS.map((qa) => (
              <button
                key={qa.label}
                onClick={() => sendText(qa.starter)}
                className="text-xs px-3 py-1.5 rounded-full border border-gray-200 text-gray-600 hover:bg-gray-50"
              >
                {qa.label}
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
