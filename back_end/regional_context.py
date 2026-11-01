"""Owned subscription context for chat; a reference region is not a photo location."""

import json
from fastapi import HTTPException, Request, Response
import agri_sources
import personal

NOTICE = "地区来自用户订阅，仅作回答参考；不证明照片拍摄地、现场发生病害或具备施药条件。当前文字明确的其他地点优先。"


def options(who):
    return [
        {
            "id": s["id"],
            "province": s["province"],
            "city": s["city"],
            "pests": s["pests"],
        }
        for s in agri_sources.subscriptions(who)
        if s["enabled"]
    ]


def matches(source, selected):
    if selected["province"] not in source.get("regions", []):
        return False
    cities = source.get("cities", [])
    if cities and selected["city"].removesuffix("市") not in {
        city.removesuffix("市") for city in cities
    }:
        return False
    return bool(set(source.get("pests", [])) & set(selected["pests"]))


def context(who, selected_id=""):
    if not who:
        return {
            "status": "not_connected",
            "selected": None,
            "options": [],
            "bulletins": [],
            "notice": NOTICE,
        }
    items = options(who)
    selected = None
    if selected_id == "none":
        status = "disabled"
    elif selected_id:
        selected = next((s for s in items if s["id"] == selected_id), None)
        if not selected:
            raise HTTPException(
                409, "参考地区订阅已暂停、删除或不可用，请重新选择本次参考地区。"
            )
        status = "selected"
    elif len(items) == 1:
        selected = items[0]
        status = "selected"
    else:
        status = "needs_selection" if items else "no_subscription"
    bulletins = []
    if selected:
        for d in sorted(
            agri_sources.documents(), key=lambda x: x["published_on"], reverse=True
        ):
            if (
                d["kind"] == "bulletin"
                and agri_sources.applicable(d)
                and matches(d, selected)
            ):
                bulletins.append(agri_sources.public(d))
                if len(bulletins) >= 3:
                    break
    return {
        "status": status,
        "selected": selected,
        "options": items,
        "bulletins": bulletins,
        "notice": NOTICE,
    }


def prompt_context(data):
    # Only metadata is supplied, not operator notes or official raw text. Treat
    # free-text city input as data, never as instructions or confirmed location.
    selected = data.get("selected")
    return {
        "status": data["status"],
        "source_type": "user_subscription_reference",
        "resolved_at": personal.now().isoformat(),
        "selected": selected,
        "candidate_regions": (
            data["options"] if data["status"] == "needs_selection" else []
        ),
        "official_signals": [
            {
                "title": b["title"],
                "url": b["url"],
                "published_on": b["published_on"],
                "valid_until": b["valid_until"],
                "regions": b["regions"],
                "cities": b.get("cities", []),
                "pests": b["pests"],
                "retrieved_at": b["retrieved_at"],
                "agronomic_review": b["agronomic_review"],
            }
            for b in data["bulletins"]
        ],
        "notice": NOTICE,
        "limitations": "没有有效情报不表示没有风险；订阅病虫害不表示现场发生。天气必须重新调用真实工具；省级地区不能推算城市天气；未接入专门气象灾害预警。",
    }


@agri_sources.router.get("/chat-context")
def read_context(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return context(personal.owner(request))
