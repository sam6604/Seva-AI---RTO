import json
from pathlib import Path
from typing import Any, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

DATA_DIR = Path(__file__).parent / "data"


def load_dataset(service_id: str) -> dict:
    """
    SWAP POINT: replace this function body when the real Data module JSON
    is ready — signature must not change.

    Reads data/dl_dataset.json.
    """
    path = DATA_DIR / "dl_dataset.json"
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_to_chunks(obj: Any) -> List[str]:
    """
    Generic JSON -> text-chunk flattening for RAG, so any file dropped into
    data/ (FAQ lists, the DL dataset, or a new schema entirely) is indexable
    without writing per-format parsing code.
    """
    chunks = []
    if isinstance(obj, dict):
        scalars = {k: v for k, v in obj.items() if isinstance(v, (str, int, float))}
        if scalars:
            chunks.append(" | ".join(f"{k}: {v}" for k, v in scalars.items()))
        for v in obj.values():
            if isinstance(v, (dict, list)):
                chunks.extend(_flatten_to_chunks(v))
    elif isinstance(obj, list):
        for item in obj:
            chunks.extend(_flatten_to_chunks(item))
    return chunks


def _all_chunks() -> List[str]:
    chunks = []
    for path in DATA_DIR.glob("*.json"):
        chunks.extend(_flatten_to_chunks(json.loads(path.read_text(encoding="utf-8"))))
    return chunks


def get_relevant_context(query: str, service_id: str, top_k: int = 3) -> List[str]:
    """
    Return top_k matching text chunks from every JSON file in data/, using
    TF-IDF overlap. Intentionally simple — no FAISS/embeddings needed for
    this dataset size.
    """
    corpus = _all_chunks()
    if not corpus:
        return []

    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(corpus + [query])
    scores = (matrix[:-1] @ matrix[-1].T).toarray().ravel()

    top_idx = np.argsort(scores)[::-1][:top_k]
    return [corpus[i] for i in top_idx if scores[i] > 0]
