import { useState } from 'react'

// Drop the real logo file at frontend/public/logo.jpeg (NOT src/assets — this
// is Vite's public/ dir, served as a plain static file with no import/build
// step, so it works immediately in dev AND production the moment the file
// exists, with zero code changes). Every usage site in the app already
// renders <Logo />, not raw markup, so adding the file is the only step
// needed for it to appear everywhere at once.
//
// NOTE: JPEG has no transparency, so a white background around the logo
// will show as a visible white box on the colored spots this renders over
// (e.g. FloatingAssistant's gradient header) — fine on plain white
// backgrounds (sidebar, language picker), less clean elsewhere. Switch this
// path to a .png with a transparent background if that ever matters.
//
// Until the file exists, this falls back to an SVG recreation of the same
// design (orange/green arcs + blue soundwave) instead of a broken image icon.
export default function Logo({ size = 32 }) {
  const [imgFailed, setImgFailed] = useState(false)

  if (!imgFailed) {
    return (
      <img
        src="/logo.jpeg"
        width={size}
        height={size}
        alt="Seva AI"
        style={{ width: size, height: size, objectFit: 'contain' }}
        onError={() => setImgFailed(true)}
      />
    )
  }

  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="sevaOrange" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#fb923c" />
          <stop offset="100%" stopColor="#f97316" />
        </linearGradient>
        <linearGradient id="sevaGreen" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor="#16a34a" />
          <stop offset="100%" stopColor="#22c55e" />
        </linearGradient>
        <linearGradient id="sevaBlue" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2563eb" />
          <stop offset="100%" stopColor="#1e3a8a" />
        </linearGradient>
      </defs>

      <path
        d="M 78 22 A 38 38 0 1 0 68 82"
        stroke="url(#sevaOrange)"
        strokeWidth="13"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M 32 82 A 38 38 0 0 0 74 34"
        stroke="url(#sevaGreen)"
        strokeWidth="13"
        strokeLinecap="round"
        fill="none"
      />

      <g stroke="url(#sevaBlue)" strokeWidth="6" strokeLinecap="round">
        <line x1="30" y1="50" x2="30" y2="50" />
        <line x1="40" y1="42" x2="40" y2="58" />
        <line x1="50" y1="30" x2="50" y2="70" />
        <line x1="60" y1="42" x2="60" y2="58" />
        <line x1="70" y1="50" x2="70" y2="50" />
      </g>
    </svg>
  )
}
