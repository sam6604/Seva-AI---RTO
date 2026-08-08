"""
Builds the keyword (BM25) and semantic (TF-IDF -> LSA) indices once and
caches them at module level. This is the "reuse of precomputed
embeddings / avoid duplicate work" piece of the latency requirement: the
corpus is small and static (JSON files on disk), so there's no reason to
re-tokenize or re-fit anything on every request.

Call `refresh()` if data/ changes at runtime (not needed for the hackathon
demo, but keeps this honest for a long-running server).
"""
from threading import Lock
from typing import List

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from .chunking import Chunk, load_all_chunks

_lock = Lock()
_built = False
_chunks: List[Chunk] = []
_bm25: BM25Okapi | None = None
_tfidf: TfidfVectorizer | None = None
_svd: TruncatedSVD | None = None
_svd_matrix = None  # (n_chunks, n_components) dense LSA embedding matrix


def _tokenize(text: str) -> List[str]:
    return text.lower().split()


def _build():
    global _chunks, _bm25, _tfidf, _svd, _svd_matrix, _built
    _chunks = load_all_chunks()
    _built = True

    if not _chunks:
        _bm25, _tfidf, _svd, _svd_matrix = None, None, None, None
        return

    tokenized = [_tokenize(c.text) for c in _chunks]
    _bm25 = BM25Okapi(tokenized)

    _tfidf = TfidfVectorizer(stop_words="english")
    tfidf_matrix = _tfidf.fit_transform([c.text for c in _chunks])

    # LSA (TF-IDF + SVD) as the "semantic" retriever: it groups
    # co-occurring terms into latent topics, so it can match paraphrases
    # and related vocabulary that plain keyword overlap misses, without
    # needing a downloaded embedding model (no network access to a model
    # hub at runtime, and this keeps the stack unchanged — sklearn is
    # already a dependency). n_components is capped to the corpus size.
    n_components = max(1, min(64, tfidf_matrix.shape[1] - 1, tfidf_matrix.shape[0] - 1))
    _svd = TruncatedSVD(n_components=n_components, random_state=0)
    _svd_matrix = _svd.fit_transform(tfidf_matrix)


def get_index():
    """Returns (chunks, bm25, tfidf_vectorizer, svd, svd_matrix), building on first call."""
    with _lock:
        if not _built:
            _build()
    return _chunks, _bm25, _tfidf, _svd, _svd_matrix


def refresh():
    with _lock:
        _build()
