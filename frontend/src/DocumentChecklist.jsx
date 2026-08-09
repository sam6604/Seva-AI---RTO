import { useEffect, useState } from 'react'
import { t } from './i18n'

const STORAGE_KEY = 'seva_checklist_v1'

function loadChecked() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

export default function DocumentChecklist({ uiLang }) {
  const [documents, setDocuments] = useState(null) // null = loading, [] = loaded-but-empty
  const [checked, setChecked] = useState(loadChecked)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch('/api/checklist/driving_license')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => setDocuments(data.documents || []))
      .catch(() => setError(true))
  }, [])

  function toggle(doc) {
    setChecked((prev) => {
      const next = { ...prev, [doc]: !prev[doc] }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }

  function resetAll() {
    setChecked({})
    localStorage.removeItem(STORAGE_KEY)
  }

  const doneCount = documents ? documents.filter((d) => checked[d]).length : 0
  const total = documents?.length || 0

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-1">{t(uiLang, 'checklistTitle')}</h1>
      <p className="text-gray-500 text-sm mb-6">{t(uiLang, 'checklistSubtitle')}</p>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        {error && <p className="text-sm text-red-600">{t(uiLang, 'checklistLoadError')}</p>}

        {!error && documents === null && <p className="text-sm text-gray-400">{t(uiLang, 'loading')}</p>}

        {!error && documents !== null && documents.length === 0 && (
          <p className="text-sm text-gray-400">—</p>
        )}

        {!error && documents !== null && documents.length > 0 && (
          <>
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm font-medium text-gray-700">
                  {t(uiLang, 'checklistProgress', doneCount, total)}
                </span>
                {doneCount > 0 && (
                  <button onClick={resetAll} className="text-xs text-gray-400 hover:text-gray-600 underline">
                    {t(uiLang, 'checklistResetBtn')}
                  </button>
                )}
              </div>
              <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                <div
                  className="h-full bg-green-500 transition-all"
                  style={{ width: `${total ? (doneCount / total) * 100 : 0}%` }}
                />
              </div>
            </div>

            <ul className="flex flex-col gap-2">
              {documents.map((doc) => (
                <li key={doc}>
                  <button
                    onClick={() => toggle(doc)}
                    className={`w-full flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors ${
                      checked[doc]
                        ? 'border-green-200 bg-green-50'
                        : 'border-gray-200 bg-white hover:border-gray-300'
                    }`}
                  >
                    <span
                      className={`w-6 h-6 rounded-md border-2 flex items-center justify-center shrink-0 ${
                        checked[doc] ? 'bg-green-600 border-green-600' : 'border-gray-300'
                      }`}
                    >
                      {checked[doc] && (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3">
                          <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    <span className={`text-sm ${checked[doc] ? 'text-green-800 line-through' : 'text-gray-800'}`}>
                      {doc}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
