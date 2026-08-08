import json
from pathlib import Path
from typing import List, Optional

from retrieval import retrieve

DATA_DIR = Path(__file__).parent / "data"


def load_dataset(service_id: str) -> dict:
    """
    SWAP POINT: replace this function body when the real Data module JSON
    is ready — signature must not change.

    Reads data/<service_id>/dl_dataset.json (driving_license today; the
    other two services don't have a real dataset yet — see the data-gap
    note in data/vehicle_transfer/dataset.json and
    data/vehicle_registration/dataset.json).
    """
    path = DATA_DIR / "driving_license" / "dl_dataset.json"
    if service_id != "driving_license":
        path = DATA_DIR / service_id / "dataset.json"
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_relevant_context(query: str, service_id: Optional[str] = None, top_k: int = 3) -> List[str]:
    """
    Backward-compatible wrapper around the Phase 1 hybrid RAG pipeline
    (retrieval/pipeline.py): service-aware BM25 + semantic retrieval, RRF
    fusion, and reranking, filtered down to plain text strings the way the
    original TF-IDF-only version returned them.

    `service_id=None` lets the pipeline auto-detect the service from the
    query itself instead of the caller having to know it in advance.
    Prefer calling `retrieval.retrieve()` directly (via intelligence.py) if
    you need the confidence score, source refs, or the "no verified data"
    flag — this wrapper only exists for any older caller that just wants
    text chunks.
    """
    result = retrieve(query, service_id=service_id, top_k=top_k)
    return [c.text for c in result.chunks]
