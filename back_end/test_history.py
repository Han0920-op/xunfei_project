"""后端历史案例数据闭环测试（不依赖真实大模型与视觉接口，不触碰真实数据库）。

验证：
1. 图片上传后案例入库（识别描述、状态正确，诊断结论为空）。
2. 历史列表能查到新案例。
3. 详情能按案例 ID 查回正确字段，且无诊断结果时不报错。
4. 首次诊断（带 vision_result + case_id）后，结论写回案例、状态保持「进行中」。
5. 诊断失败时案例状态标记为「失败」。

运行方式（在 back_end 目录下）：
    venv/Scripts/python.exe test_history.py
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
    """内存 SQLite，测试结束即销毁，不碰 chat_history.db。"""
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

    # 替换真实视觉 / 图片落盘调用，避免依赖讯飞接口与磁盘。
    main.understand_image = lambda image_bytes, question: "叶片发黄，有红褐色锈斑。"
    main._save_image = lambda image_bytes, content_type, filename: "/uploads/test.jpg"

    # 场景 1：上传图片 → 案例入库，识别描述保存、状态「进行中」、诊断结论为空
    db = Session()
    result = asyncio.run(
        main.upload_image(file=make_upload_file(), question="请描述小麦生长状况", case_id=None, db=db)
    )
    case_id = result["case_id"]
    assert case_id is not None
    case = db.get(main.Case, case_id)
    assert case.recognition == "叶片发黄，有红褐色锈斑。"
    assert case.status == "进行中"
    assert case.diagnosis == ""
    db.close()
    print("[PASS] 1 上传后案例入库：识别描述保存、状态为进行中、结论为空")

    # 场景 2：历史列表能查到新案例
    db = Session()
    items = main.history_list(db)
    assert case_id in [i.id for i in items]
    db.close()
    print("[PASS] 2 历史列表能查到新案例")

    # 场景 3：详情按 ID 查回正确字段，无诊断结果时不报错
    db = Session()
    detail = main.history_detail(case_id, db)
    assert detail.id == case_id
    assert detail.recognition == "叶片发黄，有红褐色锈斑。"
    assert detail.diagnosis == ""
    assert detail.status == "进行中"
    db.close()
    print("[PASS] 3 详情字段与同一条记录正确对应，无诊断结果时不报错")

    # 场景 4：首次诊断 → 结论写回案例，状态保持「进行中」（仍在跟踪，等待手动结束）
    llm.chat = lambda messages: "疑似条锈病，建议喷施三唑酮。"
    db = Session()
    resp = main.chat(
        ChatRequest(
            message="请诊断",
            vision_result="叶片发黄，有红褐色锈斑。",
            case_id=case_id,
        ),
        db,
    )
    db.close()
    assert resp.case_id == case_id
    db = Session()
    case = db.get(main.Case, case_id)
    assert case.diagnosis == "疑似条锈病，建议喷施三唑酮。"
    assert case.status == "进行中"
    db.close()
    print("[PASS] 4 首次诊断后结论写回案例，状态保持进行中")

    # 场景 5：诊断失败 → 案例状态标记为「失败」
    def fail_chat(messages):
        raise llm.LLMError("模拟大模型调用失败")

    llm.chat = fail_chat
    db = Session()
    result2 = asyncio.run(
        main.upload_image(file=make_upload_file(), question="请描述", case_id=None, db=db)
    )
    case_id2 = result2["case_id"]
    db.close()

    db = Session()
    try:
        main.chat(
            ChatRequest(
                message="请诊断",
                vision_result="叶片发黄",
                case_id=case_id2,
            ),
            db,
        )
        raise AssertionError("应当抛出异常")
    except Exception:
        pass
    db.close()

    db = Session()
    case2 = db.get(main.Case, case_id2)
    assert case2.status == "失败"
    db.close()
    print("[PASS] 5 诊断失败时案例状态标记为失败")

    print("\n全部历史案例数据闭环测试通过")


if __name__ == "__main__":
    run()
