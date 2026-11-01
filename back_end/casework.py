"""Sourced case state, private compressed photos, reports and follow-up feedback."""

import hashlib
import html
import json
import secrets
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
import personal

router = APIRouter(prefix="/api/casework")
STATUSES = (
    "collecting",
    "needs_information",
    "assessing",
    "followup",
    "escalated",
    "closed",
)
TRANSITIONS = {
    "collecting": set(STATUSES) - {"collecting"},
    "needs_information": {"assessing", "followup", "escalated", "closed"},
    "assessing": {"needs_information", "followup", "escalated", "closed"},
    "followup": {"assessing", "needs_information", "escalated", "closed"},
    "escalated": {"assessing", "followup", "closed"},
    "closed": {"collecting"},
}


def ensure(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS case_states(case_id TEXT PRIMARY KEY,owner TEXT NOT NULL,body TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS case_events(id TEXT PRIMARY KEY,owner TEXT NOT NULL,case_id TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS case_photos(id TEXT NOT NULL,owner TEXT NOT NULL,case_id TEXT NOT NULL,content BLOB NOT NULL,uploaded TEXT NOT NULL,captured TEXT,PRIMARY KEY(owner,id))"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS case_reports(id TEXT PRIMARY KEY,owner TEXT NOT NULL,case_id TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL)"
    )


def blank():
    return {
        "status": "collecting",
        "reported_symptoms": [],
        "assessment": None,
        "evidence": [],
        "clarification_rounds": 0,
        "review_required": False,
        "updated_at": personal.now().isoformat(),
    }


def read_state(c, who, case_id):
    ensure(c)
    row = c.execute(
        "SELECT body FROM case_states WHERE owner=? AND case_id=?", (who, case_id)
    ).fetchone()
    if row:
        return json.loads(row["body"])
    state = blank()
    old = c.execute(
        "SELECT archived FROM memory_cases WHERE owner=? AND id=?", (who, case_id)
    ).fetchone()
    if old and old["archived"]:
        state["status"] = "closed"
    return state


def put_state(c, who, case_id, state):
    state["updated_at"] = personal.now().isoformat()
    c.execute(
        "INSERT INTO case_states VALUES(?,?,?) ON CONFLICT(case_id) DO UPDATE SET body=excluded.body",
        (case_id, who, json.dumps(state, ensure_ascii=False)),
    )


def event(c, who, case_id, kind, body, event_id=None):
    c.execute(
        "INSERT OR IGNORE INTO case_events VALUES(?,?,?,?,?,?)",
        (
            event_id or secrets.token_hex(16),
            who,
            case_id,
            kind,
            json.dumps(body, ensure_ascii=False),
            personal.now().isoformat(),
        ),
    )


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)
    symptoms: str = Field(default="", max_length=2000)
    growth_stage: str = Field(default="", max_length=100)
    candidate_causes: list[str] = Field(default_factory=list, max_length=5)
    missing_information: list[str] = Field(default_factory=list, max_length=2)
    review_required: bool = False


def prepare_assessment(who, case_id, value):
    import memory

    assessment = Assessment.model_validate(value)
    if any(
        len(s) > 200
        for s in assessment.candidate_causes + assessment.missing_information
    ):
        raise ValueError("assessment too long")
    with memory.db() as c:
        row = c.execute(
            "SELECT owner FROM memory_cases WHERE id=?", (case_id,)
        ).fetchone()
        if row and row["owner"] != who:
            raise HTTPException(404)
        old = read_state(c, who, case_id)
    if assessment.missing_information and old["clarification_rounds"] >= 2:
        assessment.review_required = True
    return assessment.model_dump()


def add_turn(
    c,
    who,
    case_id,
    turn_id,
    message,
    vision,
    tools,
    image_bytes=None,
    photo_id="",
    assessment=None,
    regional_context=None,
):
    state = read_state(c, who, case_id)
    if regional_context is not None:
        state["reference_region"] = regional_context
    if state["status"] == "closed":
        state["status"] = "collecting"
    state["reported_symptoms"] = (
        state["reported_symptoms"]
        + [
            {
                "text": message[:2000],
                "source_type": "user_reported",
                "at": personal.now().isoformat(),
            }
        ]
    )[-20:]
    if assessment:
        parsed = Assessment.model_validate(assessment)
        state["assessment"] = {
            **parsed.model_dump(),
            "source_type": "model_inference",
            "confirmed": False,
        }
        if parsed.missing_information:
            state["clarification_rounds"] += 1
        state["review_required"] = (
            state["review_required"]
            or parsed.review_required
            or state["clarification_rounds"] >= 3
        )
        state["status"] = (
            "escalated"
            if state["review_required"]
            else "needs_information" if parsed.missing_information else "assessing"
        )
    for t in tools:
        r = t.get("result", {})
        if t["tool"] in ("search_knowledge", "search_agri_guidelines"):
            for item in r.get("results", [])[:5]:
                source = item.get("source", {})
                state["evidence"].append(
                    {
                        "id": item.get("id")
                        or "e-"
                        + hashlib.sha256(
                            json.dumps(
                                item, sort_keys=True, ensure_ascii=False
                            ).encode()
                        ).hexdigest()[:16],
                        "kind": (
                            "official_guideline"
                            if t["tool"] == "search_agri_guidelines"
                            else "uploaded_observation"
                        ),
                        "quote": item.get("quote", "")[:3000],
                        "topic": item.get("topic", ""),
                        "source": source,
                        "review_status": item.get("review_status", "pending_review"),
                        "retrieved_at": r.get("retrieved_at"),
                    }
                )
        elif t["tool"] == "check_pesticide":
            state["evidence"].append(
                {
                    "id": "registration-" + turn_id,
                    "kind": "registration_check",
                    "result": r,
                    "source": r.get("source"),
                }
            )
        elif t["tool"] == "get_weather":
            state["evidence"].append(
                {
                    "id": "weather-" + turn_id,
                    "kind": "dated_weather",
                    "result": r,
                    "retrieved_at": r.get("retrieved_at"),
                }
            )
    # Preserve source metadata and deduplicate exact evidence IDs, newest first.
    state["evidence"] = list({e["id"]: e for e in state["evidence"]}.values())[-50:]
    if image_bytes:
        if (
            c.execute(
                "SELECT count(*) FROM case_photos WHERE owner=? AND case_id=?",
                (who, case_id),
            ).fetchone()[0]
            >= 100
        ):
            raise HTTPException(400, "每个案例最多100张照片，请整理后再保存")
        photo_id = photo_id or secrets.token_hex(16)
        prior = c.execute(
            "SELECT case_id,content FROM case_photos WHERE owner=? AND id=?",
            (who, photo_id),
        ).fetchone()
        if prior and (
            prior["case_id"] != case_id or bytes(prior["content"]) != image_bytes
        ):
            raise HTTPException(409, "照片编号已用于其他照片或案例，请重新选择照片")
        c.execute(
            "INSERT OR IGNORE INTO case_photos VALUES(?,?,?,?,?,NULL)",
            (photo_id, who, case_id, image_bytes, personal.now().isoformat()),
        )
        event(
            c,
            who,
            case_id,
            "photo_observation",
            {
                "photo_id": photo_id,
                "observations": vision,
                "source_type": "visual_inference",
                "capture_date_known": False,
            },
            "photo-" + turn_id,
        )
    event(
        c,
        who,
        case_id,
        "consultation",
        {
            "user_description": message[:2000],
            "assessment": state["assessment"],
            "evidence_ids": [e["id"] for e in state["evidence"]],
            "source_type": "mixed_sources_explicit",
        },
        "consult-" + turn_id,
    )
    put_state(c, who, case_id, state)


def snapshot(who, case_id):
    import memory

    with memory.db() as c:
        memory.owned(c, who, case_id)
        state = read_state(c, who, case_id)
        events = [
            {
                "id": r["id"],
                "kind": r["kind"],
                "created_at": r["created"],
                **json.loads(r["body"]),
            }
            for r in c.execute(
                "SELECT * FROM case_events WHERE owner=? AND case_id=? ORDER BY created DESC,rowid DESC LIMIT 100",
                (who, case_id),
            )
        ]
        photos = [
            {
                "id": r["id"],
                "name": "诊断照片",
                "date": r["uploaded"],
                "uploaded_at": r["uploaded"],
                "captured_at": r["captured"],
                "serverUrl": f'/api/casework/cases/{case_id}/photos/{r["id"]}',
            }
            for r in c.execute(
                "SELECT id,uploaded,captured FROM case_photos WHERE owner=? AND case_id=? ORDER BY uploaded",
                (who, case_id),
            )
        ]
    return {
        "state": state,
        "events": events,
        "photos": photos,
        "allowed_statuses": sorted(TRANSITIONS[state["status"]] | {state["status"]}),
    }


@router.get("/cases/{case_id}")
def case_state(case_id: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return snapshot(personal.owner(request), case_id)


@router.get("/cases/{case_id}/photos/{photo_id}")
def photo(case_id: str, photo_id: str, request: Request):
    import memory

    who = personal.owner(request)
    with memory.db() as c:
        memory.owned(c, who, case_id)
        ensure(c)
        r = c.execute(
            "SELECT content FROM case_photos WHERE owner=? AND case_id=? AND id=?",
            (who, case_id, photo_id),
        ).fetchone()
        if not r:
            raise HTTPException(404)
    return Response(
        bytes(r["content"]),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/cases/{case_id}/photos")
async def upload_photo(case_id: str, request: Request, image: UploadFile = File(...)):
    import memory
    from chat_api import prepare_image, MAX_IMAGE_BYTES

    who = memory.write_owner(request)
    with memory.db() as c:
        memory.owned(c, who, case_id)
    try:
        raw = await image.read(MAX_IMAGE_BYTES + 1)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "照片为空或超过10MB")
        clean = prepare_image(raw, image.content_type)
    finally:
        await image.close()
    identifier = secrets.token_hex(16)
    with memory.db() as c:
        memory.owned(c, who, case_id)
        ensure(c)
        if (
            c.execute(
                "SELECT count(*) FROM case_photos WHERE owner=? AND case_id=?",
                (who, case_id),
            ).fetchone()[0]
            >= 100
        ):
            raise HTTPException(400, "每个案例最多100张照片")
        c.execute(
            "INSERT INTO case_photos VALUES(?,?,?,?,?,NULL)",
            (identifier, who, case_id, clean, personal.now().isoformat()),
        )
        event(
            c,
            who,
            case_id,
            "photo_uploaded",
            {
                "photo_id": identifier,
                "source_type": "user_uploaded",
                "capture_date_known": False,
            },
        )
    return {"saved": True, "photo_id": identifier}


class StateChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[
        "collecting",
        "needs_information",
        "assessing",
        "followup",
        "escalated",
        "closed",
    ]


def cancel_case_tasks(c, who, case_id, remove=False):
    if remove:
        for row in c.execute(
            "SELECT id,body FROM entries WHERE owner=? AND kind='notifications'", (who,)
        ).fetchall():
            if json.loads(row["body"]).get("case_id") == case_id:
                c.execute(
                    "DELETE FROM entries WHERE owner=? AND id=?", (who, row["id"])
                )
    for r in c.execute(
        "SELECT * FROM entries WHERE owner=? AND kind='tasks'", (who,)
    ).fetchall():
        body = json.loads(r["body"])
        if body.get("case_id") != case_id:
            continue
        if remove:
            c.execute("DELETE FROM entries WHERE owner=? AND id=?", (who, r["id"]))
        else:
            body.update(enabled=False, _revision=secrets.token_hex(12))
            c.execute(
                "UPDATE entries SET body=?,next=? WHERE owner=? AND id=?",
                (json.dumps(body, ensure_ascii=False), "", who, r["id"]),
            )
        c.execute("DELETE FROM jobs WHERE owner=? AND task_id=?", (who, r["id"]))


@router.put("/cases/{case_id}/state")
def change_state(case_id: str, item: StateChange, request: Request):
    import memory

    who = memory.write_owner(request)
    with memory.db() as c:
        c.execute("BEGIN IMMEDIATE")
        memory.owned(c, who, case_id)
        state = read_state(c, who, case_id)
        if (
            item.status != state["status"]
            and item.status not in TRANSITIONS[state["status"]]
        ):
            raise HTTPException(409, "请按当前案例进度更新状态")
        state["status"] = item.status
        if item.status == "escalated":
            state["review_required"] = True
        put_state(c, who, case_id, state)
        c.execute(
            "UPDATE memory_cases SET archived=? WHERE owner=? AND id=?",
            (int(item.status == "closed"), who, case_id),
        )
        if item.status == "closed":
            cancel_case_tasks(c, who, case_id)
        event(
            c,
            who,
            case_id,
            "status_changed",
            {
                "status": item.status,
                "source_type": "user_confirmed",
                "notice": "结束观察不等于治愈",
            },
        )
    return {"saved": True, "state": state}


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    change: Literal["improved", "unchanged", "worse", "unclear"]
    notes: str = Field(default="", max_length=2000)
    measures: str = Field(default="", max_length=2000)


@router.post("/cases/{case_id}/feedback")
def feedback(case_id: str, item: Feedback, request: Request):
    import memory

    who = memory.write_owner(request)
    with memory.db() as c:
        c.execute("BEGIN IMMEDIATE")
        case = memory.owned(c, who, case_id)
        state = read_state(c, who, case_id)
        if case["archived"]:
            raise HTTPException(409, "请先重新打开案例")
        state["status"] = (
            "escalated"
            if item.change == "worse" or state["review_required"]
            else "followup"
        )
        state["review_required"] = state["review_required"] or item.change == "worse"
        put_state(c, who, case_id, state)
        event(
            c,
            who,
            case_id,
            "followup_feedback",
            {
                **item.model_dump(),
                "source_type": "user_confirmed",
                "notice": "改善属于用户反馈，不能证明药效",
            },
        )
        if item.measures:
            if (
                c.execute(
                    "SELECT count(*) FROM memory_facts WHERE owner=? AND case_id=?",
                    (who, case_id),
                ).fetchone()[0]
                >= 30
            ):
                raise HTTPException(400, "已确认资料达到30条，请先整理旧资料")
            c.execute(
                "INSERT INTO memory_facts VALUES(?,?,?,?,?,?)",
                (
                    secrets.token_hex(16),
                    who,
                    case_id,
                    "复查时确认的实际措施",
                    item.measures,
                    personal.now().isoformat(),
                ),
            )
    return {"saved": True, "state": state}


def compare(who, case_id, current=None):
    data = snapshot(who, case_id)
    observations = [
        e
        for e in reversed(data["events"])
        if e["kind"] == "photo_observation"
        and any(v.get("status") == "ok" for v in e.get("observations", []))
    ]
    if current:
        observations.append(
            {
                "observations": [{"status": "ok", "content": current}],
                "source_type": "visual_inference",
                "pending_save": True,
                "capture_date_known": False,
            }
        )
    return {
        "status": "ok" if len(observations) >= 2 else "insufficient_evidence",
        "before": observations[-2] if len(observations) >= 2 else None,
        "after": observations[-1] if observations else None,
        "feedback": [e for e in data["events"] if e["kind"] == "followup_feedback"][:5],
        "limitations": "仅比较可见观察与用户反馈；照片光照、角度、位置和拍摄日期可能不同，不能仅凭照片认定药效或自动升级用药。",
    }


@router.get("/cases/{case_id}/comparison")
def comparison(case_id: str, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return compare(personal.owner(request), case_id)


def build_report(who, case_id):
    import memory

    data = snapshot(who, case_id)
    case = memory.get_case(who, case_id)
    state = data["state"]
    checks = []
    references = []
    import agri_sources

    source_by_id = {d["id"]: d for d in agri_sources.documents()}
    for evidence in state["evidence"]:
        if evidence["kind"] == "registration_check":
            r = evidence["result"]
            checks.append(
                {
                    "kind": "registration",
                    "status": r.get("use_decision", "hold_for_verification"),
                    "reasons": r.get("reason_codes", []),
                }
            )
        source = evidence.get("source") or {}
        if evidence["kind"] == "official_guideline":
            latest = source_by_id.get(evidence["id"])
            valid = bool(
                latest
                and latest["sha256"] == source.get("sha256")
                and agri_sources.applicable(latest)
            )
            checks.append(
                {
                    "kind": "guideline_applicability",
                    "evidence_id": evidence["id"],
                    "status": (
                        "source_applicable_not_agronomically_reviewed"
                        if valid
                        else "hold_expired_changed_or_unverified"
                    ),
                    "action_allowed": False,
                }
            )
        if source:
            references.append(
                {
                    "evidence_id": evidence["id"],
                    "quote": evidence.get("quote", ""),
                    "source": source,
                    "review_status": evidence.get("review_status", "pending_review"),
                }
            )
    guideline_sources = [
        r["source"] for r in references if r["source"].get("id") in source_by_id
    ]
    overlapping = []
    for index, left in enumerate(guideline_sources):
        for right in guideline_sources[index + 1 :]:
            if left.get("id") != right.get("id") and set(left.get("pests", [])) & set(
                right.get("pests", [])
            ):
                overlapping.append([left["id"], right["id"]])
    if overlapping:
        checks.append(
            {
                "kind": "source_consistency",
                "status": "hold_multiple_guidelines_require_comparison",
                "pairs": overlapping,
                "notice": "多个来源涉及相同对象，需逐条比较生育期、地区和适用条件，不能拼接为处方。",
            }
        )
    verified = [r for r in references if r["review_status"] == "agronomically_reviewed"]
    reasons = ["登记当前有效性与完整标签尚未形成可核验用药许可。"]
    if overlapping:
        reasons.append(
            "存在涉及相同病虫害的多个来源，适用条件和潜在冲突尚需人工逐条核对。"
        )
    if not verified:
        reasons.append("缺少已完成农技审校且适用于本次情况的指导资料。")
    if not state["assessment"]:
        reasons.append("尚未形成结构化候选原因和缺失证据记录。")
    report = {
        "id": secrets.token_hex(16),
        "case_id": case_id,
        "title": case["title"],
        "created_at": personal.now().isoformat(),
        "status": state["status"],
        "reference_region": state.get("reference_region"),
        "user_confirmed_facts": case["facts"],
        "reported_symptoms": state["reported_symptoms"],
        "possible_causes": (state["assessment"] or {}).get("candidate_causes", []),
        "cause_source": "模型候选推测，未确诊",
        "references": references,
        "rule_checks": checks,
        "uncertainties": reasons,
        "next_steps": [
            "补充异常部位、全株及近期变化，记录实际措施；明显恶化或证据冲突时请农技人员现场复核。"
        ],
        "missing_evidence": (state["assessment"] or {}).get("missing_information", []),
        "review_required": state["review_required"],
        "medication_decision": {
            "allowed": False,
            "decision": "hold_for_verification",
            "notice": "本报告不提供未经核验的剂量、混配、施药次数或间隔。",
        },
        "comparison": compare(who, case_id),
        "notice": "辅助观察与核对报告，不是确诊或处方；每项引用保留来源和审校状态。",
    }
    with memory.db() as c:
        memory.owned(c, who, case_id)
        ensure(c)
        c.execute(
            "INSERT INTO case_reports VALUES(?,?,?,?,?)",
            (
                report["id"],
                who,
                case_id,
                json.dumps(report, ensure_ascii=False),
                report["created_at"],
            ),
        )
        event(
            c,
            who,
            case_id,
            "report_created",
            {
                "report_id": report["id"],
                "source_type": "deterministic_report",
                "medication_allowed": False,
            },
        )
    return report


@router.post("/cases/{case_id}/reports")
def report(case_id: str, request: Request):
    import memory

    return build_report(memory.write_owner(request), case_id)


@router.get("/cases/{case_id}/reports/{report_id}")
def read_report(case_id: str, report_id: str, request: Request, response: Response):
    import memory

    with memory.db() as c:
        memory.owned(c, personal.owner(request), case_id)
        ensure(c)
        r = c.execute(
            "SELECT body FROM case_reports WHERE owner=? AND case_id=? AND id=?",
            (personal.owner(request), case_id, report_id),
        ).fetchone()
        if not r:
            raise HTTPException(404)
    response.headers["Cache-Control"] = "no-store"
    return json.loads(r["body"])


@router.get("/cases/{case_id}/reports/{report_id}/print", response_class=HTMLResponse)
def print_report(case_id: str, report_id: str, request: Request):
    import memory

    with memory.db() as c:
        who = personal.owner(request)
        memory.owned(c, who, case_id)
        ensure(c)
        row = c.execute(
            "SELECT body FROM case_reports WHERE owner=? AND case_id=? AND id=?",
            (who, case_id, report_id),
        ).fetchone()
        if not row:
            raise HTTPException(404)
    report = json.loads(row["body"])
    escape = html.escape
    sections = [
        ("地区订阅参考（不代表照片所在地）", report.get("reference_region")),
        ("已确认事实", report["user_confirmed_facts"]),
        ("用户症状描述", report["reported_symptoms"]),
        ("候选原因（模型推测）", report["possible_causes"]),
        ("引用及适用条件", report["references"]),
        ("规则核对", report["rule_checks"]),
        ("不确定性", report["uncertainties"]),
        ("下一步", report["next_steps"]),
        ("前后观察与局限", report["comparison"]),
    ]
    content = "".join(
        "<section><h2>"
        + escape(name)
        + "</h2><pre>"
        + escape(json.dumps(value, ensure_ascii=False, indent=2))
        + "</pre></section>"
        for name, value in sections
    )
    return HTMLResponse(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>智麦案例报告</title><style>body{max-width:900px;margin:40px auto;padding:24px;color:#254f37;font:16px/1.8 sans-serif}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{break-inside:avoid;border-top:1px solid #ddd}h1{font-size:26px}</style><h1>'
        + escape(report["title"])
        + "</h1><p>"
        + escape(report["created_at"])
        + "</p><p>"
        + escape(report["notice"])
        + "</p><p>"
        + escape(report["medication_decision"]["notice"])
        + "</p>"
        + content
        + "</html>",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
        },
    )
