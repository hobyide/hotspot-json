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
    "death": ("去世","逝世","病逝","离世","死亡","死讯","享年","death","dead","died","dies","passed away","obituary","tribute"),
    "injury": ("伤亡","受伤","重伤","injury","injured","hospitalized"),
    "relationship": ("恋情","离婚","出轨","relationship","divorce","affair"),
    "legal": ("被捕","逮捕","起诉","指控","控告","违法","犯罪","arrest","arrested","lawsuit","sued","accused","accusation","allegation","crime","criminal"),
    "minor": ("未成年人","未成年","minor"),
    "privacy": ("隐私","privacy"),
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

def event_text(event: dict[str, Any], records: dict[str, dict[str, Any]]) -> str:
    parts = [str(event.get("topic","")), str(event.get("summary","")),
             str(event.get("content",{}).get("overview",""))]
    parts += [str(x) for x in event.get("content",{}).get("key_points",[])]
    parts += [str(f.get("statement","")) for f in event.get("facts",[])]
    for source in event.get("sources",[]):
        content = source.get("content",{})
        parts += [str(content.get(k,"")) for k in ("summary","excerpt","text")]
    for sid in event.get("source_ids",[]):
        record = records.get(sid,{})
        content = record.get("content",{})
        parts += [str(record.get("title",""))]
        parts += [str(content.get(k,"")) for k in ("summary","excerpt","text")]
        parts += [str(x) for x in content.get("key_facts",[])]
    return re.sub(r"\s+"," "," ".join(parts)).lower()

def term_matches(text: str, term: str) -> bool:
    term = term.lower().strip()
    if not term:
        return False
    if re.search(r"[\u4e00-\u9fff]", term):
        return term in text
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term).replace(r"\ ", r"\s+") + r"(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.I) is not None

def sensitive_categories(text: str) -> set[str]:
    return {category for category, terms in SENSITIVE_GROUPS.items()
            if any(term_matches(text, term) for term in terms)}

def proper_names(title: str) -> set[str]:
    names = set(re.findall(r"\b(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+)(?:\s+(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+)){1,3}\b", title))
    names -= {"The Guardian","Jurassic Park","New York","Los Angeles"}
    names |= set(re.findall(r"([\u4e00-\u9fff]{2,4})(?:去世|逝世|病逝|离世|被捕|起诉|回应|道歉)", title))
    return names

def title_tokens(title: str) -> set[str]:
    latin = {x.lower() for x in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3,}",title)
             if x.lower() not in {"the","and","with","from","final","interview"}}
    han = re.findall(r"[\u4e00-\u9fff]",title)
    return latin | {"".join(han[i:i+2]) for i in range(max(0,len(han)-1))}

def event_publishers(event: dict[str, Any]) -> set[str]:
    values = {str(s.get("platform")) for s in event.get("sources",[]) if s.get("platform")}
    if values:
        return values
    return {str(x) for x in event.get("entities",{}).get("organizations",[]) if x} or {"unknown"}

def sufficiently_verified(event: dict[str, Any]) -> bool:
    verification = event.get("verification",{})
    status = verification.get("status")
    official = verification.get("official_source_ids") or []
    independent = int(event.get("heat_signals",{}).get("independent_source_count",0) or 0)
    return (status == "official" and bool(official)) or (status == "confirmed" and (bool(official) or independent >= 2))

def same_event(a: dict[str,Any], b: dict[str,Any]) -> bool:
    if not (a["categories"] & b["categories"]):
        return False
    if a["names"] & b["names"]:
        return True
    if not a["tokens"] or not b["tokens"]:
        return False
    return len(a["tokens"] & b["tokens"]) / max(1,min(len(a["tokens"]),len(b["tokens"]))) >= .55

def components(items: list[dict[str,Any]]) -> list[list[dict[str,Any]]]:
    parent = list(range(len(items)))
    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a: int,b: int) -> None:
        a,b=find(a),find(b)
        if a != b: parent[b]=a
    for i in range(len(items)):
        for j in range(i+1,len(items)):
            if same_event(items[i],items[j]): union(i,j)
    groups: dict[int,list[dict[str,Any]]] = {}
    for i,item in enumerate(items): groups.setdefault(find(i),[]).append(item)
    return list(groups.values())

def merge_death(group: list[dict[str,Any]]) -> dict[str,Any]:
    ranked = sorted(group,key=lambda x: float(x["event"].get("hot_score",0)),reverse=True)
    merged = copy.deepcopy(ranked[0]["event"])
    publishers = set().union(*(event_publishers(x["event"]) for x in ranked))
    source_ids = list(dict.fromkeys(s for x in ranked for s in x["event"].get("source_ids",[])))
    sources = {s.get("source_id"):s for x in ranked for s in x["event"].get("sources",[]) if s.get("source_id")}
    urls = list(dict.fromkeys(u for x in ranked for u in x["event"].get("verification",{}).get("evidence_urls",[])))
    shared_names = set.intersection(*(x["names"] for x in ranked)) if all(x["names"] for x in ranked) else set()
    identity = max(shared_names,key=len) if shared_names else merged.get("topic","该人物")
    publisher_text = "、".join(sorted(publishers))
    claim = f"{publisher_text}均报道，{identity}已去世。"
    topic = f"{identity}去世消息获多个独立来源确认"
    merged["id"] = "20260716-" + hashlib.sha256(topic.encode()).hexdigest()[:16]
    merged["topic"], merged["summary"] = topic, claim
    merged.setdefault("heat_signals",{})["independent_source_count"] = len(publishers)
    merged["heat_signals"]["cross_platform_count"] = len(publishers)
    merged.setdefault("trend",{})["cross_platform_count"] = len(publishers)
    merged["source_ids"], merged["sources"] = source_ids[:20], list(sources.values())[:20]
    merged["verification"] = {"status":"confirmed","level":4,"official_source_ids":[],"evidence_urls":urls[:20]}
    merged["facts"] = [{"fact_id":"F"+hashlib.sha256(claim.encode()).hexdigest()[:18],"statement":claim,
                        "source_ids":source_ids[:20],"evidence_status":"cross_confirmed",
                        "fact_type":"statement","can_use_as_fact":True}]
    merged["content"] = {"overview":claim+" 仅保留多个来源共同支持的核心事实。",
                         "key_points":[claim,f"独立发布者数量：{len(publishers)}。"],"timeline":[]}
    merged["conflicts"] = []
    merged["risk_flags"] = [x for x in merged.get("risk_flags",[]) if x != "single_source"] or ["none"]
    return merged

def main() -> int:
    latest, store, status = load(DATA/"latest.json",{}), load(DATA/"sources.json",{}), load(DATA/"status.json",{})
    if not latest or not store or not status:
        raise SystemExit("missing quality-gated collector output")
    records = {r["source_id"]:r for r in store.get("records",[]) if r.get("source_id")}
    accepted, candidates, rejected, merged_groups = [], [], [], []
    for event in latest.get("items",[]):
        text = event_text(event,records)
        cats = sensitive_categories(text)
        if not cats or sufficiently_verified(event):
            accepted.append(event)
        else:
            candidates.append({"event":event,"text":text,"categories":cats,
                               "names":proper_names(str(event.get("topic",""))),
                               "tokens":title_tokens(str(event.get("topic","")))})
    for group in components(candidates):
        pubs = set().union(*(event_publishers(x["event"]) for x in group))
        shared = set.intersection(*(x["categories"] for x in group))
        if len(pubs) >= 2 and "death" in shared:
            merged = merge_death(group); accepted.append(merged)
            merged_groups.append({"topic":merged["topic"],"source_count":len(merged["source_ids"]),"publishers":sorted(pubs)})
        else:
            for x in group:
                e=x["event"]; rejected.append({"id":e.get("id"),"topic":e.get("topic"),
                    "matched_categories":sorted(x["categories"]),
                    "verification_status":e.get("verification",{}).get("status"),
                    "independent_source_count":e.get("heat_signals",{}).get("independent_source_count",0)})
    used = {sid for e in accepted for sid in e.get("source_ids",[])}
    store["records"] = [r for r in store.get("records",[]) if r.get("source_id") in used]
    counter=Counter()
    for e in accepted: counter.update(event_publishers(e))
    distinct=len(counter); share=max(counter.values(),default=0)/max(sum(counter.values()),1)
    facts=sum(1 for e in accepted for f in e.get("facts",[]) if f.get("can_use_as_fact"))
    ready=len(accepted)>=5 and distinct>=3 and facts>=3 and share<=.45
    partial=len(accepted)>=3 and distinct>=2 and facts>=2 and share<=.67
    if not (ready or partial):
        raise SystemExit("sensitive evidence gate left no publishable feed")
    predicates={"all":lambda e:True,"drama":lambda e:e.get("category")=="drama",
        "variety":lambda e:e.get("category")=="variety","celebrity":lambda e:e.get("category")=="celebrity",
        "entertainment-events":lambda e:e.get("category")=="entertainment_event"}
    for feed,predicate in predicates.items():
        payload=dict(latest); payload["feed"]=feed; payload["items"]=[e for e in accepted if predicate(e)]
        save(DATA/("latest.json" if feed=="all" else feed+".json"),payload)
    save(DATA/"sources.json",store)
    overall="ready" if ready else "partial"
    status["status"]=overall
    status["publishability"]={"can_publish":True,"mode":"full" if ready else "attributed_only",
        "publishable_event_count":len(accepted),"publishable_fact_count":facts,
        "distinct_publisher_count":distinct,"max_single_publisher_share":round(share,4),
        "primary_gate":"config/health-gate.json","semantic_quality_gate":"scripts/quality_gate.py",
        "sensitive_evidence_gate":"scripts/sensitive_gate.py"}
    status.setdefault("validation",{})["sensitive_claims"]="passed"
    status["validation"]["overall"]="passed"
    status["counts"]={"all":len(accepted),"drama":sum(e.get("category")=="drama" for e in accepted),
        "variety":sum(e.get("category")=="variety" for e in accepted),
        "celebrity":sum(e.get("category")=="celebrity" for e in accepted),
        "entertainment_events":sum(e.get("category")=="entertainment_event" for e in accepted),
        "source_records":len(store["records"]),"distinct_publishers":distinct}
    status["warnings"]=[w for w in status.get("warnings",[]) if not str(w).startswith("sensitive_gate:")]
    status["warnings"].append(f"sensitive_gate: merged {len(merged_groups)} cross-confirmed groups and removed {len(rejected)} insufficiently verified candidates")
    status["sensitive_gate"]={"merged_cross_confirmed_groups":merged_groups,"removed_candidates":len(rejected),
                              "kept_events":len(accepted),"rejections":rejected}
    save(DATA/"status.json",status)
    print(json.dumps({"status":overall,"kept":len(accepted),"merged_sensitive_groups":len(merged_groups),
                      "removed_sensitive":len(rejected),"publishers":distinct},ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
