import { useEffect, useState } from 'react'
import { t, UI_LANGUAGES } from './i18n'

const CHECKLIST_KEY = 'seva_checklist_v1'
const TEXT_SIZE_KEY = 'seva_text_size'

export default function Profile({ uiLang, lang, onChangeLanguage, textSize, onChangeTextSize, onResetAll }) {
  const [progress, setProgress] = useState({ done: 0, total: 0 })

  useEffect(() => {
    fetch('/api/checklist/driving_license')
      .then((r) => (r.ok ? r.json() : { documents: [] }))
      .then((data) => {
        const checked = JSON.parse(localStorage.getItem(CHECKLIST_KEY) || '{}')
        const docs = data.documents || []
        setProgress({ done: docs.filter((d) => checked[d]).length, total: docs.length })
      })
      .catch(() => {})
  }, [])

  return (
    <div className="max-w-2xl flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-gray-900">{t(uiLang, 'profileTitle')}</h1>

      {/* Language */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p className="text-sm font-semibold text-gray-900 mb-3">{t(uiLang, 'profileLanguageLabel')}</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {UI_LANGUAGES.map((l) => (
            <button
              key={l.code}
              onClick={() => onChangeLanguage(l.code)}
              className={`rounded-xl border py-2.5 text-sm font-medium transition-colors ${
                lang === l.code
                  ? 'border-green-500 bg-green-50 text-green-700'
                  : 'border-gray-200 text-gray-700 hover:border-gray-300'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      {/* Text size (accessibility) */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p className="text-sm font-semibold text-gray-900 mb-3">{t(uiLang, 'profileTextSize')}</p>
        <div className="flex gap-2">
          <button
            onClick={() => onChangeTextSize('normal')}
            className={`px-4 py-2 rounded-full text-sm font-medium border ${
              textSize === 'normal'
                ? 'border-green-500 bg-green-50 text-green-700'
                : 'border-gray-200 text-gray-700'
            }`}
          >
            {t(uiLang, 'profileTextSizeNormal')}
          </button>
          <button
            onClick={() => onChangeTextSize('large')}
            className={`px-4 py-2 rounded-full text-base font-medium border ${
              textSize === 'large'
                ? 'border-green-500 bg-green-50 text-green-700'
                : 'border-gray-200 text-gray-700'
            }`}
          >
            {t(uiLang, 'profileTextSizeLarge')}
          </button>
        </div>
      </div>

      {/* Checklist progress summary */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p className="text-sm font-semibold text-gray-900 mb-2">{t(uiLang, 'profileProgress')}</p>
        <div className="h-2 rounded-full bg-gray-100 overflow-hidden mb-2">
          <div
            className="h-full bg-green-500 transition-all"
            style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }}
          />
        </div>
        <p className="text-xs text-gray-500">
          {t(uiLang, 'checklistProgress', progress.done, progress.total)}
        </p>
      </div>

      {/* Reset */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p className="text-sm font-semibold text-gray-900 mb-1">{t(uiLang, 'profileResetTitle')}</p>
        <p className="text-xs text-gray-500 mb-3">{t(uiLang, 'profileResetSubtitle')}</p>
        <button
          onClick={onResetAll}
          className="px-4 py-2 rounded-full border border-red-200 text-red-600 hover:bg-red-50 text-sm font-medium"
        >
          {t(uiLang, 'profileResetBtn')}
        </button>
      </div>
    </div>
  )
}
