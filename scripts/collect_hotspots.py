#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config"
TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ)
WINDOW = NOW - timedelta(hours=30)
HARD_MAX = 30

ENTERTAINMENT_TERMS = (
    "电视剧", "网剧", "短剧", "综艺", "真人秀", "晚会", "电影", "演员", "明星",
    "导演", "编剧", "定档", "开机", "杀青", "官宣", "首播", "上映", "预告",
    "剧集", "节目", "票房", "专辑", "音乐", "演唱会", "film", "movie", "tv",
    "television", "series", "actor", "actress", "director", "trailer", "premiere",
    "casting", "album", "concert", "entertainment"
)
SENSITIVE_TERMS = (
    "恋情", "离婚", "出轨", "隐私", "去世", "死亡", "伤亡", "被捕", "起诉", "指控",
    "未成年人", "relationship", "divorce", "death", "dies", "arrest", "lawsuit",
    "accused", "allegation", "minor"
)
EXCLUDE_TERMS = (
    "政治", "选举", "总统", "战争", "军事", "体育", "足球", "篮球", "游戏", "数码",
    "科技股", "politics", "election", "war", "military", "sports", "football",
    "basketball", "gaming"
)
CATEGORY_TERMS = {
    "variety": ("综艺", "真人秀", "晚会", "节目", "reality", "variety", "show"),
    "celebrity": ("明星", "演员", "歌手", "艺人", "actor", "actress", "singer", "celebrity"),
    "entertainment_event": ("红毯", "颁奖", "演唱会", "活动", "festival", "awards", "concert"),
    "drama": ("电视剧", "网剧", "短剧", "电影", "剧集", "定档", "首播", "上映", "预告",
              "film", "movie", "series", "trailer", "premiere", "casting"),
}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    json.loads(tmp.read_text("utf-8"))
    tmp.replace(path)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(TZ).isoformat(timespec="seconds") if dt else None


def parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except Exception:
        return None


def strip_html(raw: str | None) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str, publisher: str | None = None) -> str:
    title = html.unescape(title).strip()
    if publisher:
        for sep in (" - ", " | ", " – ", " — "):
            suffix = sep + publisher
            if title.lower().endswith(suffix.lower()):
                title = title[:-len(suffix)].strip()
    return re.sub(r"\s+", " ", title)


def title_key(title: str) -> str:
    return re.sub(r"[\W_]+", "", title.lower(), flags=re.UNICODE)[:180]


def host_name(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host.removeprefix("www.") or "unknown"


def source_id(url: str) -> str:
    return "S" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def event_id(title: str) -> str:
    return NOW.strftime("%Y%m%d") + "-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]


def fact_id(title: str) -> str:
    return "F" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:18]


def make_hash(title: str, summary: str, url: str) -> str:
    raw = f"{title}\n{summary}\n{url}".encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def classify(title: str, hint: list[str]) -> str:
    low = title.lower()
    scores = {category: sum(1 for term in terms if term.lower() in low)
              for category, terms in CATEGORY_TERMS.items()}
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    for candidate in hint:
        if candidate in ("drama", "variety", "celebrity", "entertainment_event"):
            return candidate
    return "industry"


def is_relevant(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    return any(t.lower() in text for t in ENTERTAINMENT_TERMS) and not any(
        t.lower() in text for t in EXCLUDE_TERMS
    )


def is_sensitive(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    return any(t.lower() in text for t in SENSITIVE_TERMS)


def fetch(url: str, user_agent: str, timeout: int, retry_count: int, backoffs: list[int]) -> bytes:
    last: Exception | None = None
    for attempt in range(retry_count):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last = exc
            if attempt < retry_count - 1:
                time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
    raise RuntimeError(str(last) if last else "unknown fetch error")


def first_text(node: ET.Element, names: tuple[str, ...]) -> str | None:
    for child in node.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names and child.text:
            return child.text.strip()
    return None


def parse_feed(blob: bytes, group: dict[str, Any]) -> list[dict[str, Any]]:
    root = ET.fromstring(blob)
    rows: list[dict[str, Any]] = []
    item_nodes = [n for n in root.iter()
                  if n.tag.rsplit("}", 1)[-1].lower() in ("item", "entry")]
    for node in item_nodes[: int(group.get("max_items", 20))]:
        title = first_text(node, ("title",))
        if not title:
            continue
        link = first_text(node, ("link",))
        if not link:
            for child in node.iter():
                if child.tag.rsplit("}", 1)[-1].lower() == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        if not link:
            continue
        published = first_text(node, ("pubdate", "published", "updated", "date"))
        summary = first_text(node, ("description", "summary", "content", "encoded"))
        publisher = first_text(node, ("source",))
        publisher = strip_html(publisher) if publisher else host_name(link)
        clean_title = normalize_title(strip_html(title), publisher)
        clean_summary = strip_html(summary)
        dt = parse_dt(published)
        if dt and dt < WINDOW:
            continue
        if not is_relevant(clean_title, clean_summary) or is_sensitive(clean_title, clean_summary):
            continue
        rows.append({
            "title": clean_title,
            "url": link,
            "publisher": publisher,
            "published_at": dt,
            "summary": clean_summary[:1200],
            "region": group.get("region", "GLOBAL"),
            "tier": group.get("tier", "tier_4_search_fallback"),
            "category_hint": group.get("categories", []),
        })
    return rows


def choose_balanced(rows: list[dict[str, Any]], max_per_publisher: int, hard_max: int) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict[str, Any]] = []
    minimum = datetime.min.replace(tzinfo=TZ)
    for row in sorted(rows, key=lambda r: r["published_at"] or minimum, reverse=True):
        norm_url = row["url"].split("#", 1)[0]
        key = title_key(row["title"])
        if norm_url in seen_urls or key in seen_titles:
            continue
        seen_urls.add(norm_url)
        seen_titles.add(key)
        unique.append(row)

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in unique:
        buckets[row["publisher"]].append(row)

    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    publishers = sorted(buckets, key=lambda p: buckets[p][0]["published_at"] or minimum, reverse=True)
    while len(selected) < hard_max:
        added = False
        for publisher in publishers:
            if counts[publisher] >= max_per_publisher or not buckets[publisher]:
                continue
            selected.append(buckets[publisher].pop(0))
            counts[publisher] += 1
            added = True
            if len(selected) >= hard_max:
                break
        if not added:
            break
    return selected


def build_source_record(row: dict[str, Any]) -> dict[str, Any]:
    sid = source_id(row["url"])
    summary = row["summary"] or f"{row['publisher']} 发布了与“{row['title']}”相关的公开页面。"
    return {
        "source_id": sid,
        "title": row["title"],
        "url": row["url"],
        "normalized_url": row["url"].split("#", 1)[0],
        "source": row["publisher"],
        "source_type": "industry_media" if row["tier"] == "tier_3_industry_media" else "search_fallback",
        "tier": row["tier"],
        "author": None,
        "published_at": iso(row["published_at"]),
        "fetched_at": iso(NOW),
        "content_hash": make_hash(row["title"], summary, row["url"]),
        "fetch_status": "success",
        "rank": None,
        "heat_raw": None,
        "content": {
            "mode": "summary_only",
            "text": None,
            "summary": summary,
            "excerpt": None,
            "language": "zh-CN" if re.search(r"[\u4e00-\u9fff]", row["title"]) else "en",
            "license": {"status": "unknown", "name": None, "url": None},
            "key_facts": [f"据{row['publisher']}页面，{row['title']}。"],
        },
        "media": {"images": [], "videos": []},
    }


def build_event(row: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    category = classify(row["title"], row["category_hint"])
    age_hours = 12
    if row["published_at"]:
        age_hours = max(0, int((NOW - row["published_at"]).total_seconds() / 3600))
    score = max(35, min(78, 72 - age_hours))
    statement = f"据{row['publisher']}页面，{row['title']}。"
    return {
        "id": event_id(row["title"]),
        "topic": row["title"],
        "summary": statement,
        "category": category,
        "language": "zh-CN",
        "region": row["region"],
        "hot_score": score,
        "heat_signals": {
            "independent_source_count": 1,
            "official_source_count": 0,
            "cross_platform_count": 1,
            "best_rank": None,
            "spread_velocity": None,
            "engagement": {"likes": None, "comments": None, "shares": None, "views": None},
        },
        "first_seen_at": iso(NOW),
        "last_seen_at": iso(NOW),
        "trend": {"status": "new", "cross_platform_count": 1},
        "entities": {"shows": [], "celebrities": [], "organizations": [row["publisher"]]},
        "content": {
            "overview": statement + (" " + row["summary"][:700] if row["summary"] else ""),
            "key_points": [statement, "当前未保存不可核验的排名或互动量。"],
            "timeline": [{"time": iso(row["published_at"]) or iso(NOW), "event": statement,
                          "source_ids": [src["source_id"]]}],
        },
        "verification": {
            "status": "reported",
            "level": 2,
            "official_source_ids": [],
            "evidence_urls": [row["url"]],
        },
        "source_ids": [src["source_id"]],
        "sources": [{
            "source_id": src["source_id"],
            "platform": row["publisher"],
            "source_type": src["source_type"],
            "rank": None,
            "heat_raw": None,
            "title": row["title"],
            "url": row["url"],
            "captured_at": iso(NOW),
            "content_hash": src["content_hash"],
            "content": {
                "mode": "summary_only",
                "text": None,
                "summary": src["content"]["summary"],
                "excerpt": None,
                "language": src["content"]["language"],
                "license": src["content"]["license"],
                "retrieved_at": iso(NOW),
            },
        }],
        "facts": [{
            "fact_id": fact_id(row["title"]),
            "statement": statement,
            "source_ids": [src["source_id"]],
            "evidence_status": "single_source",
            "fact_type": "statement",
            "can_use_as_fact": True,
        }],
        "conflicts": [],
        "risk_flags": ["single_source", "copyright_restriction"],
        "media": {"images": [], "videos": []},
    }


def validate(events: list[dict[str, Any]], sources: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    source_ids = {s["source_id"] for s in sources}
    if len(source_ids) != len(sources):
        errors.append("duplicate_source_id")
    event_ids: set[str] = set()
    for event in events:
        if event["id"] in event_ids:
            errors.append(f"duplicate_event_id:{event['id']}")
        event_ids.add(event["id"])
        for sid in event["source_ids"]:
            if sid not in source_ids:
                errors.append(f"missing_source:{sid}")
        for fact in event["facts"]:
            if not fact["source_ids"]:
                errors.append(f"fact_without_source:{fact['fact_id']}")
    return (not errors, errors)


def main() -> int:
    runtime = read_json(CONFIG / "runtime-sources.json", {})
    health_cfg = read_json(CONFIG / "health-gate.json", {})
    req = runtime.get("request", {})
    source_status: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for group in runtime.get("source_groups", []):
        try:
            blob = fetch(
                group["url"],
                req.get("user_agent", "hotspot-json/1.0"),
                int(req.get("timeout_seconds", 20)),
                int(req.get("retry_count", 3)),
                list(req.get("retry_backoff_seconds", [2, 5, 10])),
            )
            parsed = parse_feed(blob, group)
            rows.extend(parsed)
            source_status.append({
                "platform": group["name"],
                "status": "ok",
                "item_count": len(parsed),
                "checked_at": iso(NOW),
                "error": None,
            })
        except Exception as exc:
            source_status.append({
                "platform": group.get("name", group.get("id", "unknown")),
                "status": "failed",
                "item_count": 0,
                "checked_at": iso(NOW),
                "error": str(exc)[:900],
            })

    selection = runtime.get("selection", {})
    chosen = choose_balanced(
        rows,
        int(selection.get("max_items_per_publisher", 4)),
        int(selection.get("hard_max_items", HARD_MAX)),
    )
    sources = [build_source_record(row) for row in chosen]
    events = [build_event(row, src) for row, src in zip(chosen, sources)]

    valid, validation_errors = validate(events, sources)
    publisher_counts = Counter(row["publisher"] for row in chosen)
    distinct_publishers = len(publisher_counts)
    max_share = max(publisher_counts.values(), default=0) / max(len(chosen), 1)
    publishable_facts = sum(1 for event in events for fact in event["facts"]
                            if fact.get("can_use_as_fact"))

    ready_cfg = health_cfg.get("ready", {})
    partial_cfg = health_cfg.get("partial", {})
    ready = (
        valid
        and len(events) >= int(ready_cfg.get("minimum_events", 5))
        and distinct_publishers >= int(ready_cfg.get("minimum_distinct_publishers", 3))
        and publishable_facts >= int(ready_cfg.get("minimum_publishable_facts", 3))
        and max_share <= float(ready_cfg.get("maximum_single_publisher_share", 0.45))
    )
    partial = (
        valid
        and len(events) >= int(partial_cfg.get("minimum_events", 3))
        and distinct_publishers >= int(partial_cfg.get("minimum_distinct_publishers", 2))
        and publishable_facts >= int(partial_cfg.get("minimum_publishable_facts", 2))
        and max_share <= float(partial_cfg.get("maximum_single_publisher_share", 0.67))
    )

    status = "ready" if ready else "partial" if partial else "failed"
    can_publish = ready or partial
    mode = "full" if ready else "attributed_only" if partial else "blocked"

    if not can_publish:
        previous_status = read_json(DATA / "status.json", {})
        previous_feed = read_json(DATA / "latest.json", {})
        generated = parse_dt(previous_feed.get("generated_at")) if previous_feed else None
        previous_ok = (
            previous_feed
            and previous_feed.get("items")
            and generated
            and (NOW - generated) <= timedelta(hours=36)
            and previous_status.get("publishability", {}).get("can_publish", False)
        )
        if previous_ok:
            previous_status["status"] = "partial"
            previous_status["last_check_at"] = iso(NOW)
            previous_status["warnings"] = sorted(set(previous_status.get("warnings", []) + [
                "本轮新数据未达到 partial 门槛，已保留36小时内的上一版有效 Feed"
            ]))
            previous_status["publishability"]["mode"] = "cached_attributed"
            write_json(DATA / "status.json", previous_status)
            print("Preserved previous valid feed; new run below partial threshold.")
            return 0

    cleanup_prev = read_json(DATA / "latest.json", {}).get("cleanup", {
        "last_run_at": None,
        "status": "pending",
        "mode": "archive_then_expire",
        "last_archive_at": None,
    })
    pipeline = {
        "source_store": "data/sources.json",
        "facts_required": True,
        "citation_validation": "passed" if valid else "failed",
    }
    feed_base = {
        "schema_version": "1.2",
        "generated_at": iso(NOW),
        "timezone": "Asia/Shanghai",
        "window_hours": 24,
        "pipeline": pipeline,
        "source_status": source_status,
        "cleanup": cleanup_prev,
    }

    feeds = {
        "all": events,
        "drama": [e for e in events if e["category"] == "drama"],
        "variety": [e for e in events if e["category"] == "variety"],
        "celebrity": [e for e in events if e["category"] == "celebrity"],
        "entertainment-events": [e for e in events if e["category"] == "entertainment_event"],
    }
    file_map = {
        "all": "latest.json",
        "drama": "drama.json",
        "variety": "variety.json",
        "celebrity": "celebrity.json",
        "entertainment-events": "entertainment-events.json",
    }
    for feed_name, items in feeds.items():
        payload = dict(feed_base)
        payload["feed"] = feed_name
        payload["items"] = items
        write_json(DATA / file_map[feed_name], payload)

    write_json(DATA / "sources.json", {
        "schema_version": "1.0",
        "generated_at": iso(NOW),
        "timezone": "Asia/Shanghai",
        "records": sources,
        "source_status": [{
            "source": row["platform"],
            "status": row["status"],
            "checked_at": row["checked_at"],
            "error": row["error"],
        } for row in source_status],
    })

    old_manifest = read_json(DATA / "manifest.json", {})
    old_manifest["last_event_generated_at"] = iso(NOW)
    old_manifest["last_source_store_generated_at"] = iso(NOW)
    old_manifest["runtime_sources"] = "config/runtime-sources.json"
    old_manifest["health_gate"] = "config/health-gate.json"
    old_manifest["collector"] = "scripts/collect_hotspots.py"
    write_json(DATA / "manifest.json", old_manifest)

    warnings = [f"{s['platform']}: {s['error']}" for s in source_status if s["status"] != "ok"]
    write_json(DATA / "status.json", {
        "schema_version": "2.0",
        "project": "hobyide/hotspot-json",
        "timezone": "Asia/Shanghai",
        "status": status,
        "last_check_at": iso(NOW),
        "next_check_at": iso(NOW + timedelta(hours=6)),
        "publishability": {
            "can_publish": can_publish,
            "mode": mode,
            "publishable_event_count": len(events),
            "publishable_fact_count": publishable_facts,
            "distinct_publisher_count": distinct_publishers,
            "max_single_publisher_share": round(max_share, 4),
            "primary_gate": "config/health-gate.json",
        },
        "validation": {
            "overall": "passed" if valid else "failed",
            "json_parse": "passed",
            "source_reference_integrity": "passed" if valid else "failed",
            "fact_support": "passed" if valid else "failed",
            "deduplication": "passed" if valid else "failed",
            "errors": validation_errors,
        },
        "counts": {
            "all": len(events),
            "drama": len(feeds["drama"]),
            "variety": len(feeds["variety"]),
            "celebrity": len(feeds["celebrity"]),
            "entertainment_events": len(feeds["entertainment-events"]),
            "source_records": len(sources),
            "distinct_publishers": distinct_publishers,
        },
        "source_status": source_status,
        "warnings": warnings,
        "errors": validation_errors if not valid else [],
        "content_model": "multi_source_rss_plus_news_aggregation_with_attribution",
        "pipeline": {
            "runtime_sources": "config/runtime-sources.json",
            "health_gate": "config/health-gate.json",
            "source_store": "data/sources.json",
            "event_schema": "schema/hotspot-v1.2.schema.json",
            "source_schema": "schema/source-record.schema.json",
        },
    })

    print(json.dumps({
        "status": status,
        "can_publish": can_publish,
        "events": len(events),
        "publishers": distinct_publishers,
        "max_share": round(max_share, 4),
        "failed_sources": sum(1 for s in source_status if s["status"] != "ok"),
    }, ensure_ascii=False))
    return 0 if can_publish else 2


if __name__ == "__main__":
    sys.exit(main())
