from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from .state import (
    empty_reference_patch,
    empty_summary_patch,
    merge_reference_profile,
    new_reference_profile,
    new_story_state,
)

PROGRESS_VERSION = 4


def make_batch_key(batch_index: int) -> str:
    return f"batch_{batch_index:04d}"


def _new_reference_phase(
    reference_book: Optional[Dict[str, str]],
    target_language: str,
    enabled: bool,
) -> Dict[str, Any]:
    return {
        "status": "pending" if enabled else "disabled",
        "completed_count": 0,
        "total_document_count": 0,
        "reference_profile": new_reference_profile(reference_book, target_language),
    }


def _new_summary_phase(book_metadata: Dict[str, str]) -> Dict[str, Any]:
    story_state = new_story_state(book_metadata)
    return {
        "status": "pending",
        "completed_count": 0,
        "story_state": story_state,
    }


def _new_translation_phase() -> Dict[str, Any]:
    return {
        "status": "pending",
        "completed_document_count": 0,
        "completed_batch_count": 0,
        "total_batch_count": 0,
    }


def _normalize_translated_batches(value: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(value, dict):
        normalized: Dict[str, Dict[str, Any]] = {}
        for key, entry in value.items():
            if not isinstance(entry, dict):
                continue
            batch_index = int(entry.get("batch_index") or 0)
            if batch_index <= 0:
                match = re.search(r"(\d+)$", str(key))
                batch_index = int(match.group(1)) if match else 0
            if batch_index <= 0:
                continue
            normalized[make_batch_key(batch_index)] = {
                "batch_index": batch_index,
                "translations": dict(entry.get("translations") or {}),
                "review": dict(entry.get("review") or {}),
            }
        return normalized

    if isinstance(value, list):
        normalized = {}
        for entry in value:
            if not isinstance(entry, dict):
                continue
            batch_index = int(entry.get("batch_index") or 0)
            if batch_index <= 0:
                continue
            normalized[make_batch_key(batch_index)] = {
                "batch_index": batch_index,
                "translations": dict(entry.get("translations") or {}),
                "review": dict(entry.get("review") or {}),
            }
        return normalized

    return {}


def _normalize_document_record(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(record or {})
    normalized.setdefault("file_name", "")
    normalized.setdefault("item_id", "")
    normalized.setdefault("source_hash", "")
    normalized["segment_count"] = int(normalized.get("segment_count", 0) or 0)
    normalized["batch_count"] = int(normalized.get("batch_count", 0) or 0)
    normalized.setdefault("summary_status", "pending")
    normalized["summary_patch"] = dict(normalized.get("summary_patch") or empty_summary_patch())
    normalized["translation_context_snapshot"] = dict(normalized.get("translation_context_snapshot") or {})
    normalized.setdefault("translation_status", "pending")
    normalized["translated_batches"] = _normalize_translated_batches(normalized.get("translated_batches"))
    normalized["translated_html"] = str(normalized.get("translated_html") or "")
    normalized["reviews"] = list(normalized.get("reviews") or [])

    if normalized.get("status") == "done" and normalized["translated_html"]:
        normalized["translation_status"] = "done"

    return normalized


def _can_omit_translated_html(record: Dict[str, Any]) -> bool:
    translated_html = str(record.get("translated_html") or "")
    if not translated_html:
        return False

    segment_count = int(record.get("segment_count", 0) or 0)
    batch_count = int(record.get("batch_count", 0) or 0)
    if segment_count == 0:
        return True
    if batch_count <= 0:
        return False

    translated_batches = _normalize_translated_batches(record.get("translated_batches"))
    completed_batches = 0
    for entry in translated_batches.values():
        batch_index = int(entry.get("batch_index", 0) or 0)
        if (
            1 <= batch_index <= batch_count
            and isinstance(entry.get("translations"), dict)
            and entry.get("translations")
        ):
            completed_batches += 1
    return completed_batches >= batch_count


def _lightweight_progress_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    light_payload = dict(payload)
    documents = payload.get("documents", {}) or {}
    light_documents: Dict[str, Dict[str, Any]] = {}
    for file_name, record in documents.items():
        if not isinstance(record, dict):
            continue
        light_record = dict(record)
        if _can_omit_translated_html(light_record):
            light_record["translated_html"] = ""
        light_documents[str(file_name)] = light_record
    light_payload["documents"] = light_documents
    return light_payload


def _normalize_reference_document_record(record: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(record or {})
    normalized.setdefault("file_name", "")
    normalized.setdefault("item_id", "")
    normalized.setdefault("source_hash", "")
    normalized["segment_count"] = int(normalized.get("segment_count", 0) or 0)
    normalized.setdefault("status", "pending")
    normalized["patch"] = dict(normalized.get("patch") or empty_reference_patch())
    return normalized


def _recompute_phase_counts(progress: Dict[str, Any]) -> None:
    reference_documents = progress.get("reference_documents", {}) or {}
    reference_completed = 0
    reference_total = 0
    for record in reference_documents.values():
        if not isinstance(record, dict):
            continue
        reference_total += 1
        if record.get("status") == "done":
            reference_completed += 1

    documents = progress.get("documents", {}) or {}
    summary_completed = 0
    translation_completed_documents = 0
    translation_completed_batches = 0
    translation_total_batches = 0

    for record in documents.values():
        if not isinstance(record, dict):
            continue
        batch_count = int(record.get("batch_count", 0) or 0)
        translation_total_batches += batch_count

        if record.get("summary_status") == "done":
            summary_completed += 1

        translated_batches = _normalize_translated_batches(record.get("translated_batches"))
        if record.get("translation_status") == "done":
            translation_completed_documents += 1
            translation_completed_batches += batch_count
            continue

        translation_completed_batches += min(batch_count, len(translated_batches))

    reference_phase = progress.setdefault("reference_phase", {})
    summary_phase = progress.setdefault("summary_phase", {})
    translation_phase = progress.setdefault("translation_phase", {})
    reference_phase["completed_count"] = reference_completed
    reference_phase["total_document_count"] = reference_total
    summary_phase["completed_count"] = summary_completed
    translation_phase["completed_document_count"] = translation_completed_documents
    translation_phase["completed_batch_count"] = translation_completed_batches
    translation_phase["total_batch_count"] = translation_total_batches


def _migrate_progress_document(progress: Dict[str, Any]) -> Dict[str, Any]:
    book_metadata = dict(progress.get("book") or {})
    target_language = str(progress.get("target_language") or "")
    reference_input_path = str(progress.get("reference_input_path") or "")
    reference_fingerprint = str(progress.get("reference_fingerprint") or "")
    reference_book = dict(progress.get("reference_book") or {})
    reference_enabled = bool(progress.get("reference_enabled"))
    if reference_input_path or reference_fingerprint or reference_book:
        reference_enabled = True

    reference_phase = dict(progress.get("reference_phase") or {})
    summary_phase = dict(progress.get("summary_phase") or {})
    translation_phase = dict(progress.get("translation_phase") or {})
    story_state = dict(summary_phase.get("story_state") or progress.get("story_state") or new_story_state(book_metadata))

    migrated = {
        "version": PROGRESS_VERSION,
        "input_path": progress.get("input_path", ""),
        "output_path": progress.get("output_path", ""),
        "source_language": progress.get("source_language", ""),
        "target_language": target_language,
        "book": book_metadata,
        "reference_enabled": reference_enabled,
        "reference_input_path": reference_input_path,
        "reference_fingerprint": reference_fingerprint,
        "reference_book": reference_book,
        "assistant_fingerprint": str(progress.get("assistant_fingerprint") or ""),
        "story_state": story_state,
        "reference_phase": _new_reference_phase(reference_book, target_language, reference_enabled),
        "summary_phase": _new_summary_phase(book_metadata),
        "translation_phase": _new_translation_phase(),
        "reference_documents": {},
        "documents": {},
    }

    migrated["reference_phase"].update(reference_phase)
    migrated["summary_phase"].update(summary_phase)
    migrated["summary_phase"]["story_state"] = story_state
    migrated["translation_phase"].update(translation_phase)
    migrated["reference_phase"]["reference_profile"] = merge_reference_profile(
        new_reference_profile(reference_book, target_language),
        migrated["reference_phase"].get("reference_profile") or {},
    )

    if reference_enabled:
        migrated["reference_phase"]["status"] = str(migrated["reference_phase"].get("status") or "pending")
    else:
        migrated["reference_phase"]["status"] = "disabled"
        migrated["reference_phase"]["completed_count"] = 0
        migrated["reference_phase"]["total_document_count"] = 0
        migrated["reference_phase"]["reference_profile"] = new_reference_profile({}, target_language)

    reference_documents = progress.get("reference_documents", {}) or {}
    for file_name, record in reference_documents.items():
        normalized = _normalize_reference_document_record(record)
        normalized["file_name"] = normalized.get("file_name") or str(file_name)
        migrated["reference_documents"][normalized["file_name"]] = normalized

    documents = progress.get("documents", {}) or {}
    for file_name, record in documents.items():
        normalized = _normalize_document_record(record)
        normalized["file_name"] = normalized.get("file_name") or str(file_name)
        migrated["documents"][normalized["file_name"]] = normalized

    _recompute_phase_counts(migrated)
    return migrated


def load_progress(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return _migrate_progress_document(payload)


def create_progress_document(
    input_path: Path,
    output_path: Path,
    source_language: str,
    target_language: str,
    book_metadata: Dict[str, str],
    *,
    reference_enabled: bool = False,
    reference_input_path: Optional[Path] = None,
    reference_fingerprint: str = "",
    reference_book: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    summary_phase = _new_summary_phase(book_metadata)
    normalized_reference_book = dict(reference_book or {})
    return {
        "version": PROGRESS_VERSION,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "source_language": source_language,
        "target_language": target_language,
        "book": book_metadata,
        "reference_enabled": bool(reference_enabled),
        "reference_input_path": str(reference_input_path) if reference_input_path else "",
        "reference_fingerprint": str(reference_fingerprint or ""),
        "reference_book": normalized_reference_book,
        "story_state": copy.deepcopy(summary_phase["story_state"]),
        "reference_phase": _new_reference_phase(normalized_reference_book, target_language, bool(reference_enabled)),
        "summary_phase": summary_phase,
        "translation_phase": _new_translation_phase(),
        "reference_documents": {},
        "documents": {},
    }


def save_progress(path: Path, payload: Dict[str, Any]) -> None:
    normalized = _migrate_progress_document(_lightweight_progress_payload(payload))
    normalized["version"] = PROGRESS_VERSION
    normalized["story_state"] = copy.deepcopy(normalized["summary_phase"]["story_state"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)


def get_reference_document_record(progress: Dict[str, Any], file_name: str) -> Optional[Dict[str, Any]]:
    record = progress.get("reference_documents", {}).get(file_name)
    if not isinstance(record, dict):
        return None
    normalized = _normalize_reference_document_record(record)
    progress.setdefault("reference_documents", {})[file_name] = normalized
    return normalized


def upsert_reference_document_record(progress: Dict[str, Any], record: Dict[str, Any]) -> None:
    normalized = _normalize_reference_document_record(record)
    progress.setdefault("reference_documents", {})[normalized["file_name"]] = normalized
    _recompute_phase_counts(progress)


def get_document_record(progress: Dict[str, Any], file_name: str) -> Optional[Dict[str, Any]]:
    record = progress.get("documents", {}).get(file_name)
    if not isinstance(record, dict):
        return None
    normalized = _normalize_document_record(record)
    progress.setdefault("documents", {})[file_name] = normalized
    return normalized


def upsert_document_record(progress: Dict[str, Any], record: Dict[str, Any]) -> None:
    normalized = _normalize_document_record(record)
    progress.setdefault("documents", {})[normalized["file_name"]] = normalized
    _recompute_phase_counts(progress)
