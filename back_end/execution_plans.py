"""Owned execution plans. Current unreviewed data permits investigation steps only."""

import hashlib
import json
from typing import Literal
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, ConfigDict, Field
import memory, personal
from web_search import safe_url

router = APIRouter(prefix="/api/plans")
ACTIONS = {
    "photograph": (
        "补拍关键部位",
        "拍摄异常部位近景、全株和邻近正常植株，保留拍摄日期。",
        "现场安全、光线清晰时",
    ),
    "observe": (
        "记录异常变化",
        "记录异常部位、分布、新叶或麦穗变化；避免仅凭颜色判断病因或药效。",
        "本次观察及下一次复查时",
    ),
    "confirm_context": (
        "补充现场信息",
        "核对实际地点、拍摄时间、生育期及近期真实采取的措施。",
        "进一步判断前",
    ),
    "check_label": (
        "核对药品标签",
        "核对包装完整登记号、作物、防治对象和有效标签；未核实前不据此安排施药。",
        "考虑使用农药之前",
    ),
    "consult": (
        "请农技人员复核",
        "携带案例照片、变化记录和药品标签请当地农技人员鉴别原因。",
        "异常加重、扩大或证据不足时",
    ),
    "followup": (
        "安排复查",
        "在原案例补图并记录改善、无变化、恶化或尚不确定；可另行确认设置提醒。",
        "由用户确定合适的复查时间",
    ),
}


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=6, max_length=40)
    crop: str = Field(default="待确认", max_length=40)
    region: str = Field(default="待确认", max_length=80)
    growth_stage: str = Field(default="待确认", max_length=40)
    steps: list[
        Literal[
            "photograph",
            "observe",
            "confirm_context",
            "check_label",
            "consult",
            "followup",
        ]
    ] = Field(min_length=1, max_length=6)


def ensure(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS execution_plans(id TEXT PRIMARY KEY,owner TEXT NOT NULL,case_id TEXT NOT NULL,turn_id TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(owner,case_id,turn_id))"
    )


def save(who, case_id, turn_id, payload, current_tools=None, current_message=""):
    if not who or not case_id or not turn_id:
        return {
            "status": "needs_case",
            "message": "请先完成并保存一次诊断对话，再生成执行方案。",
        }
    spec = PlanInput.model_validate_json(payload)
    case = memory.get_case(who, case_id)
    if case["archived"]:
        return {"status": "needs_case", "message": "请先重新打开案例。"}
    user_reports = (
        "\n".join(t["user"]["text"] for t in case["turns"])
        + "\n"
        + "\n".join(f["content"] for f in case["facts"])
    )
    user_reports += "\n" + current_message
    grounded = lambda value: (
        value if value != "待确认" and value in user_reports else "待确认"
    )
    refs = []
    seen = set()
    for turn in [*case["turns"], {"assistant": {"toolResults": current_tools or []}}]:
        for t in turn["assistant"].get("toolResults", []):
            r = t.get("result", {})
            for entry in r.get("results", []):
                source = entry.get("source") or entry
                url = safe_url(source.get("url", ""))
                if url and url not in seen:
                    refs.append(
                        {
                            "title": source.get("title", "参考资料"),
                            "url": url,
                            "published_on": source.get("published_on", ""),
                            "notice": source.get("notice", "适用性待核对"),
                        }
                    )
                    seen.add(url)
    steps = [
        {
            "number": i + 1,
            "title": ACTIONS[a][0],
            "operation": ACTIONS[a][1],
            "condition": ACTIONS[a][2],
            "completed": False,
        }
        for i, a in enumerate(dict.fromkeys(spec.steps))
    ]
    identifier = hashlib.sha256(f"{who}:{case_id}:{turn_id}".encode()).hexdigest()[:32]
    stamp = personal.now().isoformat()
    body = {
        "id": identifier,
        "case_id": case_id,
        "case_title": case["title"],
        "title": "排查方案：" + spec.title,
        "created_at": stamp,
        "user_id": hashlib.sha256(who.encode()).hexdigest()[:16],
        "crop": grounded(spec.crop),
        "region": grounded(spec.region),
        "growth_stage": grounded(spec.growth_stage),
        "problem": case["turns"][0]["user"]["text"],
        "diagnosis_summary": case["turns"][-1]["assistant"]["text"],
        "suspected_diseases": case.get("state", {}).get("candidate_causes", []),
        "uncertainty": "诊断摘要是模型初步判断，疑似病害待农技复核；未核实的信息不作为确诊。",
        "goal": "补齐证据、核对风险并持续复查",
        "steps": steps,
        "precautions": [
            "本方案为排查与核实方案，不含未经核验的施药指令。",
            "完成步骤不代表作物已恢复健康。",
        ],
        "references": refs[:10],
        "status": "pending",
    }
    with memory.db() as c:
        ensure(c)
        c.execute("BEGIN IMMEDIATE")
        row = memory.owned(c, who, case_id)
        if row["archived"]:
            raise HTTPException(409, "案例已结束")
        c.execute(
            "INSERT OR IGNORE INTO execution_plans VALUES(?,?,?,?,?,?)",
            (
                identifier,
                who,
                case_id,
                turn_id,
                json.dumps(body, ensure_ascii=False),
                stamp,
            ),
        )
        saved = json.loads(
            c.execute(
                "SELECT body FROM execution_plans WHERE id=? AND owner=?",
                (identifier, who),
            ).fetchone()["body"]
        )
    return {
        "status": "saved",
        "plan_id": identifier,
        "title": saved["title"],
        "message": "执行方案已保存到“我的记录→执行方案”。",
        "url": "plans.html?id=" + identifier,
    }


@router.get("")
def listing(request: Request, response: Response):
    who = personal.owner(request)
    response.headers["Cache-Control"] = "no-store"
    with memory.db() as c:
        ensure(c)
        return [
            json.loads(r["body"])
            for r in c.execute(
                "SELECT p.body FROM execution_plans p JOIN memory_cases m ON p.case_id=m.id AND p.owner=m.owner WHERE p.owner=? ORDER BY p.created DESC LIMIT 200",
                (who,),
            )
        ]


@router.get("/{identifier}")
def read(identifier: str, request: Request, response: Response):
    who = personal.owner(request)
    response.headers["Cache-Control"] = "no-store"
    with memory.db() as c:
        ensure(c)
        row = c.execute(
            "SELECT * FROM execution_plans WHERE id=? AND owner=?", (identifier, who)
        ).fetchone()
        if not row:
            raise HTTPException(404, "方案不存在或不属于当前身份")
        memory.owned(c, who, row["case_id"])
        return json.loads(row["body"])
