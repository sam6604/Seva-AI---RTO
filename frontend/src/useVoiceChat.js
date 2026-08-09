import { useRef, useState } from 'react'
import { playAudioBase64 } from './utils'

// A small state machine instead of separate booleans (isRecording,
// isSending, isSpeaking as independent flags) — makes "what's the UI state
// right now" a single source of truth instead of something that could go
// out of sync (e.g. isRecording AND isSpeaking both true at once, which
// shouldn't be possible).
//   idle      -> "Tap to speak" — ready for the user to act
//   listening -> mic is recording ("Listening...")
//   thinking  -> waiting on the backend ("SEVA is thinking...")
//   speaking  -> TTS audio is playing ("SEVA is speaking..." + STOP control)

// Recordings shorter than this are almost certainly an accidental tap, not
// real speech — skip sending them rather than round-tripping to the
// backend for an STT call that will just fail on near-empty audio.
const MIN_AUDIO_BYTES = 2000

export function useVoiceChat({ lang, voiceEndpoint = '/api/chat/voice', textEndpoint = '/api/chat/text', onLanguageChange }) {
  const [status, setStatus] = useState('idle')
  const [messages, setMessages] = useState([])
  const [history, setHistory] = useState([])
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const audioRef = useRef(null)

  function stopSpeaking() {
    audioRef.current?.pause()
    audioRef.current = null
    setStatus('idle')
  }

  function playReply(base64) {
    const audio = playAudioBase64(base64)
    if (!audio) {
      setStatus('idle')
      return
    }
    audioRef.current = audio
    setStatus('speaking')
    // "automatically return to a ready-to-listen state" — once playback
    // finishes (or errors), drop straight back to idle so the mic/input is
    // immediately usable again without any extra manual reset. This is NOT
    // an auto-restart of the microphone — the user still has to tap; it
    // just means there's nothing blocking them from tapping right away.
    const backToIdle = () => {
      if (audioRef.current === audio) audioRef.current = null
      setStatus((s) => (s === 'speaking' ? 'idle' : s))
    }
    audio.addEventListener('ended', backToIdle)
    audio.addEventListener('error', backToIdle)
  }

  function applyTurnResult(data, userTextForVoice) {
    setHistory(data.history || [])
    if (data.language && data.language !== lang) onLanguageChange?.(data.language)
    setMessages((m) => {
      const next = [...m]
      if (userTextForVoice !== undefined) next.push({ role: 'user', text: userTextForVoice })
      next.push({
        role: 'assistant',
        text: data.reply_text || 'Sorry, no response came through.',
        citations: data.citations,
        isError: Boolean(data.error),
      })
      return next
    })
    playReply(data.audio_base64)
  }

  async function sendText(text) {
    const trimmed = (text || '').trim()
    if (!trimmed || status === 'thinking') return
    setMessages((m) => [...m, { role: 'user', text: trimmed }])
    setStatus('thinking')
    try {
      const resp = await fetch(textEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed, history, language: lang }),
      })
      if (!resp.ok) throw new Error('bad response')
      const data = await resp.json()
      applyTurnResult(data)
    } catch {
      setStatus('idle')
      setMessages((m) => [
        ...m,
        { role: 'assistant', text: "Connection error — I couldn't reach SEVA AI. Please try again.", isError: true },
      ])
    }
  }

  async function toggleRecording() {
    if (status === 'listening') {
      mediaRecorderRef.current?.stop()
      return
    }
    if (status === 'speaking') stopSpeaking() // tapping mic while SEVA is talking interrupts it, doesn't queue behind it
    if (status === 'thinking') return

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data)
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        if (blob.size < MIN_AUDIO_BYTES) {
          setStatus('idle')
          setMessages((m) => [
            ...m,
            { role: 'assistant', text: "Didn't catch that — please tap the mic and try again.", isError: true },
          ])
          return
        }
        setStatus('thinking')
        try {
          const form = new FormData()
          form.append('audio', blob, 'input.webm')
          form.append('history', JSON.stringify(history))
          const resp = await fetch(voiceEndpoint, { method: 'POST', body: form })
          if (!resp.ok) throw new Error('bad response')
          const data = await resp.json()
          applyTurnResult(data, data.user_text)
        } catch {
          setStatus('idle')
          setMessages((m) => [
            ...m,
            { role: 'assistant', text: "Couldn't hear that — please try again, or type your question instead.", isError: true },
          ])
        }
      }
      recorder.start()
      mediaRecorderRef.current = recorder
      setStatus('listening')
    } catch {
      // Microphone permission denied/unavailable — text must still work
      // (explicit Phase 3 requirement), so this only ever affects `status`.
      setStatus('idle')
      setMessages((m) => [
        ...m,
        { role: 'assistant', text: 'Microphone access is needed for voice — you can still type your question below.', isError: true },
      ])
    }
  }

  return {
    status,
    isRecording: status === 'listening',
    isSending: status === 'thinking',
    isSpeaking: status === 'speaking',
    messages,
    setMessages,
    history,
    sendText,
    toggleRecording,
    stopSpeaking,
  }
}
