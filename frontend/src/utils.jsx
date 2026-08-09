// Shared between App.jsx (main chat) and FloatingAssistant.jsx (Phase 3) so
// the two don't duplicate the same audio-playback/icon code. Behavior is
// unchanged from what App.jsx had before Phase 3 — this is purely an
// extraction, not a redesign.

export function playAudioBase64(base64) {
  if (!base64) return null // TTS can fail gracefully now (Phase 3 error handling) and return ""
  try {
    const bytes = atob(base64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const blob = new Blob([arr], { type: 'audio/wav' })
    const audio = new Audio(URL.createObjectURL(blob))
    audio.play().catch(() => {}) // if autoplay is ever blocked, the message's own audio stays available to replay
    return audio
  } catch {
    return null // malformed audio should never break the text reply that's already showing
  }
}

export function MicIcon({ recording, size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
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

export function SendIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="white">
      <path d="M3 20l18-8L3 4v6l12 2-12 2z" />
    </svg>
  )
}

export function StopIcon({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="white">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  )
}

// Phase 3 Part 2: pulls a clickable "Open Official Portal" action out of a
// reply's citations, when the reply actually grounded itself in an
// official_link chunk (see retrieval/chunking.py — citation text for that
// category is always "Official portal — {label}: {url}"). Returns null if
// no official-link citation is present, rather than guessing a URL.
export function extractPortalLink(citations) {
  if (!citations?.length) return null
  for (const c of citations) {
    const match = c.match(/Official portal — (.+?):\s*(https?:\/\/\S+)/)
    if (match) return { label: match[1], url: match[2] }
  }
  return null
}
