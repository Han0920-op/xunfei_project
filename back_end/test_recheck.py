"""后端聊天持久化 + 历史案例复查 数据闭环测试（不依赖真实大模型与视觉接口）。

验证：
1. 多轮问答后消息持久化，可按会话 ID 读回。
2. 首次诊断后，案例关联到会话（conversation_id）。
3. 复查时给已有案例追加复查记录，不覆盖原诊断结论。
4. 第二次复查后，两次复查记录都保留。
5. 旧案例没有 conversation_id 时详情返回 None，不报错。
6. 不同案例关联到不同会话。

运行方式（在 back_end 目录下）：
    venv/Scripts/python.exe test_recheck.py
"""

import asyncio
from io import BytesIO

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import UploadFile

import llm
import main
from database import Base
from main import ChatRequest


def build_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def make_upload_file():
    return UploadFile(
        file=BytesIO(b"fake-image-bytes"),
        filename="test.jpg",
        headers={"content-type": "image/jpeg"},
    )


def run():
    Session = build_session_factory()
    main.understand_image = lambda image_bytes, question: "叶片发黄，有红褐色锈斑。"
    main._save_image = lambda image_bytes, content_type, filename: "/uploads/test.jpg"

    # 场景 1：多轮问答，消息持久化，可按会话 ID 读回
    llm.chat = lambda messages: "这是AI回复"
    db = Session()
    r1 = main.chat(ChatRequest(message="第一问"), db)
    cid = r1.conversation_id
    main.chat(ChatRequest(message="追问", conversation_id=cid), db)
    db.close()

    db = Session()
    msgs = main.conversation_messages(cid, db)
    db.close()
    assert len(msgs) == 4, f"应有 4 条消息，实际 {len(msgs)}"
    assert [m.role for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0].content == "第一问"
    assert msgs[2].content == "追问"
    print("[PASS] 1 多轮问答消息持久化，可按会话 ID 读回")

    # 场景 2：首次诊断后，案例关联到会话
    llm.chat = lambda messages: "疑似条锈病，建议喷施三唑酮。"
    db = Session()
    up = asyncio.run(main.upload_image(file=make_upload_file(), question="描述", case_id=None, db=db))
    case_id = up["case_id"]
    db.close()

    db = Session()
    r = main.chat(ChatRequest(message="请诊断", vision_result="叶片发黄", case_id=case_id), db)
    cid = r.conversation_id
    db.close()

    db = Session()
    case = db.get(main.Case, case_id)
    assert case.conversation_id == cid, f"案例应关联会话 {cid}"
    assert case.diagnosis == "疑似条锈病，建议喷施三唑酮。"
    assert case.status == "进行中"
    detail = main.history_detail(case_id, db)
    assert detail.conversation_id == cid
    db.close()
    print("[PASS] 2 首次诊断后案例关联会话，详情返回 conversation_id")

    # 场景 3：复查——给已有案例追加复查记录，不覆盖原结论
    llm.chat = lambda messages: "复查结论：叶面病斑减少，长势好转。"
    db = Session()
    up2 = asyncio.run(main.upload_image(file=make_upload_file(), question="描述", case_id=case_id, db=db))
    assert up2["case_id"] == case_id, "复查模式不应新建案例"
    image_path = up2["image_path"]
    db.close()

    db = Session()
    main.chat(ChatRequest(
        message="复查：现在情况如何",
        vision_result="新识别：叶片转绿",
        case_id=case_id,
        conversation_id=cid,
        image_path=image_path,
    ), db)
    db.close()

    db = Session()
    case = db.get(main.Case, case_id)
    assert case.diagnosis == "疑似条锈病，建议喷施三唑酮。", "原诊断结论不应被覆盖"
    rechecks = main.history_rechecks(case_id, db)
    assert len(rechecks) == 1, f"应有 1 条复查记录，实际 {len(rechecks)}"
    assert rechecks[0].diagnosis == "复查结论：叶面病斑减少，长势好转。"
    assert rechecks[0].image == image_path
    detail = main.history_detail(case_id, db)
    assert detail.recheck_count == 1
    assert detail.last_recheck_time is not None
    db.close()
    print("[PASS] 3 复查追加记录，原结论不被覆盖，详情返回最近复查时间")

    # 场景 4：第二次复查后，两次复查记录都保留
    db = Session()
    up3 = asyncio.run(main.upload_image(file=make_upload_file(), question="描述", case_id=case_id, db=db))
    image_path3 = up3["image_path"]
    db.close()
    db = Session()
    main.chat(ChatRequest(
        message="第二次复查",
        vision_result="新识别2",
        case_id=case_id,
        conversation_id=cid,
        image_path=image_path3,
    ), db)
    db.close()
    db = Session()
    rechecks = main.history_rechecks(case_id, db)
    assert len(rechecks) == 2, f"两次复查都应保留，实际 {len(rechecks)}"
    db.close()
    print("[PASS] 4 第二次复查后，两次复查记录都保留")

    # 场景 5：旧案例没有 conversation_id，详情安全返回 None
    db = Session()
    old = main.Case(image_path="/uploads/old.jpg", summary="旧案例", recognition="旧识别",
                    status="已完成", diagnosis="旧诊断")
    db.add(old)
    db.commit()
    db.refresh(old)
    old_id = old.id
    db.close()

    db = Session()
    detail = main.history_detail(old_id, db)
    assert detail.conversation_id is None
    db.close()
    print("[PASS] 5 旧案例无 conversation_id，详情安全返回 None")

    # 场景 6：不同案例关联到不同会话
    llm.chat = lambda messages: "诊断B"
    db = Session()
    upB = asyncio.run(main.upload_image(file=make_upload_file(), question="描述", case_id=None, db=db))
    caseB_id = upB["case_id"]
    db.close()
    db = Session()
    rB = main.chat(ChatRequest(message="诊断", vision_result="叶片发黄", case_id=caseB_id), db)
    cidB = rB.conversation_id
    db.close()
    assert cidB != cid, "不同案例不应共用同一个会话"
    print("[PASS] 6 不同案例关联到不同会话")

    print("\n全部聊天持久化 + 复查闭环测试通过")


if __name__ == "__main__":
    run()
