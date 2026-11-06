"""Save current, explicit user reports of medicines; never infer stock from images."""

import json
import re
import secrets
import unicodedata

import personal
from pesticides import number_info

OWNERSHIP = re.compile(
    r"(?:^|[，,、。.!！；;：:\s])(?:我(?:们)?(?:现在|目前|这里|这儿|这|家里|家|手里|手头|手上)?"
    r"(?:现在|目前|手里|手头|手上)?(?:还)?有|我(?:手里|手头|手上|家里|这里)(?:的)?(?:农药|药品|药)?(?:是|叫)|"
    r"(?:我(?:们)?)?(?:刚刚|刚|已经|已|最近)?买(?:到|了|回来)|(?:家里|手里|手头|手上)(?:还)?有)"
)
BOUNDARY = re.compile(
    r"[。.!！?？；;\n]|但|不过|[，,](?=(?:我(?:想|打算|准备|没|不)|"
    r"邻居|别人|朋友|他|她|你|能|可以|请|帮|想))"
)
UNSAFE_CONTEXT = re.compile(
    r"如果|假如|假设|比如|例如|例句|示例|台词|转述|引用|(?:他|她|邻居|朋友|别人)(?:说|表示|告诉我|：|:)|"
    r"[“\"「『]\s*我|不要.{0,12}(?:保存|记录|添加|入库)|别.{0,8}(?:保存|记录|添加|入库)|"
    r"不用.{0,8}(?:保存|记录|添加|入库)|不(?:想|要|需要).{0,8}(?:保存|记录|添加|入库)"
)


def ownership_spans(message):
    """Conservative clauses: a question, purchase plan or third party isn't stock."""
    if UNSAFE_CONTEXT.search(message):
        return []
    spans = []
    for match in OWNERSHIP.finditer(message):
        tail = message[match.end() :]
        boundary = BOUNDARY.search(tail)
        clause = tail[: boundary.start()] if boundary else tail
        if boundary and boundary.group()[0] in "?？":
            continue
        # Split at question punctuation, but reject a question about possession.
        if re.search(
            r"什么|哪些|哪种|吗|么|是否|有没有|可能|好像|也许|没有|没买|用完|送人|退了|邻居|别人|朋友|[他她]的|想买|准备买|打算买|建议买|推荐",
            clause,
        ):
            continue
        spans.append(message[match.start() : match.end()] + clause)
    return spans


def key(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def save_reported(who, message, medicines_json):
    if not who:
        return {
            "status": "unavailable",
            "message": "个人资料尚未连接，未保存农药，请刷新页面重试。",
        }
    try:
        proposed = json.loads(medicines_json)
        if not isinstance(proposed, list) or not 1 <= len(proposed) <= 10:
            raise ValueError()
        spans = ownership_spans(message)
        items = []
        for row in proposed:
            if not isinstance(row, dict) or set(row) - {
                "name",
                "number",
                "source_quote",
            }:
                raise ValueError()
            name, number, quote = (
                row.get("name"),
                row.get("number", ""),
                row.get("source_quote"),
            )
            if not all(isinstance(x, str) for x in (name, number, quote)):
                raise ValueError()
            name, number = name.strip(), number.strip().upper()
            if (
                len(name) < 2
                or name
                in {
                    "农药",
                    "药品",
                    "杀菌剂",
                    "除草剂",
                    "杀虫剂",
                    "这瓶药",
                    "一瓶药",
                    "什么药",
                }
                or not quote
                or quote not in message
                or name not in quote
            ):
                raise ValueError()
            if not any(
                name in span and quote.strip() in span.strip() for span in spans
            ):
                raise ValueError()
            # Numbers must be user-written, not copied from observations/history.
            if number and (
                number_info(number)["number_status"] != "recognized_format"
                or number not in quote.upper()
            ):
                raise ValueError()
            items.append(
                personal.Entry(
                    name=name,
                    number=number,
                    notes="对话记录（用户自述，登记待核对）：" + quote,
                )
            )
    except (ValueError, TypeError):
        return {
            "status": "needs_clarification",
            "message": "未添加农药。请明确说出你目前实际持有的药名；询问、假设、他人用药和未确认的图片文字不会自动入库。登记号不知道可以先留空。",
        }

    saved = []
    with personal.db() as c:
        c.execute("BEGIN IMMEDIATE")
        existing = [
            dict(r)
            for r in c.execute(
                "SELECT id,body FROM entries WHERE owner=? AND kind='medicines'", (who,)
            ).fetchall()
        ]
        for item in items:
            same_number = [
                r
                for r in existing
                if item.number
                and key(json.loads(r["body"]).get("number", "")) == key(item.number)
            ]
            same_name = [
                r
                for r in existing
                if key(json.loads(r["body"])["name"]) == key(item.name)
            ]
            match = next(iter(same_number), None)
            if not match and not item.number:
                match = next(iter(same_name), None)
            # Only enrich a single name-only record; don't overwrite known labels.
            enrich = (
                not match
                and bool(item.number)
                and len(same_name) == 1
                and not json.loads(same_name[0]["body"]).get("number")
            )
            if enrich:
                match = same_name[0]
                body = {
                    **json.loads(match["body"]),
                    "number": item.number,
                    "_revision": secrets.token_hex(12),
                }
                match["body"] = json.dumps(body, ensure_ascii=False)
                c.execute(
                    "UPDATE entries SET body=? WHERE owner=? AND id=? AND kind='medicines'",
                    (match["body"], who, match["id"]),
                )
            if match:
                saved.append(
                    {
                        "id": match["id"],
                        "name": json.loads(match["body"])["name"],
                        "number": json.loads(match["body"]).get("number", ""),
                        "action": "updated" if enrich else "existing",
                    }
                )
                continue
            if len(existing) >= 100:
                # Roll back the whole batch rather than silently saving half.
                raise personal.HTTPException(
                    400, "农药库已达100条，请先删除不需要的记录后再添加。"
                )
            identifier = "chat-med-" + secrets.token_hex(12)
            body = json.dumps(
                {**item.model_dump(), "_revision": secrets.token_hex(12)},
                ensure_ascii=False,
            )
            c.execute(
                "INSERT INTO entries VALUES(?,?,?,?,?)",
                (who, identifier, "medicines", body, ""),
            )
            existing.append({"id": identifier, "body": body})
            saved.append(
                {
                    "id": identifier,
                    "name": item.name,
                    "number": item.number,
                    "action": "added",
                }
            )
    return {
        "status": "saved",
        "medicines": saved,
        "source_type": "user_reported",
        "message": "药品资料已保存到“我的农药库”，重复药品不再新增。未知登记号留空；入库不代表允许使用，可在农药库编辑或删除。",
    }
