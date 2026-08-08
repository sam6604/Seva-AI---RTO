"""
Phase 2 additions on top of the Phase 1 retrieval pipeline (pipeline.py is
untouched in spirit — this module only adds two things intelligence.py can
optionally pull in, it doesn't change how retrieve() scores or filters):

1. get_process_outline(service_id) — the COMPLETE ordered step sequence
   (with docs/fields) for a service that has verified data, formatted for
   prompt injection. Phase 1's retrieve() only returns top-k *fragments* of
   the process, which is enough for single-fact Q&A but not enough for the
   model to reliably say "you're on step 2 of 4, here's what's next" across
   a multi-turn conversation — it needs the whole sequence in view. This is
   intentionally NOT a hand-coded step tracker; the LLM still decides where
   the user is from conversation history, same as Phase 1's DL flow — this
   just gives it the complete map instead of scattered fragments.

2. get_official_links(service_id) — direct, ungated lookup of the verified
   official portal link(s) for a service. Used two ways: (a) attached to
   the context for services that DO have process data, so "what do I do
   next" answers can end with a concrete link; (b) attached to the
   insufficient-evidence fallback for services that DON'T have verified
   process data yet (vehicle_transfer / vehicle_registration today), so
   "I don't have verified steps for this" isn't a dead end — the user still
   gets pointed to the real place to start, without any procedure being
   invented.
"""
from typing import List, Optional

from . import index as _index
from .chunking import Chunk


def get_official_links(service_id: Optional[str]) -> List[Chunk]:
    if not service_id:
        return []
    chunks, *_ = _index.get_index()
    return [c for c in chunks if c.service_id == service_id and c.category == "official_link"]


def format_official_links(service_id: Optional[str]) -> Optional[str]:
    links = get_official_links(service_id)
    if not links:
        return None
    return "\n".join(f"- {c.text}" for c in links)


def get_process_outline(service_id: Optional[str]) -> Optional[str]:
    """
    Returns a compact, ordered, numbered outline of the full process for
    `service_id`, or None if that service has no verified step data (the
    caller should rely on the normal retrieve()/insufficient-evidence path
    instead — this function never fabricates a process).
    """
    if not service_id:
        return None
    chunks, *_ = _index.get_index()
    service_chunks = [c for c in chunks if c.service_id == service_id]
    if not any(c.verified and c.category in ("eligibility", "documents", "procedure", "forms")
               for c in service_chunks):
        return None

    lines = []
    prereqs = [c for c in service_chunks if c.category == "eligibility"]
    if prereqs:
        lines.append("Prerequisites to check first:")
        lines.extend(f"  - {c.text}" for c in prereqs)

    # Steps are naturally ordered by how they were chunked from the dataset
    # (dataset order == real-world order); documents/procedure/forms chunks
    # for the same step share the same "{source}:step{idx}" id prefix, so
    # grouping by that prefix reconstructs step order without re-parsing
    # the raw JSON here.
    step_groups: "dict[str, list[Chunk]]" = {}
    for c in service_chunks:
        if c.category in ("documents", "procedure", "forms"):
            key = c.id.rsplit(":", 1)[0]  # "{source}:step{idx}"
            step_groups.setdefault(key, []).append(c)

    for i, (_key, group) in enumerate(
        sorted(step_groups.items(), key=lambda kv: int(kv[0].rsplit("step", 1)[-1])), start=1
    ):
        lines.append(f"Step {i}:")
        lines.extend(f"  - {c.text}" for c in group)

    return "\n".join(lines) if lines else None
