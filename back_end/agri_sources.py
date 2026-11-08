"""Official-source ingestion, review gates and opt-in regional inspection notices.

No language-model extraction grants publication. Fetches stay inside an HTTPS
allowlist; changed bytes invalidate all prior human review decisions.
"""

import argparse
import hashlib
import json
import logging
import re
import secrets
import threading
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
import personal

router = APIRouter(prefix="/api/intelligence")
INDEX = "https://www.moa.gov.cn/xw/zwdt/"
ALLOWED = {"www.moa.gov.cn", "moa.gov.cn"}
PROVINCES = (
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "西藏",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
)
PESTS = (
    "条锈病",
    "赤霉病",
    "白粉病",
    "纹枯病",
    "茎基腐病",
    "蚜虫",
    "红蜘蛛",
    "吸浆虫",
    "草地贪夜蛾",
    "地下害虫",
)


def db():
    return personal.db()


def ensure(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS official_documents(id TEXT PRIMARY KEY,url TEXT UNIQUE NOT NULL,body TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS region_subscriptions(owner TEXT,id TEXT,body TEXT NOT NULL,PRIMARY KEY(owner,id))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS risk_deliveries(owner TEXT,doc_id TEXT,subscription_id TEXT,created TEXT NOT NULL,PRIMARY KEY(owner,doc_id,subscription_id))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS source_status(id TEXT PRIMARY KEY,body TEXT NOT NULL)"
    )


def safe_url(url):
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or p.hostname not in ALLOWED
        or p.username
        or p.password
        or p.port not in (None, 443)
        or p.query
        or p.fragment
    ):
        raise ValueError("untrusted official source")
    if not p.path.startswith("/xw/") or ".." in p.path or "%" in p.path:
        raise ValueError("unsupported official path")
    return url


def fetch(url):
    safe_url(url)
    for _ in range(4):
        with requests.get(
            url,
            timeout=(5, 15),
            stream=True,
            allow_redirects=False,
            headers={"User-Agent": "Zhimai-SourceReader/1.0"},
        ) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = safe_url(urljoin(url, response.headers.get("Location", "")))
                continue
            response.raise_for_status()
            if "html" not in response.headers.get("Content-Type", "").lower():
                raise ValueError("expected official html")
            parts = []
            total = 0
            for part in response.iter_content(16384):
                total += len(part)
                if total > 2_000_000:
                    raise ValueError("official document too large")
                parts.append(part)
            raw = b"".join(parts)
            return (
                url,
                raw.decode("utf-8-sig", errors="strict"),
                hashlib.sha256(raw).hexdigest(),
            )
    raise ValueError("too many redirects")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.links = []
        self.anchor = None
        self.anchor_text = ""
        self.parts = []
        self.depth = 0
        self.content_depth = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.meta[(attrs.get("name") or attrs.get("property") or "").lower()] = (
                attrs.get("content", "")
            )
        if tag == "a":
            self.anchor = attrs
            self.anchor_text = ""
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "div":
            self.depth += 1
            if self.content_depth is None and (
                "TRS_Editor" in attrs.get("class", "")
                or attrs.get("id") in ("Zoom", "zoom")
            ):
                self.content_depth = self.depth
        if tag in ("p", "br") and self.content_depth:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor_text += data
        if self.content_depth and not self.skip:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag == "div":
            if self.content_depth == self.depth:
                self.content_depth = None
            self.depth = max(0, self.depth - 1)
        if tag == "a" and self.anchor is not None:
            self.links.append(
                (
                    self.anchor.get("title") or self.anchor_text.strip(),
                    self.anchor.get("href", ""),
                )
            )
            self.anchor = None


def ingest(url):
    url, text, digest = fetch(url)
    page = Page()
    page.feed(text)
    title = page.meta.get("articletitle", "").strip()
    published = (page.meta.get("pubdate") or page.meta.get("publishdate") or "")[:10]
    body = "\n".join(x.strip() for x in "".join(page.parts).splitlines() if x.strip())[
        :60000
    ]
    if not title or not body or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
        raise ValueError("official article metadata missing")
    date.fromisoformat(published)
    identifier = hashlib.sha256(url.encode()).hexdigest()[:24]
    with db() as c:
        ensure(c)
        old = c.execute(
            "SELECT body FROM official_documents WHERE id=?", (identifier,)
        ).fetchone()
        previous = json.loads(old["body"]) if old else {}
        if previous.get("sha256") == digest:
            previous["retrieved_at"] = personal.now().isoformat()
            item = previous
        else:
            item = {
                "id": identifier,
                "title": title,
                "url": url,
                "publisher": page.meta.get("contentsource") or "农业农村部网站",
                "published_on": published,
                "retrieved_at": personal.now().isoformat(),
                "sha256": digest,
                "text": body,
                "kind": "unclassified",
                "regions": [],
                "pests": [],
                "valid_until": "",
                "review_status": "pending_metadata_review",
                "agronomic_review": "pending_review",
                "reviewed_by": "",
                "review_note": "",
            }
        c.execute(
            "INSERT INTO official_documents VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
            (identifier, url, json.dumps(item, ensure_ascii=False)),
        )
    return item


def approve(identifier, kind, regions, pests, valid_until, reviewer, note, cities=None):
    """Local operator command only. Review covers applicability metadata, not diagnosis."""
    cities = cities or []
    if len(cities) > 30 or any(
        not isinstance(x, str) or not x.strip() or len(x) > 30 for x in cities
    ):
        raise ValueError("invalid city applicability")
    if (
        kind not in ("guideline", "bulletin")
        or not regions
        or any(x not in (*PROVINCES, "全国") for x in regions)
        or any(x not in PESTS for x in pests)
    ):
        raise ValueError("invalid applicability metadata")
    expiry = date.fromisoformat(valid_until)
    if not reviewer.strip() or not note.strip():
        raise ValueError("named metadata review and applicability note required")
    with db() as c:
        ensure(c)
        r = c.execute(
            "SELECT body FROM official_documents WHERE id=?", (identifier,)
        ).fetchone()
        if not r:
            raise ValueError("document missing")
        item = json.loads(r["body"])
        if expiry < date.fromisoformat(item["published_on"]):
            raise ValueError("invalid validity period")
        if kind == "bulletin" and (
            not pests
            or expiry > date.fromisoformat(item["published_on"]) + timedelta(days=30)
        ):
            raise ValueError(
                "bulletin validity must be explicitly bounded within 30 days"
            )
        item.update(
            kind=kind,
            regions=regions,
            cities=cities,
            pests=pests,
            valid_until=valid_until,
            review_status="metadata_reviewed",
            reviewed_by=reviewer[:80],
            review_note=note[:2000],
            reviewed_at=personal.now().isoformat(),
        )
        c.execute(
            "UPDATE official_documents SET body=? WHERE id=?",
            (json.dumps(item, ensure_ascii=False), identifier),
        )
    return item


def documents():
    with db() as c:
        ensure(c)
        return [
            json.loads(r["body"])
            for r in c.execute("SELECT body FROM official_documents")
        ]


def applicable(item, current=None):
    current = current or personal.now().date()
    try:
        fresh = item.get("kind") != "bulletin" or timedelta(
            0
        ) <= personal.now() - datetime.fromisoformat(item["retrieved_at"]) < timedelta(
            hours=24
        )
        return (
            fresh
            and item["review_status"] == "metadata_reviewed"
            and date.fromisoformat(item["published_on"])
            <= current
            <= date.fromisoformat(item["valid_until"])
        )
    except (ValueError, KeyError):
        return False


def public(item):
    return {k: v for k, v in item.items() if k != "text"} | {
        "currently_applicable": applicable(item)
    }


def search(query, region=""):
    if len(query) > 300:
        return {"status": "invalid_query", "results": []}
    tokens = {
        query[i : i + 2] for i in range(len(query) - 1) if query[i : i + 2].strip()
    }
    found = []
    for item in documents():
        if item["kind"] != "guideline" or not applicable(item):
            continue
        if (
            region
            and "全国" not in item["regions"]
            and not any(p in region for p in item["regions"])
        ):
            continue
        if not region and "全国" not in item["regions"]:
            continue
        if item.get("cities") and not any(city in region for city in item["cities"]):
            continue
        lines = [
            line
            for line in item["text"].splitlines()
            if len(line) > 8 and any(t in line for t in tokens)
        ]
        # Actionable chemical instructions never enter the prompt from this source layer.
        lines = [
            line
            for line in lines
            if not re.search(r"药|剂|喷|克/|倍液|毫升|混配", line)
        ]
        if not lines:
            continue
        found.append(
            {
                "id": item["id"],
                "topic": item["title"],
                "quote": "\n".join(lines[:2])[:1600],
                "source": public(item),
                "review_status": item["agronomic_review"],
                "applicability": item["review_note"],
                "notice": "官方来源、适用元数据已整理；尚未完成独立农技审校。只作观察参考。",
            }
        )
    return {
        "status": "ok" if found else "no_applicable_source",
        "results": found[:5],
        "retrieved_at": personal.now().isoformat(),
        "notice": "仅采用有效且地区相符的来源；官方发布不等于本次现场确诊或用药许可。",
    }


def search_agri_guidelines(query, region=""):
    return json.dumps(search(query, region), ensure_ascii=False)


class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    province: str = Field(min_length=2, max_length=10)
    city: str = Field(default="", max_length=30)
    pests: list[str] = Field(default_factory=list, max_length=10)
    enabled: bool = True
    weather_enabled: bool = False
    weather_types: list[str] = Field(
        default_factory=lambda: [
            "暴雨",
            "大风",
            "寒潮",
            "霜冻",
            "暴雪",
            "高温",
            "冰雹",
            "雷电",
            "台风",
            "沙尘暴",
        ],
        max_length=10,
    )
    weather_min_level: str = "蓝色"
    weather_adcode: str = Field(default="", pattern=r"^(?:[0-9]{6})?$")
    weather_urgent: bool = False
    max_daily: int = Field(default=1, ge=1, le=3)
    quiet_start: str = Field(default="22:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str = Field(default="07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


def subscriptions(who):
    with db() as c:
        ensure(c)
        return [
            {"id": r["id"], **json.loads(r["body"])}
            for r in c.execute(
                "SELECT id,body FROM region_subscriptions WHERE owner=?", (who,)
            )
        ]


@router.get("/sources")
def source_list(response: Response):
    response.headers["Cache-Control"] = "no-store"
    with db() as c:
        ensure(c)
        r = c.execute("SELECT body FROM source_status WHERE id='moa'").fetchone()
    return {
        "documents": [public(d) for d in documents()],
        "status": json.loads(r["body"]) if r else {"state": "not_checked"},
        "notice": "技术指导与实时病虫情报分别管理；没有有效情报时不推送风险结论。",
    }


@router.get("/subscriptions")
def subscription_list(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        "subscriptions": subscriptions(personal.owner(request)),
        "provinces": PROVINCES,
        "pests": PESTS,
    }


@router.put("/subscriptions/{identifier}")
def save_subscription(identifier: str, item: Subscription, request: Request):
    import memory

    who = memory.write_owner(request)
    memory.identifier(identifier)
    if item.province not in PROVINCES or any(p not in PESTS for p in item.pests):
        raise HTTPException(400, "请选择支持的省份和病虫害")
    import weather_alerts, weather

    if not item.pests and not item.weather_enabled:
        raise HTTPException(400, "请至少选择病虫害订阅或开启天气预警")
    if (
        any(t not in weather_alerts.TYPES for t in item.weather_types)
        or item.weather_min_level not in weather_alerts.LEVELS
    ):
        raise HTTPException(400, "请选择支持的天气类型和级别")
    item.weather_types = list(dict.fromkeys(item.weather_types))
    if item.weather_enabled:
        if not item.weather_types:
            raise HTTPException(400, "请至少选择一种天气类型")
        item.weather_adcode = (
            item.weather_adcode or weather._location_code(item.city) or ""
        )
        if item.city and not item.weather_adcode:
            raise HTTPException(
                400, "该城市暂未自动识别，请填写用户确认的六位市县行政区编码"
            )
        if (
            item.weather_adcode
            and item.weather_adcode[:2] != weather_alerts.PROVINCE_CODES[item.province]
        ):
            raise HTTPException(400, "行政区编码与所选省份不一致，请重新确认")
    item.pests = list(dict.fromkeys(item.pests))
    with db() as c:
        ensure(c)
        c.execute("BEGIN IMMEDIATE")
        if (
            not c.execute(
                "SELECT 1 FROM region_subscriptions WHERE owner=? AND id=?",
                (who, identifier),
            ).fetchone()
            and c.execute(
                "SELECT count(*) FROM region_subscriptions WHERE owner=?", (who,)
            ).fetchone()[0]
            >= 10
        ):
            raise HTTPException(400, "最多保存10条订阅")
        c.execute(
            "INSERT INTO region_subscriptions VALUES(?,?,?) ON CONFLICT(owner,id) DO UPDATE SET body=excluded.body",
            (who, identifier, json.dumps(item.model_dump(), ensure_ascii=False)),
        )
    return {"saved": True}


@router.delete("/subscriptions/{identifier}")
def delete_subscription(identifier: str, request: Request):
    import memory

    with db() as c:
        ensure(c)
        c.execute(
            "DELETE FROM region_subscriptions WHERE owner=? AND id=?",
            (memory.write_owner(request), identifier),
        )
    return {"deleted": True}


def quiet(item, current):
    clock = current.strftime("%H:%M")
    start = item["quiet_start"]
    end = item["quiet_end"]
    if start == end:
        return False
    return start <= clock < end if start < end else clock >= start or clock < end


def deliver():
    current = personal.now()
    # No external call while holding the write transaction. A subscription is
    # rechecked in the same transaction that publishes its notice.
    with db() as c:
        ensure(c)
        c.execute("BEGIN IMMEDIATE")
        docs = [
            json.loads(r["body"])
            for r in c.execute("SELECT body FROM official_documents")
        ]
        for row in c.execute("SELECT * FROM region_subscriptions").fetchall():
            sub = json.loads(row["body"])
            if not sub["enabled"] or quiet(sub, current):
                continue
            for item in sorted(docs, key=lambda d: d["published_on"], reverse=True):
                if item["kind"] != "bulletin" or not applicable(item, current.date()):
                    continue
                # Province-level notices retain their province scope; a city is never inferred.
                if item.get("cities") and sub["city"].removesuffix("市") not in {
                    city.removesuffix("市") for city in item["cities"]
                }:
                    continue
                if sub["province"] not in item["regions"] or not set(
                    sub["pests"]
                ).intersection(item["pests"]):
                    continue
                if c.execute(
                    "SELECT 1 FROM risk_deliveries WHERE owner=? AND doc_id=?",
                    (row["owner"], item["id"]),
                ).fetchone():
                    continue
                # Owner-wide daily cap prevents several subscriptions multiplying frequency.
                count = c.execute(
                    "SELECT count(*) FROM risk_deliveries WHERE owner=? AND created>=?",
                    (
                        row["owner"],
                        current.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        ).isoformat(),
                    ),
                ).fetchone()[0]
                if count >= sub["max_daily"]:
                    continue
                notification = {
                    "name": "区域巡查提示：" + item["title"],
                    "message": f"{sub['province']}{'、'.join(item.get('cities',[]))+'市县范围' if item.get('cities') else '省级'}公开情报涉及{'、'.join(sorted(set(sub['pests']).intersection(item['pests'])))}，建议留意异常并核对原文。区域信号不能证明你的小麦已经发病，也不构成施药许可。",
                    "task_type": "regional",
                    "created_at": current.isoformat(),
                    "read": False,
                    "source": public(item),
                    "province": sub["province"],
                    "subscription_id": row["id"],
                    "quiet_start": sub["quiet_start"],
                    "quiet_end": sub["quiet_end"],
                }
                c.execute(
                    "INSERT INTO entries VALUES(?,?,?,?,?)",
                    (
                        row["owner"],
                        "risk-" + secrets.token_hex(16),
                        "notifications",
                        json.dumps(notification, ensure_ascii=False),
                        "",
                    ),
                )
                c.execute(
                    "INSERT INTO risk_deliveries VALUES(?,?,?,?)",
                    (row["owner"], item["id"], row["id"], current.isoformat()),
                )


def refresh():
    state = {
        "checked_at": personal.now().isoformat(),
        "state": "ok",
        "candidate_count": 0,
        "imported_count": 0,
    }
    try:
        url, text, _ = fetch(INDEX)
        page = Page()
        page.feed(text)
        candidates = []
        for title, link in page.links:
            if "小麦" in title and any(
                s in title for s in ("病虫", "防控", "植保", "锈病", "蚜虫", "赤霉")
            ):
                u = urljoin(url, link)
                try:
                    safe_url(u)
                except ValueError:
                    continue
                if u not in candidates:
                    candidates.append(u)
        state["candidate_count"] = len(candidates)
        # Recheck every reviewed document so changed content loses its review gate.
        seed = json.loads(
            (Path(__file__).parent / "data/knowledge/official_feeds.json").read_text(encoding="utf-8-sig")
        )["seed_urls"]
        urls = list(
            dict.fromkeys(candidates[:10] + seed + [d["url"] for d in documents()])
        )[:30]
        failures = 0
        for u in urls:
            try:
                ingest(u)
                state["imported_count"] += 1
            except Exception:
                failures += 1
        if failures:
            state["state"] = "partial_failure"
    except Exception:
        state["state"] = "unavailable"
    with db() as c:
        ensure(c)
        c.execute(
            "INSERT OR REPLACE INTO source_status VALUES(?,?)",
            ("moa", json.dumps(state)),
        )
    return state


def start():
    stop = threading.Event()

    def loop():
        last_refresh = None
        while not stop.is_set():
            try:
                if last_refresh is None or personal.now() - last_refresh >= timedelta(
                    hours=4
                ):
                    refresh()
                    last_refresh = personal.now()
                deliver()
            except Exception:
                logging.getLogger("uvicorn.error").warning(
                    "official_source_worker_failed; no risk inferred"
                )
            stop.wait(30)

    threading.Thread(target=loop, daemon=True).start()
    return stop


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and review official metadata locally; never a public admin API"
    )
    parser.add_argument("url")
    parser.add_argument("--kind", choices=["guideline", "bulletin"])
    parser.add_argument("--regions")
    parser.add_argument("--pests", default="")
    parser.add_argument("--cities", default="")
    parser.add_argument("--valid-until")
    parser.add_argument("--reviewer")
    parser.add_argument("--note")
    args = parser.parse_args()
    item = ingest(args.url)
    if args.kind:
        item = approve(
            item["id"],
            args.kind,
            args.regions.split(","),
            [x for x in args.pests.split(",") if x],
            args.valid_until,
            args.reviewer,
            args.note,
            [x for x in args.cities.split(",") if x],
        )
    print(json.dumps(public(item), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
