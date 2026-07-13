#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

SENSITIVE_TERMS = (
    "恋情", "离婚", "出轨", "隐私", "去世", "逝世", "病逝", "离世", "死亡", "死讯",
    "伤亡", "受伤", "被捕", "逮捕", "起诉", "指控", "控告", "违法", "犯罪", "未成年人",
    "relationship", "divorce", "affair", "privacy", "death", "dead", "died", "dies",
    "passed away", "obituary", "tribute", "injury", "injured", "arrest", "arrested",
    "lawsuit", "sued", "accused", "accusation", "allegation", "crime", "criminal", "minor"
)


def load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    json.loads(tmp.read_text("utf-8"))
    tmp.replace(path)


def event_text(event: dict[str, Any], source_records: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = [
        str(event.get("topic", "")),
        str(event.get("summary", "")),
        str(event.get("content", {}).get("overview", "")),
    ]
    parts.extend(str(value) for value in event.get("content", {}).get("key_points", []))
    for fact in event.get("facts", []):
        parts.append(str(fact.get("statement", "")))
    for source in event.get("sources", []):
        content = source.get("content", {})
        parts.append(str(content.get("summary", "")))
        parts.append(str(content.get("excerpt", "")))
        parts.append(str(content.get("text", "")))
    for source_id in event.get("source_ids", []):
        record = source_records.get(source_id, {})
        content = record.get("content", {})
        parts.append(str(record.get("title", "")))
        parts.append(str(content.get("summary", "")))
        parts.append(str(content.get("excerpt", "")))
        parts.append(str(content.get("text", "")))
        parts.extend(str(value) for value in content.get("key_facts", []))
    return re.sub(r"\s+", " ", " ".join(parts)).lower()


def sensitive_matches(text: str) -> list[str]:
    return sorted({term for term in SENSITIVE_TERMS if term.lower() in text})


def sufficiently_verified(event: dict[str, Any]) -> bool:
    verification = event.get("verification", {})
    status = verification.get("status")
    official_sources = verification.get("official_source_ids") or []
    independent_sources = int(event.get("heat_signals", {}).get("independent_source_count", 0) or 0)
    if status == "official" and official_sources:
        return True
    if status == "confirmed" and (official_sources or independent_sources >= 2):
        return True
    return False


def publisher(event: dict[str, Any]) -> str:
    sources = event.get("sources") or []
    if sources and sources[0].get("platform"):
        return str(sources[0]["platform"])
    organizations = event.get("entities", {}).get("organizations") or []
    return str(organizations[0]) if organizations else "unknown"


def main() -> int:
    latest = load(DATA / "latest.json", {})
    source_store = load(DATA / "sources.json", {})
    status = load(DATA / "status.json", {})
    if not latest or not source_store or not status:
        raise SystemExit("missing quality-gated collector output")

    source_records = {
        record["source_id"]: record
        for record in source_store.get("records", [])
        if record.get("source_id")
    }
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for event in latest.get("items", []):
        matches = sensitive_matches(event_text(event, source_records))
        if matches and not sufficiently_verified(event):
            rejected.append({
                "id": event.get("id"),
                "topic": event.get("topic"),
                "matched_terms": matches,
                "verification_status": event.get("verification", {}).get("status"),
                "independent_source_count": event.get("heat_signals", {}).get("independent_source_count", 0),
            })
            continue
        accepted.append(event)

    accepted_source_ids = {source_id for event in accepted for source_id in event.get("source_ids", [])}
    retained_records = [
        record for record in source_store.get("records", [])
        if record.get("source_id") in accepted_source_ids
    ]

    publishers = Counter(publisher(event) for event in accepted)
    distinct_publishers = len(publishers)
    max_share = max(publishers.values(), default=0) / max(len(accepted), 1)
    publishable_facts = sum(
        1 for event in accepted for fact in event.get("facts", [])
        if fact.get("can_use_as_fact")
    )
    ready = (
        len(accepted) >= 5
        and distinct_publishers >= 3
        and publishable_facts >= 3
        and max_share <= 0.45
    )
    partial = (
        len(accepted) >= 3
        and distinct_publishers >= 2
        and publishable_facts >= 2
        and max_share <= 0.67
    )
    if not (ready or partial):
        print(json.dumps({
            "kept": len(accepted),
            "removed_sensitive": len(rejected),
            "rejected": rejected,
        }, ensure_ascii=False, indent=2))
        raise SystemExit("sensitive evidence gate left no publishable feed")

    feed_map = {
        "all": ("latest.json", lambda event: True),
        "drama": ("drama.json", lambda event: event.get("category") == "drama"),
        "variety": ("variety.json", lambda event: event.get("category") == "variety"),
        "celebrity": ("celebrity.json", lambda event: event.get("category") == "celebrity"),
        "entertainment-events": (
            "entertainment-events.json",
            lambda event: event.get("category") == "entertainment_event",
        ),
    }
    for feed_name, (filename, predicate) in feed_map.items():
        payload = dict(latest)
        payload["feed"] = feed_name
        payload["items"] = [event for event in accepted if predicate(event)]
        save(DATA / filename, payload)

    source_store["records"] = retained_records
    save(DATA / "sources.json", source_store)

    overall = "ready" if ready else "partial"
    mode = "full" if ready else "attributed_only"
    status["status"] = overall
    status["publishability"] = {
        "can_publish": True,
        "mode": mode,
        "publishable_event_count": len(accepted),
        "publishable_fact_count": publishable_facts,
        "distinct_publisher_count": distinct_publishers,
        "max_single_publisher_share": round(max_share, 4),
        "primary_gate": "config/health-gate.json",
        "semantic_quality_gate": "scripts/quality_gate.py",
        "sensitive_evidence_gate": "scripts/sensitive_gate.py",
    }
    validation = status.setdefault("validation", {})
    validation["sensitive_claims"] = "passed"
    validation["overall"] = "passed"
    status["counts"] = {
        "all": len(accepted),
        "drama": sum(event.get("category") == "drama" for event in accepted),
        "variety": sum(event.get("category") == "variety" for event in accepted),
        "celebrity": sum(event.get("category") == "celebrity" for event in accepted),
        "entertainment_events": sum(event.get("category") == "entertainment_event" for event in accepted),
        "source_records": len(retained_records),
        "distinct_publishers": distinct_publishers,
    }
    warnings = [
        warning for warning in status.get("warnings", [])
        if not str(warning).startswith("sensitive_gate:")
    ]
    warnings.append(
        f"sensitive_gate: removed {len(rejected)} insufficiently verified sensitive candidates"
    )
    status["warnings"] = warnings
    status["sensitive_gate"] = {
        "removed_candidates": len(rejected),
        "kept_events": len(accepted),
        "rejections": rejected,
    }
    save(DATA / "status.json", status)

    print(json.dumps({
        "status": overall,
        "kept": len(accepted),
        "removed_sensitive": len(rejected),
        "publishers": distinct_publishers,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
