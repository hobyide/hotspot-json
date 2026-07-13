#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

SENSITIVE_GROUPS = {
    "death": (
        "去世", "逝世", "病逝", "离世", "死亡", "死讯", "享年",
        "death", "dead", "died", "dies", "passed away", "obituary", "tribute",
    ),
    "injury": ("伤亡", "受伤", "重伤", "injury", "injured", "hospitalized"),
    "relationship": ("恋情", "离婚", "出轨", "relationship", "divorce", "affair"),
    "legal": (
        "被捕", "逮捕", "起诉", "指控", "控告", "违法", "犯罪",
        "arrest", "arrested", "lawsuit", "sued", "accused", "accusation",
        "allegation", "crime", "criminal",
    ),
    "minor": ("未成年人", "未成年", "minor"),
    "privacy": ("隐私", "privacy"),
}


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


def sensitive_categories(text: str) -> set[str]:
    return {
        category
        for category, terms in SENSITIVE_GROUPS.items()
        if any(term.lower() in text for term in terms)
    }


def proper_names(title: str) -> set[str]:
    pattern = re.compile(
        r"\b(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+)(?:\s+(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+)){1,3}\b"
    )
    names: set[str] = set()
    for match in pattern.findall(title):
        normalized = re.sub(r"(?:'s|’s)$", "", match.strip(), flags=re.I)
        normalized = re.sub(r"\s+", " ", normalized)
        if normalized.lower() not in {
            "The Guardian", "Jurassic Park", "New York", "Los Angeles",
        }:
            names.add(normalized)
    for match in re.findall(
        r"([\u4e00-\u9fff]{2,4})(?:去世|逝世|病逝|离世|被捕|起诉|回应|道歉)",
        title,
    ):
        names.add(match)
    return names


def title_tokens(title: str) -> set[str]:
    latin = {
        token.lower()
        for token in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3,}", title)
        if token.lower() not in {"the", "and", "with", "from", "final", "interview"}
    }
    han = re.findall(r"[\u4e00-\u9fff]", title)
    bigrams = {"".join(han[index:index + 2]) for index in range(max(0, len(han) - 1))}
    return latin | bigrams


def same_event(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not (left["categories"] & right["categories"]):
        return False
    if left["names"] & right["names"]:
        return True
    left_tokens = left["tokens"]
    right_tokens = right["tokens"]
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return overlap >= 0.55


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


def event_publishers(event: dict[str, Any]) -> set[str]:
    publishers = {
        str(source.get("platform"))
        for source in event.get("sources", [])
        if source.get("platform")
    }
    if publishers:
        return publishers
    organizations = event.get("entities", {}).get("organizations") or []
    return {str(value) for value in organizations if value} or {"unknown"}


def display_publisher(value: str) -> str:
    mappings = {
        "bbc.co.uk": "BBC",
        "theguardian.com": "The Guardian",
        "variety.com": "Variety",
        "deadline.com": "Deadline",
    }
    return mappings.get(value.lower(), value)


def consensus_age(texts: list[str]) -> str | None:
    ages: list[str] = []
    for text in texts:
        ages.extend(re.findall(r"(?:aged\s+|享年\s*)(\d{1,3})", text, flags=re.I))
    counts = Counter(ages)
    if not counts:
        return None
    age, count = counts.most_common(1)[0]
    return age if count >= 2 else None


def merge_cross_confirmed(component: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        component,
        key=lambda candidate: float(candidate["event"].get("hot_score", 0)),
        reverse=True,
    )
    merged = copy.deepcopy(ranked[0]["event"])
    source_map: dict[str, dict[str, Any]] = {}
    source_ids: list[str] = []
    evidence_urls: list[str] = []
    organizations: list[str] = []
    timeline: list[dict[str, Any]] = []
    texts: list[str] = []
    publishers: set[str] = set()

    for candidate in ranked:
        event = candidate["event"]
        texts.append(candidate["text"])
        publishers.update(event_publishers(event))
        for source_id in event.get("source_ids", []):
            if source_id not in source_ids:
                source_ids.append(source_id)
        for source in event.get("sources", []):
            source_id = source.get("source_id")
            if source_id:
                source_map[source_id] = source
        for url in event.get("verification", {}).get("evidence_urls", []):
            if url not in evidence_urls:
                evidence_urls.append(url)
        for organization in event.get("entities", {}).get("organizations", []):
            if organization not in organizations:
                organizations.append(organization)
        for entry in event.get("content", {}).get("timeline", []):
            if entry not in timeline:
                timeline.append(entry)

    common_names = set.intersection(*(candidate["names"] for candidate in ranked if candidate["names"])) \
        if all(candidate["names"] for candidate in ranked) else set()
    identity = sorted(common_names, key=len, reverse=True)[0] if common_names else merged.get("topic", "该人物")
    publisher_names = [display_publisher(value) for value in sorted(publishers)]
    publisher_text = "、".join(publisher_names)
    categories = set.intersection(*(candidate["categories"] for candidate in ranked))

    if "death" in categories:
        age = consensus_age(texts)
        claim = f"{publisher_text}均报道，{identity}已去世"
        if age:
            claim += f"，享年{age}岁"
        claim += "。"
        topic = f"{identity}去世消息获多个独立来源确认"
    else:
        claim = f"{publisher_text}均对涉及{identity}的敏感事件进行了独立报道。"
        topic = f"涉及{identity}的敏感事件获多个来源报道"

    merged["id"] = "20260713-" + hashlib.sha256(topic.encode("utf-8")).hexdigest()[:16]
    merged["topic"] = topic
    merged["summary"] = claim
    merged["hot_score"] = min(100, max(float(item["event"].get("hot_score", 0)) for item in ranked) + 8)
    merged["heat_signals"]["independent_source_count"] = len(publishers)
    merged["heat_signals"]["cross_platform_count"] = len(publishers)
    merged["trend"]["cross_platform_count"] = len(publishers)
    merged["entities"]["organizations"] = organizations
    if identity and identity not in merged["entities"].get("celebrities", []):
        merged["entities"].setdefault("celebrities", []).append(identity)
    merged["content"] = {
        "overview": claim + " 该条目由多个独立媒体来源交叉核验，未使用未经证实的延伸信息。",
        "key_points": [
            claim,
            f"独立发布者数量：{len(publishers)}。",
            "仅保留多个来源共同支持的核心事实。",
        ],
        "timeline": timeline[:20],
    }
    merged["verification"] = {
        "status": "confirmed",
        "level": 4,
        "official_source_ids": [],
        "evidence_urls": evidence_urls[:20],
    }
    merged["source_ids"] = source_ids[:20]
    merged["sources"] = list(source_map.values())[:20]
    merged["facts"] = [{
        "fact_id": "F" + hashlib.sha256(claim.encode("utf-8")).hexdigest()[:18],
        "statement": claim,
        "source_ids": source_ids[:20],
        "evidence_status": "cross_confirmed",
        "fact_type": "statement",
        "can_use_as_fact": True,
    }]
    merged["conflicts"] = []
    merged["risk_flags"] = [
        flag for flag in merged.get("risk_flags", []) if flag != "single_source"
    ]
    if not merged["risk_flags"]:
        merged["risk_flags"] = ["none"]
    return merged


def build_components(candidates: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    parent = list(range(len(candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            if same_event(candidates[left], candidates[right]):
                union(left, right)

    groups: dict[int, list[dict[str, Any]]] = {}
    for index, candidate in enumerate(candidates):
        groups.setdefault(find(index), []).append(candidate)
    return list(groups.values())


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
    sensitive_candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    merged_groups: list[dict[str, Any]] = []

    for event in latest.get("items", []):
        text = event_text(event, source_records)
        categories = sensitive_categories(text)
        if not categories:
            accepted.append(event)
            continue
        if sufficiently_verified(event):
            accepted.append(event)
            continue
        sensitive_candidates.append({
            "event": event,
            "text": text,
            "categories": categories,
            "names": proper_names(str(event.get("topic", ""))),
            "tokens": title_tokens(str(event.get("topic", ""))),
        })

    for component in build_components(sensitive_candidates):
        component_publishers = set().union(
            *(event_publishers(candidate["event"]) for candidate in component)
        )
        shared_categories = set.intersection(*(candidate["categories"] for candidate in component))
        if len(component_publishers) >= 2 and "death" in shared_categories:
            merged = merge_cross_confirmed(component)
            accepted.append(merged)
            merged_groups.append({
                "topic": merged["topic"],
                "source_count": len(merged["source_ids"]),
                "publishers": sorted(component_publishers),
            })
            continue
        for candidate in component:
            event = candidate["event"]
            rejected.append({
                "id": event.get("id"),
                "topic": event.get("topic"),
                "matched_categories": sorted(candidate["categories"]),
                "verification_status": event.get("verification", {}).get("status"),
                "independent_source_count": event.get("heat_signals", {}).get("independent_source_count", 0),
            })

    accepted_source_ids = {source_id for event in accepted for source_id in event.get("source_ids", [])}
    retained_records = [
        record for record in source_store.get("records", [])
        if record.get("source_id") in accepted_source_ids
    ]

    publisher_counter: Counter[str] = Counter()
    for event in accepted:
        publisher_counter.update(event_publishers(event))
    distinct_publishers = len(publisher_counter)
    max_share = max(publisher_counter.values(), default=0) / max(sum(publisher_counter.values()), 1)
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
            "merged_sensitive_groups": merged_groups,
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
        f"sensitive_gate: merged {len(merged_groups)} cross-confirmed groups and removed {len(rejected)} insufficiently verified candidates"
    )
    status["warnings"] = warnings
    status["sensitive_gate"] = {
        "merged_cross_confirmed_groups": merged_groups,
        "removed_candidates": len(rejected),
        "kept_events": len(accepted),
        "rejections": rejected,
    }
    save(DATA / "status.json", status)

    print(json.dumps({
        "status": overall,
        "kept": len(accepted),
        "merged_sensitive_groups": len(merged_groups),
        "removed_sensitive": len(rejected),
        "publishers": distinct_publishers,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
