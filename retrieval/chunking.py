"""
Turns the JSON files under data/ into metadata-tagged text chunks for
retrieval. Unlike the old flat `_flatten_to_chunks` (which just walked any
JSON blob into strings with no idea which service or category it belonged
to), this keeps track of:

- service_id   — which of the 3 RTO services the chunk belongs to
                 ("general" for cross-cutting FAQ content that isn't
                 specific to one service and should never be filtered out)
- category     — eligibility / documents / procedure / forms / faq / gap
- verified     — False for the vehicle_transfer / vehicle_registration
                 placeholder files (see the data-gap note in those files).
                 A chunk with verified=False must never be treated as
                 grounding evidence for an answer.
- source       — human-readable reference so replies can cite where the
                 fact came from (required by the "source/reference
                 tracking" requirement).

Directory layout convention (data/<service_id>/*.json), so adding a new
RTO service later is just "make a new folder + JSON files" — no code
changes needed here, which is what keeps this modular.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Known services today. New services just need a data/<service_id>/ folder;
# they don't need to be listed here — this is only used as a display-name
# fallback and for the service router's keyword list (see router.py).
KNOWN_SERVICES = {
    "driving_license": "Driving Licence",
    "vehicle_transfer": "Vehicle Ownership Transfer",
    "vehicle_registration": "Vehicle Registration",
}


@dataclass
class Chunk:
    id: str
    text: str
    service_id: str
    category: str
    source: str
    verified: bool = True


def _docs_chunks(step: dict, service_id: str, source: str, idx: int) -> List[Chunk]:
    out = []
    docs = step.get("docs_needed")
    if docs:
        out.append(Chunk(
            id=f"{source}:step{idx}:docs",
            text=f"{step.get('step_name', 'step')}: required documents — {', '.join(docs)}",
            service_id=service_id, category="documents", source=source,
        ))
    if step.get("narration_template") or step.get("time_estimate"):
        parts = [step.get("step_name", "step")]
        if step.get("time_estimate"):
            parts.append(f"takes about {step['time_estimate']}")
        if step.get("narration_template"):
            parts.append(step["narration_template"])
        out.append(Chunk(
            id=f"{source}:step{idx}:proc",
            text=" | ".join(parts),
            service_id=service_id, category="procedure", source=source,
        ))
    for fi, f in enumerate(step.get("fields", [])):
        out.append(Chunk(
            id=f"{source}:step{idx}:field{fi}",
            text=f"Form field '{f.get('field_label')}' ({f.get('position_hint', '')}): {f.get('narration', '')}",
            service_id=service_id, category="forms", source=source,
        ))
    return out


def _service_dataset_chunks(obj: dict, service_id: str, source: str) -> List[Chunk]:
    if obj.get("status") == "no_verified_data":
        # Gap placeholder — keep exactly one chunk so the router/pipeline can
        # detect "this service exists but has no verified data", but flag it
        # unverified so it's never used as grounding evidence.
        return [Chunk(
            id=f"{source}:gap",
            text=obj.get("note", f"No verified data yet for {service_id}."),
            service_id=service_id, category="gap", source=source, verified=False,
        )]

    chunks: List[Chunk] = []
    for q in obj.get("prereq_questions", []):
        text = f"Eligibility/prerequisite question: {q.get('question')}"
        if q.get("options"):
            text += f" (options: {', '.join(q['options'])})"
        chunks.append(Chunk(id=f"{source}:prereq:{q.get('id')}", text=text,
                             service_id=service_id, category="eligibility", source=source))
    for idx, step in enumerate(obj.get("steps", [])):
        chunks.extend(_docs_chunks(step, service_id, source, idx))
    return chunks


def _faq_chunks(obj, source: str) -> List[Chunk]:
    chunks = []
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, dict) and "q" in item and "a" in item:
                chunks.append(Chunk(
                    id=f"{source}:{i}",
                    text=f"Q: {item['q']} A: {item['a']}",
                    service_id="general", category="faq", source=source,
                ))
    return chunks


def load_all_chunks() -> List[Chunk]:
    import json
    chunks: List[Chunk] = []

    for service_dir in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        service_id = service_dir.name
        for path in sorted(service_dir.glob("*.json")):
            obj = json.loads(path.read_text(encoding="utf-8"))
            source = f"{service_dir.name}/{path.name}"
            chunks.extend(_service_dataset_chunks(obj, service_id, source))

    for path in sorted(DATA_DIR.glob("*.json")):
        obj = json.loads(path.read_text(encoding="utf-8"))
        chunks.extend(_faq_chunks(obj, path.name))

    return chunks
