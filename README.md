# SEVA AI — Voice-First RTO Assistant

A voice + text assistant for Indian RTO (Regional Transport Office) services —
Driving Licence, Vehicle Registration, and Vehicle Ownership Transfer. Speak
or type in any of four supported UI languages (Hindi, Telugu, Odia, English —
the underlying voice pipeline supports 11+ Indian languages), and SEVA
replies in the same language, by text and voice, grounded in verified data
where it exists and honest about it where it doesn't.

This README documents what actually happens at each layer of the system —
data, RAG, intelligence, application, and the responsible-AI guardrails
threaded through all of them.

```
┌─────────────────────────────────────────────────────────────┐
│  DATA LAYER            data/<service_id>/*.json               │
│  ─ per-service dataset, official links, FAQ, "gap" markers    │
└──────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  RAG LAYER             retrieval/                              │
│  ─ chunking → BM25 + semantic index → RRF fusion → rerank      │
│  ─ service router, confidence gate, process outline, links     │
└──────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  INTELLIGENCE LAYER    intelligence.py                          │
│  ─ one system prompt + retrieved context → Sarvam LLM call     │
│  ─ conversation history *is* the state machine                 │
└──────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  APPLICATION LAYER     backend/ (FastAPI) + frontend/ (React)  │
│  ─ voice I/O (Sarvam STT/translate/TTS), tabs, state, i18n      │
└─────────────────────────────────────────────────────────────┘

  RESPONSIBLE-AI LAYER cuts across all four — see below.
```

---

## 1. Data Layer

**Location:** `data/<service_id>/`

Each of the three RTO services gets its own folder:

```
data/
├── driving_license/
│   ├── dl_dataset.json        ← prereq questions, steps, docs, form fields
│   └── official_links.json    ← verified government portal URLs
├── vehicle_registration/
│   ├── dataset.json           ← status: "no_verified_data" (explicit gap)
│   └── official_links.json
├── vehicle_transfer/
│   ├── dataset.json           ← status: "no_verified_data" (explicit gap)
│   └── official_links.json
└── faq.json                    ← cross-service FAQ, service_id: "general"
```

**The "gap" pattern.** `vehicle_registration` and `vehicle_transfer` don't
have verified step-by-step data yet. Rather than leaving that implicit (and
risking the LLM improvising an answer), their dataset files explicitly say
`"status": "no_verified_data"` with a note describing what real data would
need to look like. The RAG layer reads this marker and refuses to treat
anything from that service as grounding evidence — see §2. This is the
single source of truth for "is this service safe to answer from" throughout
the whole system.

**The swap point.** `dataset_loader.load_dataset(service_id)` is the one
function that touches raw dataset files — its signature is frozen so a real
backend/data-team integration can replace the function body without any
downstream code changing.

**Official links are separate from process data.** A service can have zero
verified process data but still have a real, verified official government
URL (`official_links.json`). This is what keeps the "gap" response
actionable instead of a dead end (§3, §5).

---

## 2. RAG Layer

**Location:** `retrieval/`

### Chunking strategy (`chunking.py`)

Every dataset file is turned into small, **metadata-tagged** chunks, not one
big blob per file:

| Field | Purpose |
|---|---|
| `service_id` | which of the 3 services this chunk belongs to (`"general"` for FAQ) |
| `category` | `eligibility` / `documents` / `procedure` / `forms` / `faq` / `official_link` / `gap` |
| `verified` | `False` for the two gap-service placeholder chunks — **never usable as grounding evidence** |
| `source` | human-readable provenance, surfaced back to the user as a citation |

A prereq question becomes one `eligibility` chunk; each step's docs, timing,
and narration becomes a `documents`/`procedure` chunk; each form field
becomes its own `forms` chunk. This granularity is what lets retrieval
return "the one relevant fact" instead of a whole step's worth of text for a
narrow question like "what do I enter in the LL number field."

### Indexing (`index.py`)

Two indices are built once at process start and cached in memory (the corpus
is small and static — no reason to re-embed on every request):

- **BM25** (`rank_bm25`) — classic keyword/term-frequency search.
- **TF-IDF → Truncated SVD (LSA)** — a lightweight "semantic" search that
  groups co-occurring terms into latent topics, so it catches paraphrases
  and related vocabulary a pure keyword match would miss. Chosen over a
  downloaded embedding model specifically to avoid a model-hub dependency at
  runtime and keep the stack unchanged (scikit-learn was already a
  dependency).

A shared tokenizer also normalizes British/American spelling variants
(`license`/`licence`) so a query typed the "wrong" way still matches the
government portal's own spelling.

### Retrieval pipeline (`pipeline.py`)

```
query → service router → [BM25 ∥ semantic] → RRF fusion → lexical rerank → confidence gate
```

1. **Service router** (`router.py`) — a keyword-stem classifier (not an LLM
   call — this runs on every turn and needs to be near-free) decides which
   of the 3 services the query is about, or returns `None` to search across
   all of them. Deliberately cheap: for a closed set of 3 known services, a
   rule-based classifier is plenty accurate and avoids an unnecessary
   sequential API call on the hot path.
2. **Gap short-circuit** — if the router pins a query to a service that has
   no verified process data, retrieval returns `insufficient_evidence=True`
   immediately, without scoring anything. This is a deliberate fast-path
   *and* a correctness guarantee: an unverified service's chunks can never
   accidentally outscore something real.
3. **Hybrid retrieval** — BM25 and semantic search run independently over
   the service-filtered candidates, each producing its own ranked list.
4. **RRF (Reciprocal Rank Fusion)** — the two ranked lists are merged by
   rank position (not raw score, since BM25 and cosine-similarity scores
   aren't on comparable scales), so both signals contribute.
5. **Rerank** (`rerank.py`) — a cheap lexical re-score (exact-phrase bonus,
   content-word overlap) nudges the fused order, and permanently
   deprioritizes any `verified=False` chunk. Deliberately *not* a
   cross-encoder API call — for a corpus this small, that would be the
   single biggest latency cost in the pipeline for negligible accuracy gain.
6. **Confidence gate** — a normalized score combining top BM25 and top
   cosine similarity is compared against `CONFIDENCE_FLOOR`. Below it (or if
   nothing survived the "verified-only" filter), the result is flagged
   `insufficient_evidence` regardless of service.

### What "insufficient evidence" produces (Phase 2 addition)

A gap doesn't mean a dead end. `process_guide.py` separately looks up that
service's **real official portal link** (independent of whether process data
exists) and attaches it to the fallback message — so "I don't have verified
steps for this yet" always still ends in "but here's where to actually go."

### Process outline injection (Phase 2)

Top-k retrieved fragments are enough for single-fact Q&A but not enough for
the model to reliably track "you're on step 2 of 4" across a multi-turn
conversation. `get_process_outline(service_id)` returns the **complete**
ordered step sequence (prereqs → steps → docs/fields) for a verified
service, formatted for prompt injection. The state-tracking itself is still
done by the LLM reading conversation history — this just gives it the whole
map instead of scattered puzzle pieces.

---

## 3. Intelligence Layer

**Location:** `intelligence.py`

One entry point: `respond(history, user_message, service_id=None)`.

There is deliberately **no hand-coded state machine, keyword classifier, or
step tracker** here — earlier iterations of this project had one (rigid
`stage`/`prereq_index` tracking, a `check_scope()` keyword matcher, a
`interpret_answer()` classifier for yes/no and multiple-choice answers), and
it kept breaking on real conversation: an answer like "3-wheeler" to a
two/four-wheeler question had nowhere to go, a user asking "how do I
register my car" got funneled into the driving-license flow because
"RTO-related" and "driving-license flow" were conflated into one check.
Replacing all of that with a single well-specified system prompt + full
conversation history let the model handle those cases by actually
understanding them, instead of every edge case needing a new `if` branch.

**What one call does:**

1. Retrieve grounding context via `retrieval.retrieve()` (§2).
2. If `insufficient_evidence` — return the fixed, honest fallback (+ official
   link if one exists) **without calling the LLM at all**. This is both a
   guardrail (never let the model guess) and a latency optimization (the
   fastest path in the whole pipeline skips the slowest step).
3. Otherwise, build one message list: `[system prompt] + history + [this
   turn's message, prefixed with the retrieved "Reference material" block
   and, when available, the full process outline + official links]`.
4. One call to Sarvam's chat completions (`sarvam-105b`).
5. Append both sides of the exchange to `history` **in place** — the caller
   just keeps reusing the same list turn after turn; that mutation *is* the
   conversation state.

**The system prompt** (not the code) is what encodes behavior:
- Ground DL answers *only* in the reference material given, never invent
  documents/fees/procedures.
- Be actionable — every reply should end in a concrete next step, not just
  explanation.
- For the DL flow specifically: ask prereqs one at a time, walk steps in
  order, use judgment on off-menu answers instead of dead-ending.
- Field-level guidance follows a fixed 5-part shape (what it means → what to
  enter → where to find it → an example → what not to enter) and explicitly
  refuses to guess which field the user means if they don't say — the model
  cannot see their screen, so this is guardrail-by-instruction, not a missing
  feature.
- Anything entirely unrelated to RTO/vehicles gets refused with one exact,
  fixed sentence — checked verbatim in code (`OUT_OF_SCOPE_REPLY`) to decide
  whether citations should be attached to the reply.

**Error handling:** a custom `AssistantUnavailableError` wraps any Sarvam API
failure (network error, empty response, missing `.choices`) into one clean
fallback message instead of ever letting a raw exception/attribute error
reach the user.

---

## 4. Application Layer

### Backend — `backend/main.py` (FastAPI)

A thin HTTP layer over the Python AI stack — every endpoint is a direct call
into `intelligence.py` / `sarvam_client.py` / `dataset_loader.py`, nothing
is reimplemented here.

| Endpoint | Purpose |
|---|---|
| `POST /api/chat/text` | text message → detect/translate language → `intelligence.respond()` → translate + synthesize reply |
| `POST /api/chat/voice` | multipart audio → STT (native script + language) → same pipeline as above |
| `POST /api/greet` | one-off, history-free localized greeting for the language-picker screen |
| `GET /api/official-links` | static, no-LLM lookup of verified portal URLs per service |
| `GET /api/checklist/{service_id}` | flat, deduplicated document list read straight from the dataset (same source of truth as RAG — the frontend never hand-duplicates this) |
| `GET /api/health` | liveness + whether `SARVAM_API_KEY` is actually loaded |

**Conditional formatting / error degradation:** every external call
(translate, TTS, STT) is wrapped so a failure in *one* piece never blocks
the rest of the response — e.g. if TTS fails, `audio_base64` comes back as
`""` and an `error` field is set, but `reply_text` still arrives. The
frontend renders that `error` flag as a distinct red-bordered message style
rather than crashing or silently swallowing the failure.

### Frontend — `frontend/src/` (React + Tailwind, Vite)

**State model.** No routing library — `activeTab` is a plain `useState`
(`home` / `checklist` / `ready` / `profile`) that conditionally renders one
panel in `App.jsx`'s `<main>`. Two parallel message representations are kept
per chat turn: `history` (English-only, exactly what `intelligence.respond`
expects/returns) and `messages` (localized display text + audio + citations
+ error flag) — this split is what lets the AI layer stay language-agnostic
while the UI is fully localized.

**Voice input.** `MediaRecorder` records to a `webm` blob client-side;
uploaded as multipart form data to `/api/chat/voice`. Playback of the
reply's TTS audio is triggered directly off the same click/keypress that
sent the message — deliberately, since browsers only allow unprompted audio
autoplay when it's a direct result of a user gesture; anything more
"automatic" (e.g. an earlier hands-free auto-listen prototype) hit
inconsistent autoplay blocking and was reverted in favor of this simpler,
reliable click → reply → audio chain.

**Localization (`i18n.js`).** Two independent translation paths, on
purpose:
- *Chat replies* are translated live, per turn, by the backend (Sarvam) —
  dynamic content, translated dynamically.
- *UI chrome* (nav labels, button text, disclaimers, calculator copy) is a
  static hand-authored dictionary for 4 languages (Hindi, Telugu, Odia,
  English), looked up via `t(uiLang, key)`. Static content doesn't need a
  network round-trip to translate, and hand-authored strings can be reviewed
  for tone in a way that live machine translation of UI chrome can't.

Picking a language on the first screen sets both: the backend `language`
parameter for chat, and `uiLang` for every static string in the app. The
language keeps tracking whichever was actually detected turn-to-turn (e.g.
if a voice message comes in a different language than the one originally
picked), so the experience adapts rather than staying rigidly locked.

**Interactive tabs beyond chat:**
- **Document Checklist** — fetches the real document list from
  `/api/checklist/driving_license`, interactive checkboxes persisted in
  `localStorage` (no backend/account needed for a personal checklist).
- **"Am I Ready?"** — three genuinely functional, non-LLM tools:
  eligibility check (hardcoded Motor Vehicles Act age/vehicle-class rules,
  clearly disclaimed as general guidance), a fee estimator that asks for
  vehicle class(es) — supporting a multi-class application — and whether
  this is a fresh application vs. adding a class to an existing licence
  (different MoRTH fee lines apply), and a nearby-RTO finder that uses real
  browser geolocation to open an actual Google Maps search, no API key
  required.
- **Profile** — language switch (live, no page reload), a text-size
  accessibility toggle, checklist progress summary, and a full data reset.

---

## 5. Responsible-AI / Guardrail Layer

This isn't a separate module — it's a set of properties enforced jointly by
the data, RAG, and intelligence layers:

- **No hallucination on data gaps.** A service with `status:
  no_verified_data` is filtered out of scoring *before* retrieval runs
  (§2), not after — the LLM is never even shown a chance to guess. The
  fallback still ends with a real, verified link (§2/§3), so honesty never
  becomes a dead end for the user.
- **Scope enforcement by instruction, not keyword lists.** Earlier versions
  tried to hand-list "in-scope" keywords/deny-lists; that broke on anything
  phrased in a way nobody anticipated. The current system prompt instructs
  the model to reason about domain boundaries and refuse with one fixed,
  exact sentence — checked verbatim in code, not fuzzy-matched.
- **Citations/source tracking.** Every grounded reply carries
  `[source_file] chunk text` citations end-to-end from retrieval through the
  API response to the UI's "📚 Sources" expander — a user (or a developer)
  can always see exactly what the answer was grounded in.
- **Privacy by design, not by promise.** The floating assistant explicitly
  cannot see the user's screen and will ask which form field they mean
  rather than guess (§3); the "Open Official Portal" links launch with
  `noopener,noreferrer` so the government site never gets a window handle
  back; nothing is scraped, autofilled, or submitted on the user's behalf.
- **Disclaimers on non-verified-but-still-answered content.** General RTO
  knowledge the model answers from its own training (rather than the
  verified dataset) is explicitly flagged as such in the system prompt's
  instructions, and the eligibility/fee calculators (hardcoded, not
  LLM-generated) carry their own "confirm with your local RTO" disclaimers
  since fee schedules genuinely vary by state.
- **Graceful degradation over hard failure.** Translation, TTS, and STT
  failures each degrade to a narrower but still-useful response (§4) instead
  of a 500 or a silent crash.

---

## 6. Evals

**Location:** `eval/run_eval.py` + `eval/test_questions.json`

Two modes, chosen automatically by whether `SARVAM_API_KEY` is set:

**Retrieval-only** (always runs, no API key needed):
- **Service routing accuracy** — does the router assign the question to the
  right service?
- **Gap-handling accuracy** — do the two unverified services correctly come
  back `insufficient_evidence=True` instead of being answered?
- **Retrieval hit rate** — do the expected keywords actually show up in
  what got retrieved (checked against retrieved chunks *and* the injected
  process outline, matching what the LLM actually sees)?
- **Retrieval latency** — per-query timing.

**Full pipeline** (only if a key is set — this makes live Sarvam calls):
- **End-to-end latency**, broken into retrieval vs. LLM stages, to identify
  the actual bottleneck.
- **Groundedness / hallucination check** — for gap questions, does the reply
  literally match the safe fallback template? For answerable questions, does
  the reply's vocabulary meaningfully overlap with what it was actually
  given as context (a crude but automatic proxy for "didn't just make
  something up")?

This harness explicitly does **not** claim to prove answer correctness (that
needs human or LLM-judge review) — what it does verify automatically is that
routing is right, retrieval surfaces real evidence, gaps are reported
honestly instead of hallucinated, and latency stays low. Those are the parts
most likely to silently regress as the system evolves.

Run it:
```bash
python eval/run_eval.py
```

---

## Setup

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

Copy `.env.example` to `.env` and add your key:
```
SARVAM_API_KEY=your_actual_key_here
```
Loads automatically via `python-dotenv`; `.env` is git-ignored. No
OpenAI/Anthropic key needed — voice (STT/translate/TTS) and the LLM both run
through the single Sarvam key.

## Running

**Full app (recommended):**
```bash
python -m uvicorn backend.main:app --reload --port 8000   # terminal 1
cd frontend && npm run dev                                  # terminal 2
```
Opens at `http://localhost:5173` (proxies `/api/*` to the backend on 8000).

**Standalone Streamlit demo** (`app.py`) — a lighter single-file alternative
to the React frontend, talking to the same `intelligence.py`:
```bash
streamlit run app.py
```

**Sanity-check the Sarvam client in isolation:**
```bash
python sarvam_client.py
```

## Where to add real data

Drop a new/updated JSON file into `data/<service_id>/` following the shape
of `data/driving_license/dl_dataset.json` — no code changes needed; the
chunking layer (§2) picks up any file under `data/` automatically. To mark a
service's data as genuinely verified, update its `status` field and remove
the `no_verified_data` gap marker; the retrieval pipeline will start
scoring it like `driving_license` immediately.
