"""Validate the title generated with the first response, persist once after success."""

import re
import memory


def choose(candidate, message, vision):
    if isinstance(candidate, str):
        title = candidate.strip()
        if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·]{6,15}", title) and not any(
            w in title for w in ("确诊", "治愈", "健康", "正常", "无病")
        ):
            if any(
                w in title for w in ("赤霉病", "锈病", "白粉病", "纹枯病", "根腐病")
            ) and not any(w in title for w in ("疑似", "排查", "待确认")):
                return "小麦疑似病害排查"
            return title
    if any(w in message for w in ("农药", "登记", "核药")):
        return "农药登记信息核验"
    if vision:
        return "作物异常照片排查"
    return "农事问题咨询记录"


def save_once(who, case_id, candidate, message, vision):
    with memory.db() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS case_titles(case_id TEXT PRIMARY KEY,owner TEXT NOT NULL)"
        )
        c.execute("BEGIN IMMEDIATE")
        row = memory.owned(c, who, case_id)
        # Never rename old/multi-turn cases or override a manually edited title.
        count = c.execute(
            "SELECT count(*) FROM memory_turns WHERE owner=? AND case_id=?",
            (who, case_id),
        ).fetchone()[0]
        if (
            count == 1
            and row["title"] == "新诊断"
            and c.execute(
                "INSERT OR IGNORE INTO case_titles VALUES(?,?)", (case_id, who)
            ).rowcount
        ):
            title = choose(candidate, message, vision)
            c.execute(
                "UPDATE memory_cases SET title=? WHERE id=? AND owner=?",
                (title, case_id, who),
            )
            return title
        return row["title"]
