import { useState } from 'react'
import { t } from './i18n'

// General Motor Vehicles Act guidance (India): 16+ can hold a Learner's
// License for gearless <50cc two-wheelers only; everything else needs 18+.
// This is publicly documented law, not something retrieved/verified per-user
// via RAG — kept clearly labeled as general guidance with a disclaimer,
// same honesty standard as the rest of the app.
function checkEligibility(age, vehicle) {
  const a = Number(age)
  if (!a || a < 16) return { ok: false, level: 'no' }
  if (a >= 16 && a < 18) {
    if (vehicle === 'gearless') return { ok: true, level: 'conditional' }
    return { ok: false, level: 'under18' }
  }
  return { ok: true, level: 'yes' }
}

// Approximate MoRTH (central) base fees in INR, per CMV Rules 1989 Rule 32 —
// publicly published ballpark figures, NOT a verified per-state fee
// schedule. State RTOs commonly add their own charges on top, hence the
// disclaimer everywhere this number is shown.
//
// Per-class fees (test + issue) apply once per vehicle class since each
// class needs its own test and endorsement. The Learner's License fee is
// charged once per application regardless of how many classes it covers.
// Someone ALREADY holding a license who is adding a class pays the cheaper
// "addition of class" fee instead of a fresh LL+test+issue for that class.
const FEES = {
  learnerLicense: 150,
  drivingTest: 300,
  licenseIssue: 200,
  additionalClass: 500,
  smartCard: 200,
}

const VEHICLE_CLASS_OPTIONS = [
  { key: 'gearless', labelKey: 'eligibilityVehicleGearless' },
  { key: 'geared', labelKey: 'eligibilityVehicleGeared' },
  { key: 'four', labelKey: 'eligibilityVehicleFour' },
  { key: 'commercial', labelKey: 'feeClassCommercial' },
]

export default function AmIReady({ uiLang }) {
  const [age, setAge] = useState('')
  const [vehicle, setVehicle] = useState('gearless')
  const [eligibility, setEligibility] = useState(null)

  const [feeClasses, setFeeClasses] = useState([])
  const [hasLL, setHasLL] = useState(false)
  const [hasExistingDL, setHasExistingDL] = useState(false)
  const [feeResult, setFeeResult] = useState(null) // { lines: [{label, amount}], total } | 'select-one'

  const [rtoStatus, setRtoStatus] = useState('idle') // idle | locating | denied | unsupported

  function handleEligibilityCheck() {
    setEligibility(checkEligibility(age, vehicle))
  }

  function toggleFeeClass(key) {
    setFeeClasses((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]))
  }

  function handleFeeCalculate() {
    const n = feeClasses.length
    if (n === 0) {
      setFeeResult('select-one')
      return
    }

    const lines = []
    if (hasExistingDL) {
      // Adding class(es) to an existing license — no fresh LL needed, the
      // per-class fee already covers test + endorsement.
      lines.push({ label: t(uiLang, 'feeLineAddClass', n), amount: FEES.additionalClass * n })
    } else {
      if (!hasLL) lines.push({ label: t(uiLang, 'feeLineLL'), amount: FEES.learnerLicense })
      lines.push({ label: t(uiLang, 'feeLineTest', n), amount: FEES.drivingTest * n })
      lines.push({ label: t(uiLang, 'feeLineIssue', n), amount: FEES.licenseIssue * n })
    }
    lines.push({ label: t(uiLang, 'feeLineSmartCard'), amount: FEES.smartCard })

    setFeeResult({ lines, total: lines.reduce((sum, l) => sum + l.amount, 0) })
  }

  function findNearbyRTO() {
    if (!navigator.geolocation) {
      setRtoStatus('unsupported')
      return
    }
    setRtoStatus('locating')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords
        window.open(
          `https://www.google.com/maps/search/RTO+office/@${latitude},${longitude},13z`,
          '_blank',
          'noopener,noreferrer',
        )
        setRtoStatus('idle')
      },
      () => setRtoStatus('denied'),
    )
  }

  return (
    <div className="max-w-2xl flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-1">{t(uiLang, 'readyTitle')}</h1>
        <p className="text-gray-500 text-sm">{t(uiLang, 'readySubtitle')}</p>
      </div>

      {/* Eligibility */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p className="text-sm font-semibold text-gray-900 mb-3">{t(uiLang, 'eligibilityTitle')}</p>
        <div className="flex flex-col gap-3">
          <label className="text-xs text-gray-500">
            {t(uiLang, 'eligibilityAge')}
            <input
              type="number"
              min="1"
              max="120"
              value={age}
              onChange={(e) => setAge(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-green-400"
            />
          </label>
          <label className="text-xs text-gray-500">
            {t(uiLang, 'eligibilityVehicle')}
            <select
              value={vehicle}
              onChange={(e) => setVehicle(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-green-400 bg-white"
            >
              <option value="gearless">{t(uiLang, 'eligibilityVehicleGearless')}</option>
              <option value="geared">{t(uiLang, 'eligibilityVehicleGeared')}</option>
              <option value="four">{t(uiLang, 'eligibilityVehicleFour')}</option>
            </select>
          </label>
          <button
            onClick={handleEligibilityCheck}
            disabled={!age}
            className="self-start px-4 py-2 rounded-full bg-green-600 hover:bg-green-700 disabled:opacity-40 text-white text-sm font-medium"
          >
            {t(uiLang, 'eligibilityCheckBtn')}
          </button>

          {eligibility && (
            <div
              className={`rounded-xl p-3 text-sm ${
                eligibility.level === 'yes'
                  ? 'bg-green-50 text-green-800'
                  : eligibility.level === 'conditional'
                    ? 'bg-amber-50 text-amber-800'
                    : 'bg-red-50 text-red-800'
              }`}
            >
              {eligibility.level === 'yes' && '✅ '}
              {eligibility.level === 'conditional' && '⚠️ '}
              {(eligibility.level === 'no' || eligibility.level === 'under18') && '❌ '}
              {eligibility.level === 'yes' && t(uiLang, 'eligibilityResultYes')}
              {eligibility.level === 'conditional' && t(uiLang, 'eligibilityResultConditional')}
              {eligibility.level === 'under18' && t(uiLang, 'eligibilityResultUnder18')}
              {eligibility.level === 'no' && t(uiLang, 'eligibilityResultNo')}
            </div>
          )}
          <p className="text-xs text-gray-400">{t(uiLang, 'eligibilityDisclaimer')}</p>
        </div>
      </div>

      {/* Fee estimator */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p className="text-sm font-semibold text-gray-900 mb-3">{t(uiLang, 'feeTitle')}</p>

        <p className="text-xs text-gray-500 mb-2">{t(uiLang, 'feeVehicleClasses')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
          {VEHICLE_CLASS_OPTIONS.map((opt) => (
            <label
              key={opt.key}
              className={`flex items-center gap-2 text-sm rounded-lg border px-3 py-2 cursor-pointer ${
                feeClasses.includes(opt.key) ? 'border-green-400 bg-green-50' : 'border-gray-200'
              }`}
            >
              <input
                type="checkbox"
                checked={feeClasses.includes(opt.key)}
                onChange={() => toggleFeeClass(opt.key)}
                className="w-4 h-4"
              />
              {t(uiLang, opt.labelKey)}
            </label>
          ))}
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-700 mb-2">
          <input type="checkbox" checked={hasLL} onChange={(e) => setHasLL(e.target.checked)} className="w-4 h-4" />
          {t(uiLang, 'feeHasLL')}
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700 mb-3">
          <input
            type="checkbox"
            checked={hasExistingDL}
            onChange={(e) => setHasExistingDL(e.target.checked)}
            className="w-4 h-4"
          />
          {t(uiLang, 'feeHasExistingDL')}
        </label>

        <button
          onClick={handleFeeCalculate}
          className="px-4 py-2 rounded-full bg-green-600 hover:bg-green-700 text-white text-sm font-medium"
        >
          {t(uiLang, 'feeCalculateBtn')}
        </button>

        {feeResult === 'select-one' && (
          <p className="text-sm text-red-600 mt-3">{t(uiLang, 'feeSelectAtLeastOne')}</p>
        )}

        {feeResult && feeResult !== 'select-one' && (
          <div className="mt-3 rounded-xl bg-gray-50 p-3 text-sm text-gray-800">
            <p className="text-xs font-semibold text-gray-500 mb-2">{t(uiLang, 'feeBreakdown')}</p>
            <ul className="flex flex-col gap-1 mb-2">
              {feeResult.lines.map((line, i) => (
                <li key={i} className="flex justify-between text-xs text-gray-600">
                  <span>{line.label}</span>
                  <span>₹{line.amount}</span>
                </li>
              ))}
            </ul>
            <div className="border-t border-gray-200 pt-2 font-semibold">
              {t(uiLang, 'feeTotal')}: ₹{feeResult.total}
            </div>
          </div>
        )}
        <p className="text-xs text-gray-400 mt-2">{t(uiLang, 'feeDisclaimer')}</p>
      </div>

      {/* Nearby RTO finder */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <p className="text-sm font-semibold text-gray-900 mb-1">{t(uiLang, 'rtoTitle')}</p>
        <p className="text-xs text-gray-500 mb-3">{t(uiLang, 'rtoSubtitle')}</p>
        <button
          onClick={findNearbyRTO}
          disabled={rtoStatus === 'locating'}
          className="px-4 py-2 rounded-full bg-green-600 hover:bg-green-700 disabled:opacity-40 text-white text-sm font-medium"
        >
          {rtoStatus === 'locating' ? t(uiLang, 'rtoLocating') : t(uiLang, 'rtoFindBtn')}
        </button>
        {rtoStatus === 'denied' && <p className="text-xs text-red-600 mt-2">{t(uiLang, 'rtoDenied')}</p>}
        {rtoStatus === 'unsupported' && <p className="text-xs text-red-600 mt-2">{t(uiLang, 'rtoUnsupported')}</p>}
      </div>
    </div>
  )
}
