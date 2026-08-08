"""
The hybrid retrieval pipeline described in the Phase 1 brief:

    query -> service filter -> BM25 + semantic (concurrently, both are
    local/CPU so "concurrent" just means "cheap, not two network calls")
    -> RRF fusion -> lexical rerank -> confidence check -> result

Everything here is local computation (no network calls), so the entire
pipeline typically runs in single-digit milliseconds — the latency budget
is spent on STT/translate/LLM/TTS, not retrieval. See eval/run_eval.py for
measured numbers.
"""
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from . import index as _index
from .chunking import KNOWN_SERVICES, Chunk
from .fusion import reciprocal_rank_fusion
from .index import tokenize
from .rerank import rerank
from .router import detect_service

# Categories that represent actual verified step-by-step process knowledge.
# official_link and faq chunks are real and safe to cite, but they aren't
# "this service's process is documented" — a service with only an
# official_link chunk (see data/*/official_links.json) must still be
# treated as a data gap for full step-guidance purposes.
PROCESS_CATEGORIES = {"eligibility", "documents", "procedure", "forms"}

# Below this fused confidence, we don't trust the retrieval enough to let
# the model answer from it — the caller should fall back to the
# insufficient-evidence response instead of guessing.
CONFIDENCE_FLOOR = 0.05


@dataclass
class RetrievalResult:
    query: str
    service_id: Optional[str]
    service_display_name: str
    service_has_verified_data: bool
    chunks: List[Chunk]
    confidence: float
    insufficient_evidence: bool


def _candidate_indices(chunks: List[Chunk], service_id: Optional[str]) -> List[int]:
    if service_id is None:
        return list(range(len(chunks)))
    return [i for i, c in enumerate(chunks) if c.service_id in (service_id, "general")]


def _has_verified_process_data(chunks: List[Chunk], service_id: str) -> bool:
    return any(c.verified and c.category in PROCESS_CATEGORIES
               for c in chunks if c.service_id == service_id)


def retrieve(query: str, service_id: Optional[str] = None, top_k: int = 4) -> RetrievalResult:
    chunks, bm25, tfidf, svd, svd_matrix = _index.get_index()

    explicit_service = service_id is not None
    if service_id is None:
        service_id = detect_service(query)
    display_name = KNOWN_SERVICES.get(service_id, service_id or "general RTO")

    if not chunks:
        return RetrievalResult(query, service_id, display_name, False, [], 0.0, True)

    candidates = _candidate_indices(chunks, service_id)
    service_has_verified_data = _has_verified_process_data(chunks, service_id) if service_id else True

    if not candidates:
        return RetrievalResult(query, service_id, display_name, service_has_verified_data, [], 0.0, True)

    # A query pinned (by the router) to a known service that has no
    # verified dataset yet (vehicle_transfer / vehicle_registration today)
    # must never be answered from unrelated general/FAQ chunks that happen
    # to share vocabulary — that's exactly the "irrelevant info from one
    # service dominating another's answer" the brief warns against. Skip
    # scoring entirely: fast path, and correctness over guessing.
    if service_id in KNOWN_SERVICES and not service_has_verified_data:
        return RetrievalResult(query, service_id, display_name, False, [], 0.0, True)

    # --- keyword retrieval (BM25) ---
    tokenized_query = tokenize(query)
    bm25_scores = bm25.get_scores(tokenized_query)
    bm25_ranked = sorted(candidates, key=lambda i: bm25_scores[i], reverse=True)

    # --- semantic retrieval (TF-IDF -> LSA cosine) ---
    q_tfidf = tfidf.transform([query])
    q_svd = svd.transform(q_tfidf)[0]
    q_norm = np.linalg.norm(q_svd) or 1e-9
    cand_matrix = svd_matrix[candidates]
    cand_norms = np.linalg.norm(cand_matrix, axis=1)
    cand_norms[cand_norms == 0] = 1e-9
    sem_scores_subset = (cand_matrix @ q_svd) / (cand_norms * q_norm)
    sem_order = np.argsort(sem_scores_subset)[::-1]
    semantic_ranked = [candidates[i] for i in sem_order]

    # --- fusion ---
    fused = reciprocal_rank_fusion([bm25_ranked, semantic_ranked])

    # Never let an unverified "data gap" chunk act as grounding evidence,
    # but keep it around long enough to know a gap file was the only hit.
    verified_fused = [i for i in fused if chunks[i].verified]

    top_bm25 = max((bm25_scores[i] for i in candidates), default=0.0)
    top_sem = float(np.max(sem_scores_subset)) if len(sem_scores_subset) else 0.0
    # crude but serviceable normalized confidence: keyword score has no
    # fixed ceiling, so squash it; semantic cosine is already 0..1.
    confidence = max(min(top_bm25 / (top_bm25 + 5.0), 1.0), top_sem)

    if not verified_fused:
        return RetrievalResult(query, service_id, display_name, service_has_verified_data, [], confidence, True)

    candidate_chunks = [chunks[i] for i in verified_fused[: max(top_k * 3, top_k)]]
    final_chunks = rerank(query, candidate_chunks, top_k)

    # Fallback routing: the keyword router found no stem match, but retrieval
    # ran unrestricted across all services anyway (service_id was None), so
    # there's no extra cost to inferring the service from whichever service's
    # chunk actually won the fused+reranked ranking — cheap because it reuses
    # work already done, and safe because only *verified* chunks reach this
    # point (a data-gap service can never be inferred as the answer source).
    if not explicit_service and service_id is None and final_chunks:
        top_service = final_chunks[0].service_id
        if top_service != "general":
            service_id = top_service
            display_name = KNOWN_SERVICES.get(service_id, service_id)
            service_has_verified_data = _has_verified_process_data(chunks, service_id)

    insufficient = confidence < CONFIDENCE_FLOOR or not final_chunks
    return RetrievalResult(query, service_id, display_name, service_has_verified_data, final_chunks, confidence, insufficient)
