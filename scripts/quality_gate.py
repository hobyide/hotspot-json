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
TARGET_ITEMS = 15
MAX_PER_PUBLISHER = 3

ACTION_TERMS = (
    "官宣", "定档", "开机", "杀青", "首播", "开播", "上映", "发布", "推出", "加盟",
    "主演", "阵容", "回归", "续订", "取消", "获奖", "入围", "亮相", "回应", "预告",
    "上线", "收官", "宣布", "曝光", "发布会", "trailer", "premiere", "release",
    "released", "launch", "launched", "cast", "casting", "lineup", "renewed", "canceled",
    "cancelled", "returns", "return", "debut", "announces", "announced", "unveils",
    "passes", "joins", "wins", "nominated", "sets", "greenlights", "orders"
)
EVENT_SIGNAL_TERMS = ACTION_TERMS + (
    "release date", "sets date", "official trailer", "season premiere", "series order",
    "节目阵容", "正式公布", "确认出演", "公布名单"
)
EDITORIAL_PATTERNS = (
    r"\bpoem\b", r"\bobituary\b", r"\btribute\b", r"\bprofile\b",
    r"\binterview\b", r"\bq\s*&\s*a\b", r"\breview\b", r"\brecap\b",
    r"\bexplainer\b", r"\bcolumn\b", r"\bopinion\b", r"\bremember(?:s|ing)?\b",
    r"诗歌", r"悼文", r"纪念文", r"人物特写", r"专访", r"访谈", r"影评", r"剧评",
    r"盘点", r"回顾", r"评论", r"观点", r"生活方式", r"幕后故事"
)
GENERIC_PREFIXES = (
    "综艺 ", "电视剧 ", "电影 ", "明星 ", "娱乐 ", "真人秀 ", "剧集 ",
    "variety ", "movie ", "tv ", "series "
)
GENERIC_TITLES = {
    "娱乐新闻", "明星娱乐", "今日娱乐", "电视剧", "综艺", "电影", "明星",
    "entertainment news", "movie news", "tv news"
}
BAD_PATTERNS = (
    r"^首页$", r"^专题$", r"^视频$", r"^图片$", r"^滚动新闻$", r"^最新消息$",
    r"^(综艺|电视剧|电影|明星|娱乐)\s+[^，。！？:：]{1,12}$"
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


def compact(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def cjk_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def has_action(title: str) -> bool:
    low = title.lower()
    return any(term.lower() in low for term in ACTION_TERMS)


def has_event_signal(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    return any(term.lower() in text for term in EVENT_SIGNAL_TERMS)


def is_editorial(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    return any(re.search(pattern, text, flags=re.I) for pattern in EDITORIAL_PATTERNS)


def source_summary(event: dict[str, Any]) -> str:
    sources = event.get("sources") or []
    if not sources:
        return ""
    return compact(sources[0].get("content", {}).get("summary"))


def publisher(event: dict[str, Any]) -> str:
    sources = event.get("sources") or []
    if sources and sources[0].get("platform"):
        return compact(sources[0]["platform"])
    organizations = event.get("entities", {}).get("organizations") or []
    return compact(organizations[0]) if organizations else "unknown"


def residual_detail(title: str, summary: str, pub: str) -> str:
    text = summary
    for value in (title, pub):
        if value:
            text = text.replace(value, " ")
    text = re.sub(r"[\[\]()（）…\.·|\-—–_]+", " ", text)
    return compact(text)


def quality_result(event: dict[str, Any]) -> tuple[bool, list[str]]:
    title = compact(event.get("topic"))
    summary = source_summary(event)
    pub = publisher(event)
    reasons: list[str] = []

    if not title:
        return False, ["empty_title"]
    if title.lower() in GENERIC_TITLES:
        reasons.append("generic_title")
    if any(re.search(pattern, title, flags=re.I) for pattern in BAD_PATTERNS):
        reasons.append("query_like_or_generic_title")

    chinese = cjk_count(title)
    if chinese:
        if chinese < 8 and len(title) < 16:
            reasons.append("title_too_short")
    elif len(title) < 28:
        reasons.append("title_too_short")

    detail = residual_detail(title, summary, pub)
    action = has_action(title)
    event_signal = has_event_signal(title, summary)
    if is_editorial(title, summary) and not event_signal:
        reasons.append("editorial_not_event")
    if not action and len(detail) < 45:
        reasons.append("no_action_and_no_detail")
    if any(title.lower().startswith(prefix.lower()) for prefix in GENERIC_PREFIXES):
        if not action and len(detail) < 60:
            reasons.append("generic_prefix_without_event")
    if summary and compact(summary).lower() in {
        title.lower(), f"{title} {pub}".lower(), f"{title}-{pub}".lower()
    }:
        reasons.append("summary_repeats_title_only")
    return not reasons, sorted(set(reasons))


def balanced(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(events, key=lambda e: (
        float(e.get("hot_score", 0)), e.get("last_seen_at", "")
    ), reverse=True)
    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for event in ordered:
        pub = publisher(event)
        if counts[pub] >= MAX_PER_PUBLISHER:
            continue
        selected.append(event)
        counts[pub] += 1
        if len(selected) >= TARGET_ITEMS:
            break
    return selected


def main() -> int:
    latest = load(DATA / "latest.json", {})
    sources_store = load(DATA / "sources.json", {})
    status = load(DATA / "status.json", {})
    if not latest or not sources_store or not status:
        raise SystemExit("missing collector output")

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for event in latest.get("items", []):
        ok, reasons = quality_result(event)
        if ok:
            accepted.append(event)
        else:
            rejected.append({"id": event.get("id"), "topic": event.get("topic"), "reasons": reasons})

    accepted = balanced(accepted)
    accepted_source_ids = {sid for event in accepted for sid in event.get("source_ids", [])}
    records = [r for r in sources_store.get("records", []) if r.get("source_id") in accepted_source_ids]
    publishers = Counter(publisher(event) for event in accepted)
    distinct = len(publishers)
    max_share = max(publishers.values(), default=0) / max(len(accepted), 1)
    publishable_facts = sum(1 for e in accepted for f in e.get("facts", []) if f.get("can_use_as_fact"))

    ready = len(accepted) >= 5 and distinct >= 3 and publishable_facts >= 3 and max_share <= 0.45
    partial = len(accepted) >= 3 and distinct >= 2 and publishable_facts >= 2 and max_share <= 0.67
    can_publish = ready or partial
    overall = "ready" if ready else "partial" if partial else "failed"
    mode = "full" if ready else "attributed_only" if partial else "blocked"
    if not can_publish:
        print(json.dumps({"accepted": len(accepted), "rejected": len(rejected), "distinct_publishers": distinct,
                          "max_share": round(max_share, 4), "examples": rejected[:10]}, ensure_ascii=False, indent=2))
        raise SystemExit("semantic quality gate left no publishable feed")

    feed_map = {
        "all": ("latest.json", lambda e: True),
        "drama": ("drama.json", lambda e: e.get("category") == "drama"),
        "variety": ("variety.json", lambda e: e.get("category") == "variety"),
        "celebrity": ("celebrity.json", lambda e: e.get("category") == "celebrity"),
        "entertainment-events": ("entertainment-events.json", lambda e: e.get("category") == "entertainment_event"),
    }
    for feed_name, (filename, predicate) in feed_map.items():
        payload = dict(latest)
        payload["feed"] = feed_name
        payload["items"] = [event for event in accepted if predicate(event)]
        save(DATA / filename, payload)

    sources_store["records"] = records
    save(DATA / "sources.json", sources_store)
    status["status"] = overall
    status["publishability"] = {
        "can_publish": True, "mode": mode, "publishable_event_count": len(accepted),
        "publishable_fact_count": publishable_facts, "distinct_publisher_count": distinct,
        "max_single_publisher_share": round(max_share, 4), "primary_gate": "config/health-gate.json",
        "semantic_quality_gate": "scripts/quality_gate.py",
    }
    status.setdefault("validation", {})["content_quality"] = "passed"
    status["validation"]["overall"] = "passed"
    status["counts"] = {
        "all": len(accepted), "drama": sum(e.get("category") == "drama" for e in accepted),
        "variety": sum(e.get("category") == "variety" for e in accepted),
        "celebrity": sum(e.get("category") == "celebrity" for e in accepted),
        "entertainment_events": sum(e.get("category") == "entertainment_event" for e in accepted),
        "source_records": len(records), "distinct_publishers": distinct,
    }
    warnings = [w for w in status.get("warnings", []) if not str(w).startswith("quality_gate:")]
    warnings.append(f"quality_gate: removed {len(rejected)} low-information candidates and kept {len(accepted)}")
    status["warnings"] = warnings
    status["quality_gate"] = {
        "removed_low_information_candidates": len(rejected), "kept_events": len(accepted),
        "rejection_examples": rejected[:10],
    }
    save(DATA / "status.json", status)
    print(json.dumps({"status": overall, "kept": len(accepted), "removed": len(rejected),
                      "publishers": distinct, "max_share": round(max_share, 4)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
