"""Agent 编排循环的单元测试（mock llm.chat，不依赖真实大模型，不联网）。

验证 ReAct 循环的核心逻辑：
1. 模型先要工具、再回答 -> 最终返回答案，且工具结果被拼回上下文。
2. 模型连续多轮都要工具 -> 循环在 MAX_TOOL_ITERATIONS 处强制收尾，不报错。
3. 模型输出非 JSON 乱码 -> 兜底为纯文本回答，不抛异常。
4. 模型输出 {"action":"answer","content":...} -> 正确取出 content。
5. 模型调用未注册的工具 -> 工具错误作为结果回传，模型拿到第二次机会。

运行方式（在 back_end 目录下）：
    venv/Scripts/python.exe test_agent.py
"""

import agent
import config
import llm


def _make_chat(script: list):
    """返回一个假 llm.chat，按顺序弹出 script 里的预设回复，超出则返回默认文本。"""
    calls = []

    def fake(messages):
        calls.append(messages)
        return script.pop(0) if script else "默认回答"

    return fake, calls


def _system_text(calls, index):
    return calls[index][0]["content"]


def run():
    # 场景 1：tool -> answer，工具结果拼回上下文
    llm.chat, calls = _make_chat([
        '{"action":"tool","tool":"get_weather","args":{"location":"郑州"}}',
        '{"action":"answer","content":"郑州近期天气晴好，适合浇水。"}',
    ])
    answer = agent.run([{"role": "user", "content": "查一下郑州天气，判断要不要浇水"}])
    assert answer == "郑州近期天气晴好，适合浇水。", answer
    assert "get_weather" in _system_text(calls, 0), "系统提示词未包含工具清单"
    second = "\n".join(m.get("content", "") for m in calls[1])
    assert "【工具执行结果】" in second, "工具结果未拼回第二轮上下文"
    assert "模拟" in second, "无密钥时应回退模拟天气"
    print("[PASS] 1 tool -> answer 循环，工具结果被拼回上下文")

    # 场景 2：连续要工具 -> 循环超限强制收尾
    tool_msg = '{"action":"tool","tool":"get_weather","args":{"location":"郑州"}}'
    llm.chat, calls = _make_chat([tool_msg] * config.MAX_TOOL_ITERATIONS)
    answer = agent.run([{"role": "user", "content": "天气"}])
    assert answer == "默认回答", answer
    assert len(calls) == config.MAX_TOOL_ITERATIONS + 1, f"调用次数异常: {len(calls)}"
    print("[PASS] 2 连续调用工具在循环上限处强制收尾，不报错")

    # 场景 3：非 JSON 乱码 -> 当作纯文本回答
    llm.chat, calls = _make_chat(["这是一段不是JSON的普通回答。"])
    answer = agent.run([{"role": "user", "content": "你好"}])
    assert answer == "这是一段不是JSON的普通回答。", answer
    print("[PASS] 3 非 JSON 输出兜底为纯文本回答，不抛异常")

    # 场景 4：JSON answer -> 正确取出 content
    llm.chat, calls = _make_chat(['{"action":"answer","content":"最终回答文本"}'])
    answer = agent.run([{"role": "user", "content": "你好"}])
    assert answer == "最终回答文本", answer
    print("[PASS] 4 JSON answer 正确取出 content")

    # 场景 5：调用未注册工具 -> 错误作为结果回传，模型有第二次机会
    llm.chat, calls = _make_chat([
        '{"action":"tool","tool":"no_such_tool","args":{}}',
        '{"action":"answer","content":"工具不可用，我基于已有信息回答。"}',
    ])
    answer = agent.run([{"role": "user", "content": "帮我查个东西"}])
    assert answer == "工具不可用，我基于已有信息回答。", answer
    second = "\n".join(m.get("content", "") for m in calls[1])
    assert "未知工具" in second, "未注册工具的错误信息应回传模型"
    print("[PASS] 5 未注册工具的错误被回传，模型获得第二次机会")

    # 场景 6：多工具协同（先天气后土壤），两条工具结果都进入最终上下文
    llm.chat, calls = _make_chat([
        '{"action":"tool","tool":"get_weather","args":{"location":"郑州"}}',
        '{"action":"tool","tool":"get_soil","args":{"location":"郑州"}}',
        '{"action":"answer","content":"结合天气与墒情，近期无需浇水。"}',
    ])
    answer = agent.run([{"role": "user", "content": "判断是否要浇水"}])
    assert answer == "结合天气与墒情，近期无需浇水。", answer
    system = _system_text(calls, 0)
    assert "get_weather" in system and "get_soil" in system, "系统提示词应包含多个工具"
    third = "\n".join(m.get("content", "") for m in calls[2])
    assert "土壤" in third, "第二条工具（土壤）结果应拼回上下文"
    print("[PASS] 6 多工具协同，天气与土壤结果均拼回上下文")

    print("\n全部 Agent 编排循环测试通过")


if __name__ == "__main__":
    run()
