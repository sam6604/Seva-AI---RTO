"""Reciprocal Rank Fusion (RRF) — combines two or more ranked lists of chunk
indices into one fused ranking without needing the raw scores to be on
comparable scales (BM25 scores and cosine-similarity scores aren't)."""
from typing import Dict, List

RRF_K = 60  # standard RRF constant; de-emphasizes rank-1 dominance from a single retriever


def reciprocal_rank_fusion(ranked_lists: List[List[int]]) -> List[int]:
    """Each input is a list of chunk indices in rank order (best first).
    Returns a single fused list of indices, best first."""
    scores: Dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, idx in enumerate(ranked):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)
