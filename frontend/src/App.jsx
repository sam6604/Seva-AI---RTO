import { useEffect, useRef, useState } from 'react'
import FloatingAssistant from './FloatingAssistant'
import Logo from './Logo'
import DocumentChecklist from './DocumentChecklist'
import AmIReady from './AmIReady'
import Profile from './Profile'
import { MicIcon, SendIcon, playAudioBase64 } from './utils'
import { t, uiLangFor, UI_LANGUAGES, serviceName } from './i18n'

const TEXT_SIZE_KEY = 'seva_text_size'
const CHECKLIST_KEY = 'seva_checklist_v1'

export default function App() {
  const [lang, setLang] = useState(null) // null until the user picks one on the language screen
  const [activeTab, setActiveTab] = useState('home')
  const [messages, setMessages] = useState([])
  const [history, setHistory] = useState([])
  const [inputText, setInputText] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [isGreeting, setIsGreeting] = useState(false)
  const [officialLinks, setOfficialLinks] = useState(null) // {service_id: {label, links: [{label, url}]}}
  const [textSize, setTextSize] = useState(() => localStorage.getItem(TEXT_SIZE_KEY) || 'normal')
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])

  const uiLang = uiLangFor(lang)

  const NAV_ITEMS = [
    { key: 'home', label: t(uiLang, 'navHome'), icon: '🏠' },
    { key: 'checklist', label: t(uiLang, 'navChecklist'), icon: '📋' },
    { key: 'ready', label: t(uiLang, 'navReady'), icon: '✅' },
  ]

  const QUICK_ACTIONS = [
    { label: t(uiLang, 'quickApply'), starter: 'I want to apply for a driving license' },
    { label: t(uiLang, 'quickTrack'), starter: 'How do I track my driving license application?' },
    { label: t(uiLang, 'quickEligible'), starter: 'Am I eligible to apply for a learner’s license?' },
  ]

  useEffect(() => {
    fetch('/api/official-links')
      .then((r) => (r.ok ? r.json() : null))
      .then(setOfficialLinks)
      .catch(() => setOfficialLinks(null)) // silently unavailable is fine — it's a convenience shortcut, not required
  }, [])

  function openOfficialPortal(serviceId) {
    const entry = officialLinks?.[serviceId]
    const url = entry?.links?.[0]?.url
    if (!url) return
    // noopener/noreferrer: the government site never gets a handle back to
    // this window (security requirement — no cross-origin access).
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  function changeTextSize(size) {
    setTextSize(size)
    localStorage.setItem(TEXT_SIZE_KEY, size)
  }

  function resetEverything() {
    localStorage.removeItem(CHECKLIST_KEY)
    setLang(null)
    setActiveTab('home')
    setMessages([])
    setHistory([])
  }

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
      setMessages([{ role: 'assistant', text: t(uiLangFor(code), 'connectionError'), lang: code }])
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
        { role: 'assistant', text: data.reply_text, lang: data.language, citations: data.citations, isError: Boolean(data.error) },
      ])
      playAudioBase64(data.audio_base64)
    } catch {
      setMessages((m) => [...m, { role: 'assistant', text: t(uiLang, 'connectionError'), lang: '' }])
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
            { role: 'assistant', text: data.reply_text, lang: data.language, citations: data.citations, isError: Boolean(data.error) },
          ])
          playAudioBase64(data.audio_base64)
        } catch {
          setMessages((m) => [...m, { role: 'assistant', text: t(uiLang, 'connectionError'), lang: '' }])
        } finally {
          setIsSending(false)
        }
      }
      recorder.start()
      mediaRecorderRef.current = recorder
      setIsRecording(true)
    } catch {
      alert(t(uiLang, 'micError'))
    }
  }

  if (!lang) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#f7f8fa] p-6">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 max-w-lg w-full text-center">
          <div className="mx-auto mb-4">
            <Logo size={56} />
          </div>
          <h1 className="text-lg font-semibold text-gray-900 mb-1">Choose your language</h1>
          <p className="text-sm text-gray-500 mb-6">भाषा चुनें · భాష ఎంచుకోండి · ଭାଷା ବାଛନ୍ତୁ</p>
          <div className="grid grid-cols-2 gap-3">
            {UI_LANGUAGES.map((l) => (
              <button
                key={l.code}
                onClick={() => chooseLanguage(l.code)}
                disabled={isGreeting}
                className="rounded-xl border border-gray-200 py-4 text-base font-medium text-gray-700 hover:border-green-400 hover:bg-green-50 disabled:opacity-40 transition-colors"
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

  const textSizeClass = textSize === 'large' ? 'text-lg' : 'text-base'

  return (
    <div className={`flex h-screen bg-[#f7f8fa] ${textSizeClass}`}>
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col p-4 shrink-0">
        <div className="flex items-center gap-2 px-2 py-3">
          <Logo size={32} />
          <span className="font-semibold text-gray-900">{t(uiLang, 'appName')}</span>
        </div>

        <nav className="mt-4 flex flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => setActiveTab(item.key)}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                activeTab === item.key ? 'bg-green-50 text-green-700 font-medium' : 'text-gray-500 hover:bg-gray-50'
              }`}
            >
              <span>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="flex-1" />

        <div className="flex flex-col gap-1 border-t border-gray-100 pt-3">
          <button
            onClick={() => setActiveTab('profile')}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
              activeTab === 'profile' ? 'bg-green-50 text-green-700 font-medium' : 'text-gray-500 hover:bg-gray-50'
            }`}
          >
            <span>👤</span> {t(uiLang, 'navProfile')}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-8">
        {activeTab === 'checklist' && <DocumentChecklist uiLang={uiLang} />}
        {activeTab === 'ready' && <AmIReady uiLang={uiLang} />}
        {activeTab === 'profile' && (
          <Profile
            uiLang={uiLang}
            lang={lang}
            onChangeLanguage={setLang}
            textSize={textSize}
            onChangeTextSize={changeTextSize}
            onResetAll={resetEverything}
          />
        )}

        {activeTab === 'home' && (
          <>
            <div className="flex items-start justify-between mb-6">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">👋 {t(uiLang, 'appName')}</h1>
                <p className="text-gray-500 text-sm mt-1">{t(uiLang, 'tagline')}</p>
              </div>
              <div className="w-9 h-9 rounded-full bg-gray-100 text-gray-600 text-xs font-medium flex items-center justify-center">
                <Logo size={22} />
              </div>
            </div>

            {/* Open Official Portal — the citizen picks their service and
                control stays entirely with them; we only open the real
                government site in a new tab, nothing is scraped or auto-filled. */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mb-6">
              <p className="text-sm font-semibold text-gray-900 mb-1">{t(uiLang, 'openPortalTitle')}</p>
              <p className="text-xs text-gray-500 mb-3">{t(uiLang, 'openPortalSubtitle')}</p>
              <div className="flex flex-wrap gap-2">
                {officialLinks &&
                  Object.entries(officialLinks).map(([serviceId, entry]) => (
                    <button
                      key={serviceId}
                      onClick={() => openOfficialPortal(serviceId)}
                      disabled={!entry.links?.length}
                      className="text-sm px-4 py-2 rounded-full border border-green-200 bg-green-50 text-green-700 hover:bg-green-100 disabled:opacity-40 font-medium"
                    >
                      {t(uiLang, 'openPortalBtn', serviceName(uiLang, serviceId))}
                    </button>
                  ))}
                {!officialLinks && <p className="text-xs text-gray-400">{t(uiLang, 'loadingLinks')}</p>}
              </div>
            </div>

            {/* Chat card */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mb-6">
              <div className="flex items-start gap-3 mb-4">
                <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0">
                  <Logo size={36} />
                </div>
                <div>
                  <p className="font-semibold text-gray-900">{t(uiLang, 'greetingTitle')}</p>
                  <p className="text-sm text-gray-500">{t(uiLang, 'greetingSubtitle')}</p>
                </div>
              </div>

              {messages.length > 0 && (
                <div className="flex flex-col gap-3 mb-4 max-h-96 overflow-y-auto pr-1">
                  {messages.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div
                        className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${
                          msg.role === 'user'
                            ? 'bg-green-600 text-white'
                            : msg.isError
                              ? 'bg-red-50 text-red-700 border border-red-100'
                              : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        <p>{msg.text}</p>
                        {msg.citations?.length > 0 && (
                          <details className="mt-2 text-xs opacity-80">
                            <summary className="cursor-pointer">📚 {t(uiLang, 'sources')}</summary>
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
                  {isSending && <p className="text-xs text-gray-400">{t(uiLang, 'thinking')}</p>}
                </div>
              )}

              <div className="flex items-center gap-2">
                <button
                  onClick={toggleRecording}
                  className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 transition-colors ${
                    isRecording ? 'bg-red-500 animate-pulse' : 'bg-green-600 hover:bg-green-700'
                  }`}
                  title={isRecording ? t(uiLang, 'stopRecordTitle') : t(uiLang, 'recordTitle')}
                >
                  <MicIcon recording={isRecording} />
                </button>
                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && sendText(inputText)}
                  placeholder={t(uiLang, 'inputPlaceholder')}
                  disabled={isRecording}
                  className="flex-1 rounded-full border border-gray-200 bg-gray-50 px-4 py-2 text-sm outline-none focus:border-green-400"
                />
                <button
                  onClick={() => sendText(inputText)}
                  disabled={isSending || !inputText.trim()}
                  className="w-10 h-10 rounded-full bg-green-600 hover:bg-green-700 disabled:opacity-40 flex items-center justify-center shrink-0"
                  title={t(uiLang, 'sendTitle')}
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
          </>
        )}
      </main>

      {/* Floating assistant — a separate, self-contained quick-help panel
          available anywhere in the app, reusing the same backend pipeline
          as the main chat. */}
      <FloatingAssistant lang={lang} uiLang={uiLang} />
    </div>
  )
}
