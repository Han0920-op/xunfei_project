"""Opt-in official weather warnings and explicitly separate presentation scenarios.

Only bounded, dated, region-coded source records can notify. A feed disappearance
never means cancellation. Demonstrations do not write warnings or notifications.
"""

import hashlib
import json
import logging
import re
import secrets
import threading
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from xml.etree import ElementTree

import requests
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
import agri_sources
import personal

router = APIRouter(prefix="/api/weather-alerts")
SOURCE_URL = "https://weather.cma.cn/api/map/alarm"
PORTAL_URL = "https://weather.cma.cn/"
TYPES = (
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
)
LEVELS = {"蓝色": 1, "黄色": 2, "橙色": 3, "红色": 4}
PROVINCE_CODES = dict(
    zip(
        agri_sources.PROVINCES,
        (
            "11",
            "12",
            "13",
            "14",
            "15",
            "21",
            "22",
            "23",
            "31",
            "32",
            "33",
            "34",
            "35",
            "36",
            "37",
            "41",
            "42",
            "43",
            "44",
            "45",
            "46",
            "50",
            "51",
            "52",
            "53",
            "54",
            "61",
            "62",
            "63",
            "64",
            "65",
        ),
    )
)
MAX_AGE = timedelta(minutes=20)
INTERVAL = 600
ADVICE = {
    "暴雨": [
        "先确保人员安全，雷雨、积水或道路受阻时不要下田。",
        "在天气允许且安全时检查排水沟和出口是否堵塞；雨后记录积水、倒伏与新叶变化。",
        "补拍同一异常部位和全株照片；病虫害及后续处理需结合实际情况核对。",
    ],
    "大风": [
        "提前收妥容易被风吹动的农资、工具和轻物；远离松动设施。",
        "大风期间暂停露天施药及高处作业，避免漂移和人身伤害。",
        "风后从安全位置检查倒伏、折伤和异常范围，记录并补图复查。",
    ],
    "寒潮": [
        "关注当地最新预警和农技指导，先核实麦苗生育期及实际气温。",
        "低温期间以人员安全和持续观察为先，不仅凭预报自动灌水、追肥或增加药剂。",
        "天气好转后观察新叶、生长点外观和异常范围，必要时请当地农技人员现场复核。",
    ],
    "霜冻": [
        "核对当地实况、地表温度及作物生育期，城市预报不能证明麦苗已受冻。",
        "防冻措施需结合当地农技指导和灌排条件确认，不统一安排灌水或喷药。",
        "天气好转后记录新叶及异常部位变化，保留前后照片供复核。",
    ],
    "暴雪": [
        "避免雪中下田、清理高处积雪或靠近受压设施。",
        "在安全条件下检查道路和排水出口；不要因担心冻害立即追加农药或肥料。",
        "雪后记录积雪、倒伏与麦苗变化，按当地农技指导复查。",
    ],
    "高温": [
        "避开高温时段进行户外作业，做好人员防暑。",
        "观察麦苗萎蔫、叶片及土壤表面状况；灌溉安排需结合实际墒情和当地指导。",
        "记录异常发生时间与范围，不能凭高温预警直接认定病害或决定喷药。",
    ],
    "冰雹": [
        "及时到安全处避险，不在冰雹过程中下田检查。",
        "天气平稳后检查叶片破损、折伤和倒伏，记录范围并补拍全株与近景。",
        "受伤不等于感染病害；后续处置请结合实际症状与农技复核。",
    ],
    "雷电": [
        "立即停止露天作业，在安全建筑物内避险。",
        "远离孤立树木、金属农具、临时棚架和积水，不在雷电过程中施药。",
        "天气平稳、道路安全后再检查麦苗和排水情况。",
    ],
    "台风": [
        "及时关注当地应急与气象部门指引，提前收妥农资和工具。",
        "停止危险露天作业，远离易坠落物、积水和受损设施。",
        "天气平稳后检查积水、倒伏和折伤；按当地农技指导安排后续管理。",
    ],
    "沙尘暴": [
        "暂停露天作业并做好人员防护，避免在能见度差时赶往田间。",
        "提前收妥易被风吹动的农资；不要在强风沙尘中施药。",
        "天气好转后记录叶片擦伤、覆尘及倒伏等可见变化，再评估是否需处理。",
    ],
}
NOTICE = "天气预警提示防护与复查，不代表现场已发生病虫害或具备施药条件。建议为一般防护和观察方向，具体农业措施须结合生育期、墒情与当地农技意见。"


def ensure(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS weather_warning_events(id TEXT PRIMARY KEY,body TEXT NOT NULL,observed TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS weather_warning_latest(identifier TEXT PRIMARY KEY,event_id TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS weather_warning_deliveries(owner TEXT,event_id TEXT,subscription_id TEXT,created TEXT NOT NULL,PRIMARY KEY(owner,event_id))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS weather_warning_meta(id TEXT PRIMARY KEY,body TEXT NOT NULL)"
    )


def clock(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?",
        value,
    ):
        raise ValueError("explicit source clock required")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=personal.TZ)).astimezone(personal.TZ)


def source_link(value):
    p = urlsplit(value or PORTAL_URL)
    if (
        p.scheme != "https"
        or p.hostname not in ("weather.cma.cn", "www.cma.gov.cn", "www.weather.com.cn")
        or p.username
        or p.password
        or p.port not in (None, 443)
    ):
        return PORTAL_URL
    return value or PORTAL_URL


def normalize(item):
    if not isinstance(item, dict):
        raise ValueError("unsupported warning record")
    kind = item.get("typeName") or item.get("event")
    level = item.get("level")
    if level in ("Blue", "Yellow", "Orange", "Red"):
        level = {"Blue": "蓝色", "Yellow": "黄色", "Orange": "橙色", "Red": "红色"}[
            level
        ]
    if isinstance(level, str) and level in ("蓝", "黄", "橙", "红"):
        level += "色"
    if kind not in TYPES or level not in LEVELS:
        raise ValueError("unsupported warning category")
    identifier = item.get("identifier") or item.get("id")
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200:
        raise ValueError("warning identifier required")
    issued = clock(item.get("sent") or item.get("pubTime"))
    effective = clock(
        item.get("effective") or item.get("startTime") or issued.isoformat()
    )
    expires = clock(item.get("expires") or item.get("endTime"))
    if (
        not issued <= expires
        or not effective < expires
        or expires - issued > timedelta(days=7)
    ):
        raise ValueError("unbounded warning validity")
    codes = item.get("areaCodes")
    if (
        not isinstance(codes, list)
        or not codes
        or len(codes) > 500
        or any(
            not isinstance(x, str)
            or not re.fullmatch(r"\d{6}", x)
            or x[:2] not in PROVINCE_CODES.values()
            for x in codes
        )
    ):
        raise ValueError("explicit administrative scope required")
    publisher = item.get("senderName") or item.get("sender")
    title = item.get("headline") or item.get("title")
    if (
        not isinstance(publisher, str)
        or not publisher.strip()
        or len(publisher) > 200
        or not isinstance(title, str)
        or not title.strip()
        or len(title) > 300
    ):
        raise ValueError("source publisher and title required")
    action = item.get("msgType") or item.get("status") or "Alert"
    actions = {
        "Alert": "active",
        "Update": "active",
        "Cancel": "cancelled",
        "active": "active",
        "update": "active",
        "cancelled": "cancelled",
    }
    if action not in actions:
        raise ValueError("unsupported warning status")
    references = item.get("references", [])
    if not isinstance(references, list) or any(
        not isinstance(x, str) or len(x) > 200 for x in references
    ):
        raise ValueError("invalid references")
    result = {
        "identifier": identifier,
        "title": title,
        "publisher": publisher,
        "hazard": kind,
        "level": level,
        "rank": LEVELS[level],
        "issued_at": issued.isoformat(),
        "effective_at": effective.isoformat(),
        "expires_at": expires.isoformat(),
        "area_codes": sorted(set(codes)),
        "status": actions[action],
        "message_type": (
            "update"
            if action in ("Update", "update")
            else "cancel" if actions[action] == "cancelled" else "alert"
        ),
        "references": references,
        "description": str(item.get("description") or item.get("text") or "")[:5000],
        "source_url": source_link(item.get("web") or item.get("url")),
        "source": "中国气象局天气网站公开预警",
        "is_demo": False,
    }
    result["id"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:32]
    return result


def cap_records(content):
    # CAP is XML data; reject entity declarations and oversized input before parse.
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("unsupported XML declaration")
    root = ElementTree.fromstring(content)
    if root.tag.rsplit("}", 1)[-1] not in ("alert", "alerts", "feed"):
        raise ValueError("not a CAP document")

    def children(node, name):
        return [c for c in node.iter() if c.tag.rsplit("}", 1)[-1] == name]

    def value(node, name, default=""):
        values = children(node, name)
        return values[0].text or default if values else default

    alerts = (
        children(root, "alert") if root.tag.rsplit("}", 1)[-1] != "alert" else [root]
    )
    results = []
    if not alerts and children(root, "entry"):
        raise ValueError("linked CAP entries require a supported adapter")
    for alert in alerts:
        if value(alert, "status") != "Actual" or value(alert, "scope") != "Public":
            continue
        if value(alert, "msgType") == "Cancel" and not children(alert, "info"):
            refs = [
                r.split(",")[1]
                for r in value(alert, "references").split()
                if len(r.split(",")) == 3
            ]
            results.append(
                {
                    "identifier": value(alert, "identifier"),
                    "sender": value(alert, "sender"),
                    "sent": value(alert, "sent"),
                    "msgType": "Cancel",
                    "references": refs,
                }
            )
        for info in children(alert, "info"):
            if value(info, "language", "zh-CN") not in ("zh-CN", "zh"):
                continue
            codes = []
            for code in children(info, "geocode"):
                if value(code, "valueName") in ("GB/T 2260", "GB/T2260", "adcode"):
                    codes.append(value(code, "value"))
            event = value(info, "event")
            headline = value(info, "headline")
            hazard = next((t for t in TYPES if t in event), None)
            level = next((l for l in LEVELS if l in headline or l in event), None)
            refs = [
                r.split(",")[1]
                for r in value(alert, "references").split()
                if len(r.split(",")) == 3
            ]
            results.append(
                {
                    "identifier": value(alert, "identifier"),
                    "sender": value(alert, "sender"),
                    "senderName": value(info, "senderName"),
                    "sent": value(alert, "sent"),
                    "effective": value(info, "effective")
                    or value(info, "onset")
                    or value(alert, "sent"),
                    "expires": value(info, "expires"),
                    "typeName": hazard,
                    "level": level,
                    "headline": headline,
                    "description": value(info, "description")
                    + "\n"
                    + value(info, "instruction"),
                    "msgType": value(alert, "msgType"),
                    "areaCodes": codes,
                    "references": refs,
                    "web": value(info, "web"),
                }
            )
    return results


def fetch_records():
    with requests.get(
        SOURCE_URL,
        timeout=(5, 12),
        allow_redirects=False,
        stream=True,
        headers={"Accept": "application/json, application/cap+xml, application/xml"},
    ) as response:
        if response.status_code != 200:
            raise ValueError("official source unavailable")
        content = bytearray()
        for chunk in response.iter_content(16384):
            content.extend(chunk)
            if len(content) > 3_000_000:
                raise ValueError("official source too large")
        if bytes(content).lstrip().startswith(b"<"):
            return cap_records(bytes(content))
        data = json.loads(bytes(content).decode("utf-8-sig"))
        if not isinstance(data, dict) or data.get("code") not in (0, "0"):
            raise ValueError("invalid official response")
        payload = data.get("data")
        records = (
            payload.get("alerts")
            if isinstance(payload, dict) and "alerts" in payload
            else payload.get("data") if isinstance(payload, dict) else payload
        )
        if not isinstance(records, list) or len(records) > 5000:
            raise ValueError("unsupported official schema")
        # Explicit dictionaries with scope/time fields only; never guess array columns.
        return records


def set_meta(c, value):
    c.execute(
        "INSERT OR REPLACE INTO weather_warning_meta VALUES(?,?)",
        ("source", json.dumps(value, ensure_ascii=False)),
    )


def referenced_cancel(row):
    if not isinstance(row, dict) or row.get("msgType") != "Cancel":
        raise ValueError("not an explicit cancellation")
    refs = row.get("references")
    identifier = row.get("identifier")
    sender = row.get("senderName") or row.get("sender")
    if (
        not isinstance(refs, list)
        or not refs
        or any(not isinstance(r, str) or len(r) > 200 for r in refs)
        or not isinstance(identifier, str)
        or not 1 <= len(identifier) <= 200
        or not isinstance(sender, str)
        or not sender.strip()
    ):
        raise ValueError("invalid cancellation reference")
    sent = clock(row.get("sent") or row.get("pubTime"))
    with personal.db() as c:
        ensure(c)
        found = []
        for ref in refs:
            r = c.execute(
                "SELECT e.body FROM weather_warning_latest l JOIN weather_warning_events e ON e.id=l.event_id WHERE l.identifier=?",
                (ref,),
            ).fetchone()
            if r:
                found.append(json.loads(r["body"]))
    if not found or any(
        (d["hazard"], d["area_codes"]) != (found[0]["hazard"], found[0]["area_codes"])
        for d in found
    ):
        raise ValueError("ambiguous cancellation scope")
    original = found[0]
    if sent < clock(original["issued_at"]):
        raise ValueError("cancellation predates warning")
    result = {
        **original,
        "identifier": identifier,
        "title": row.get("headline")
        or "发布机构解除此前" + original["hazard"] + "预警",
        "publisher": sender,
        "issued_at": sent.isoformat(),
        "effective_at": sent.isoformat(),
        "expires_at": sent.isoformat(),
        "status": "cancelled",
        "message_type": "cancel",
        "references": refs,
        "validity_basis": "explicit_cancel_message_time",
        "description": str(row.get("description") or "")[:5000],
    }
    result.pop("id", None)
    result["id"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:32]
    return result


def refresh():
    state = {
        "checked_at": personal.now().isoformat(),
        "source_url": SOURCE_URL,
        "state": "ok",
        "accepted": 0,
        "rejected": 0,
    }
    try:
        records = fetch_records()
        parsed = []
        for row in records:
            try:
                parsed.append(normalize(row))
            except (ValueError, TypeError, KeyError, OverflowError):
                try:
                    parsed.append(referenced_cancel(row))
                except (ValueError, TypeError, KeyError, OverflowError):
                    state["rejected"] += 1
        if records and not parsed:
            state["state"] = "unsupported_source_schema"
        elif state["rejected"]:
            state["state"] = "partial"
        with personal.db() as c:
            ensure(c)
            c.execute("BEGIN IMMEDIATE")
            for item in parsed:
                if clock(item["issued_at"]) > personal.now() + timedelta(minutes=5):
                    continue
                prior = c.execute(
                    "SELECT e.body FROM weather_warning_latest l JOIN weather_warning_events e ON e.id=l.event_id WHERE l.identifier=?",
                    (item["identifier"],),
                ).fetchone()
                priority = {"alert": 0, "update": 1, "cancel": 2}
                if prior:
                    previous = json.loads(prior["body"])
                    previous_time = clock(previous["issued_at"])
                    incoming_time = clock(item["issued_at"])
                    if previous_time > incoming_time or (
                        previous_time == incoming_time
                        and priority.get(previous.get("message_type"), 0)
                        > priority.get(item.get("message_type"), 0)
                    ):
                        continue
                if (
                    item["status"] == "cancelled"
                    or item.get("message_type") == "update"
                ):
                    newer_reference = False
                    for reference in item["references"]:
                        previous = c.execute(
                            "SELECT e.body FROM weather_warning_latest l JOIN weather_warning_events e ON e.id=l.event_id WHERE l.identifier=?",
                            (reference,),
                        ).fetchone()
                        if previous and clock(
                            json.loads(previous["body"])["issued_at"]
                        ) > clock(item["issued_at"]):
                            newer_reference = True
                            break
                    if newer_reference:
                        continue
                c.execute(
                    "INSERT OR IGNORE INTO weather_warning_events VALUES(?,?,?)",
                    (
                        item["id"],
                        json.dumps(item, ensure_ascii=False),
                        personal.now().isoformat(),
                    ),
                )
                c.execute(
                    "INSERT OR REPLACE INTO weather_warning_latest VALUES(?,?)",
                    (item["identifier"], item["id"]),
                )
                if (
                    item["status"] == "cancelled"
                    or item.get("message_type") == "update"
                ):
                    for old in item["references"]:
                        c.execute(
                            "INSERT OR REPLACE INTO weather_warning_latest VALUES(?,?)",
                            (old, item["id"]),
                        )
                state["accepted"] += 1
            if state["state"] in ("ok", "partial"):
                state["last_success_at"] = personal.now().isoformat()
            else:
                old = c.execute(
                    "SELECT body FROM weather_warning_meta WHERE id='source'"
                ).fetchone()
                if old:
                    state["last_success_at"] = json.loads(old["body"]).get(
                        "last_success_at"
                    )
            set_meta(c, state)
    except Exception:
        state["state"] = "unavailable"
        with personal.db() as c:
            ensure(c)
            old = c.execute(
                "SELECT body FROM weather_warning_meta WHERE id='source'"
            ).fetchone()
            if old:
                state["last_success_at"] = json.loads(old["body"]).get(
                    "last_success_at"
                )
            set_meta(c, state)
    return state


def metadata(c):
    ensure(c)
    r = c.execute("SELECT body FROM weather_warning_meta WHERE id='source'").fetchone()
    return (
        json.loads(r["body"])
        if r
        else {"state": "not_checked", "source_url": SOURCE_URL, "last_success_at": None}
    )


def fresh(meta):
    try:
        return (
            meta.get("state") in ("ok", "partial")
            and timedelta(0)
            <= personal.now() - clock(meta["last_success_at"])
            <= MAX_AGE
        )
    except (ValueError, TypeError, KeyError):
        return False


def relevant(item, sub):
    prefix = PROVINCE_CODES.get(sub["province"])
    target = sub.get("weather_adcode") or ""
    if (
        item["hazard"] not in sub.get("weather_types", [])
        or item["rank"] < LEVELS[sub.get("weather_min_level", "蓝色")]
    ):
        return False
    for code in item["area_codes"]:
        if code[:2] != prefix:
            continue
        if code.endswith("0000"):
            return True
        if not sub["city"]:
            return True
        if target and (
            target.endswith("0000")
            or code == target
            or target.endswith("00")
            and code[:4] == target[:4]
            or code.endswith("00")
            and target[:4] == code[:4]
        ):
            return True
    return False


def valid(item):
    return (
        item["status"] == "active"
        and clock(item["issued_at"]) <= personal.now() + timedelta(minutes=5)
        and clock(item["effective_at"]) <= personal.now() < clock(item["expires_at"])
    )


def latest(c):
    return [
        json.loads(r["body"])
        for r in c.execute(
            "SELECT DISTINCT e.body FROM weather_warning_latest l JOIN weather_warning_events e ON e.id=l.event_id"
        )
    ]


def active_for(who, subscription_id=None):
    subs = [
        s
        for s in agri_sources.subscriptions(who)
        if s["enabled"]
        and s.get("weather_enabled")
        and (not subscription_id or s["id"] == subscription_id)
    ]
    with personal.db() as c:
        meta = metadata(c)
        items = [
            i
            for i in latest(c)
            if fresh(meta) and valid(i) and any(relevant(i, s) for s in subs)
        ]
    return {
        "source": {
            **meta,
            "state": (
                "stale"
                if meta.get("state") in ("ok", "partial") and not fresh(meta)
                else meta["state"]
            ),
            "usable": fresh(meta),
        },
        "warnings": [
            {**i, "advice": ADVICE[i["hazard"]], "notice": NOTICE} for i in items
        ],
        "notice": "没有匹配预警不代表天气无风险；来源不可用时不能推断没有预警。",
    }


def deliver():
    with personal.db() as c:
        agri_sources.ensure(c)
        ensure(c)
        c.execute("BEGIN IMMEDIATE")
        meta = metadata(c)
        if not fresh(meta):
            return
        subs = [
            {"owner": r["owner"], "id": r["id"], **json.loads(r["body"])}
            for r in c.execute("SELECT * FROM region_subscriptions")
        ]
        for item in sorted(latest(c), key=lambda i: i["rank"], reverse=True):
            if item["status"] != "cancelled" and not valid(item):
                continue
            if item["status"] == "cancelled" and personal.now() - clock(
                item["issued_at"]
            ) > timedelta(hours=24):
                continue
            for sub in subs:
                if (
                    not sub["enabled"]
                    or not sub.get("weather_enabled")
                    or not relevant(item, sub)
                ):
                    continue
                if c.execute(
                    "SELECT 1 FROM weather_warning_deliveries WHERE owner=? AND event_id=?",
                    (sub["owner"], item["id"]),
                ).fetchone():
                    continue
                # A cancellation is useful only for users who saw the warning or its references.
                seen = c.execute(
                    "SELECT e.body FROM weather_warning_deliveries d JOIN weather_warning_events e ON e.id=d.event_id WHERE d.owner=?",
                    (sub["owner"],),
                ).fetchall()
                family = {item["identifier"], *item["references"]}
                related = [
                    json.loads(r["body"])
                    for r in seen
                    if json.loads(r["body"])["identifier"] in family
                ]
                if item["status"] == "cancelled" and not related:
                    continue
                urgent = (
                    item["rank"] >= 3
                    and sub.get("weather_urgent", False)
                    and (not related or item["rank"] > max(i["rank"] for i in related))
                )
                if agri_sources.quiet(sub, personal.now()) and not urgent:
                    continue
                day = (
                    personal.now()
                    .replace(hour=0, minute=0, second=0, microsecond=0)
                    .isoformat()
                )
                count = c.execute(
                    "SELECT count(*) FROM weather_warning_deliveries WHERE owner=? AND created>=?",
                    (sub["owner"], day),
                ).fetchone()[0]
                if (
                    count >= sub["max_daily"]
                    and not urgent
                    and item["status"] != "cancelled"
                ):
                    continue
                change = (
                    "解除"
                    if item["status"] == "cancelled"
                    else (
                        "升级"
                        if related and item["rank"] > max(i["rank"] for i in related)
                        else "更新" if related else "发布"
                    )
                )
                payload = {
                    "name": f"天气预警{change} · {item['hazard']}{item['level']}",
                    "message": item["title"]
                    + "。"
                    + (
                        "发布机构已发送解除信息，请继续核对当地实况。"
                        if change == "解除"
                        else ADVICE[item["hazard"]][0]
                    ),
                    "task_type": "weather_alert",
                    "created_at": personal.now().isoformat(),
                    "read": False,
                    "is_demo": False,
                    "warning_id": item["id"],
                    "warning": item,
                    "advice": ADVICE[item["hazard"]],
                    "subscription_id": sub["id"],
                    "quiet_start": sub["quiet_start"],
                    "quiet_end": sub["quiet_end"],
                    "urgent": urgent,
                    "notice": NOTICE,
                }
                for previous in c.execute(
                    "SELECT id,body FROM entries WHERE owner=? AND kind='notifications'",
                    (sub["owner"],),
                ).fetchall():
                    body = json.loads(previous["body"])
                    if (
                        body.get("task_type") == "weather_alert"
                        and body.get("warning", {}).get("identifier") in family
                    ):
                        body["superseded"] = True
                        c.execute(
                            "UPDATE entries SET body=? WHERE owner=? AND id=?",
                            (
                                json.dumps(body, ensure_ascii=False),
                                sub["owner"],
                                previous["id"],
                            ),
                        )
                c.execute(
                    "INSERT INTO entries VALUES(?,?,?,?,?)",
                    (
                        sub["owner"],
                        "weather-" + secrets.token_hex(16),
                        "notifications",
                        json.dumps(payload, ensure_ascii=False),
                        "",
                    ),
                )
                c.execute(
                    "INSERT INTO weather_warning_deliveries VALUES(?,?,?,?)",
                    (sub["owner"], item["id"], sub["id"], personal.now().isoformat()),
                )


@router.get("/status")
def status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return active_for(personal.owner(request)) | {
        "hazards": TYPES,
        "levels": list(LEVELS),
        "source_portal": PORTAL_URL,
        "interval_seconds": INTERVAL,
    }


class Demo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscription_id: str = Field(default="", max_length=80)
    hazard: str = "暴雨"
    level: str = "橙色"
    action: str = "发布"


@router.post("/demo")
def demo(item: Demo, request: Request, response: Response):
    import memory

    who = memory.write_owner(request)
    if (
        item.hazard not in TYPES
        or item.level not in LEVELS
        or item.action not in ("发布", "升级", "解除")
    ):
        raise HTTPException(400, "请选择支持的演示情景")
    sub = (
        next(
            (
                s
                for s in agri_sources.subscriptions(who)
                if s["id"] == item.subscription_id
            ),
            None,
        )
        if item.subscription_id
        else None
    )
    if item.subscription_id and not sub:
        raise HTTPException(404, "该地区订阅不属于当前身份")
    region = (
        (sub["province"] + " " + sub["city"]).strip()
        if sub
        else "示例地区（未指定实际地区）"
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "id": "demo-" + secrets.token_hex(8),
        "is_demo": True,
        "name": f"演示 · {item.hazard}{item.level}预警{item.action}",
        "message": f"【演示情景】假设{region}出现{item.hazard}{item.level}预警{item.action}。这不代表当地正在发生灾害或收到真实官方预警。",
        "region": region,
        "task_type": "weather_alert",
        "hazard": item.hazard,
        "level": item.level,
        "action": item.action,
        "created_at": personal.now().isoformat(),
        "advice": ADVICE[item.hazard],
        "notice": NOTICE,
        "source": "演示情景，非官方发布",
        "source_url": PORTAL_URL,
        "persisted": False,
    }


def start():
    stop = threading.Event()

    def loop():
        next_fetch = personal.now()
        while not stop.is_set():
            try:
                with personal.db() as c:
                    agri_sources.ensure(c)
                    ensure(c)
                    enabled = any(
                        json.loads(r["body"]).get("enabled")
                        and json.loads(r["body"]).get("weather_enabled")
                        for r in c.execute("SELECT body FROM region_subscriptions")
                    )
                if enabled and personal.now() >= next_fetch:
                    refresh()
                    next_fetch = personal.now() + timedelta(seconds=INTERVAL)
                if enabled:
                    deliver()
            except Exception:
                logging.getLogger("uvicorn.error").warning(
                    "weather_warning_worker_failed; no warning inferred"
                )
            stop.wait(10)

    threading.Thread(target=loop, daemon=True).start()
    return stop
