"""
Reranking stage. Deliberately a cheap lexical re-score, not a cross-encoder
API call: for a corpus this small (dozens of chunks, not millions), an
extra network round-trip to a reranking API would be the single biggest
latency cost in the whole pipeline for close to no accuracy gain.

Candidates arrive already ordered by RRF fusion (see fusion.py), which
already blends keyword + semantic signal — this stage nudges that order
using cheap signals (exact phrase containment, content-word overlap), it
doesn't replace it. Scoring purely from scratch here previously let common
English words ("driving", "license", "a", "for") in an unrelated FAQ chunk
outrank the actually-relevant chunk that fusion had ranked higher, so the
fused position is the dominant term and the lexical signal is a small
tie-breaking nudge on top of it.
"""
from typing import List

from .chunking import Chunk
from .index import tokenize

_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "did", "i", "my", "me",
    "for", "to", "of", "in", "on", "and", "or", "what", "how", "when",
    "where", "which", "who", "need", "want", "get", "can", "you", "your",
    "this", "that", "it", "be", "am", "was", "were",
}


def rerank(query: str, fused_candidates: List[Chunk], top_k: int) -> List[Chunk]:
    """`fused_candidates` must already be in fusion rank order (best first)."""
    q_tokens = tokenize(query)
    q = " ".join(q_tokens)
    q_words = {w for w in q_tokens if w not in _STOPWORDS and len(w) > 2}

    def score(rank: int, c: Chunk) -> float:
        text = " ".join(tokenize(c.text))
        s = 1.0 / (rank + 1)  # dominant term: preserve the fused ordering
        if q in text:
            s += 0.5  # exact phrase containment, small nudge
        content_words = {w for w in tokenize(c.text) if w not in _STOPWORDS and len(w) > 2}
        overlap = len(q_words & content_words)
        s += overlap * 0.02
        if not c.verified:
            s -= 100.0  # never let an unverified/gap chunk float to the top
        return s

    scored = [(score(rank, c), c) for rank, c in enumerate(fused_candidates)]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:top_k]]
