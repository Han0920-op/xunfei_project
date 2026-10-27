"""Agent 编排循环（Prompt 驱动 ReAct）。

核心流程：把「系统提示词 + 工具清单 + 历史 + 当前用户消息」组装好交给大模型，
模型输出决策 JSON：
  - {"action":"tool","tool":"get_weather","args":{...}}  -> 执行工具，把结果拼回对话再问
  - 其它任何输出（或 {"action":"answer","content":"..."}） -> 当作最终回答
循环最多 MAX_TOOL_ITERATIONS 轮，超限强制收尾，防止死循环。
解析失败一律回退为纯文本回答，绝不因为 JSON 解析异常让整个请求 502。
"""

import json
import re
from typing import Iterator, Optional

import config
import llm
import tools
from pesticides import format_check_answer

# 输出格式说明（追加到系统提示词末尾，告诉模型怎么用工具）。
_DECISION_PROTOCOL = (
    "【输出规则】\n"
    "- 需要调用工具时：只输出一行 JSON，不要输出其它任何文字：\n"
    '  {"action":"tool","tool":"工具名","args":{参数}}\n'
    "- 不需要工具、可以直接回答时：直接输出给用户的自然语言回答，不要输出 JSON。"
)


def build_system_prompt() -> str:
    """组装 Agent 系统提示词 = 角色设定 + 工具清单 + 输出规则。"""
    return "\n\n".join([config.AGENT_SYSTEM_PROMPT, tools.tools_prompt(), _DECISION_PROTOCOL])


def _extract_json(text: str) -> Optional[dict]:
    """尽量从一段文本里抠出一个 JSON 对象：先整体解析，再剥代码块，再截取首尾大括号。"""
    text = (text or "").strip()
    if not text:
        return None
    # 去掉 ```json ... ``` 代码块包裹
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _iter(messages: list[dict]) -> Iterator[dict]:
    """生成事件序列：{"type":"tool_call"|"tool_result"|"delta", ...}。

    messages 为「历史 + 当前用户消息」（不含 system，system 在这里注入）。
    """
    conversation = [{"role": "system", "content": build_system_prompt()}, *messages]

    for _ in range(config.MAX_TOOL_ITERATIONS):
        reply = llm.chat(conversation)
        data = _extract_json(reply)

        # 只有「明确是 tool 动作的 JSON」才当工具调用。
        if isinstance(data, dict) and data.get("action") == "tool" and data.get("tool"):
            name = data["tool"]
            args = data.get("args") or {}
            yield {"type": "tool_call", "tool": name, "args": args}
            result = tools.execute(name, args)
            yield {"type": "tool_result", "tool": name, "result": result}
            if name == "check_pesticide":
                # Registration verdicts are program facts, not model paraphrases.
                yield {"type": "delta", "content": format_check_answer(result)}
                return
            # 把「模型的调用决策」和「工具返回结果」都拼回上下文，让模型基于结果继续。
            conversation.append({"role": "assistant", "content": reply})
            conversation.append({"role": "user", "content": f"【工具执行结果】\n{result}"})
            continue

        # 其它情况一律当最终回答：优先取 JSON 里的 content 字段，否则用原文。
        content = reply or ""
        if isinstance(data, dict) and isinstance(data.get("content"), str):
            content = data["content"]
        yield {"type": "delta", "content": content}
        return

    # 循环超限：强制让模型直接收尾，不再调用工具。
    final = llm.chat(
        conversation + [{"role": "user", "content": "请直接给出最终回答，不要再调用任何工具。"}]
    )
    yield {"type": "delta", "content": final}


def run(messages: list[dict]) -> str:
    """非流式：执行完整循环，返回最终回答文本。"""
    parts = []
    for event in _iter(messages):
        if event["type"] == "delta":
            parts.append(event["content"])
    return "".join(parts)


def run_stream(messages: list[dict]) -> Iterator[dict]:
    """流式：同样的事件序列，但把最终回答切成小块，方便前端逐段渲染。"""
    for event in _iter(messages):
        if event["type"] != "delta":
            yield event
            continue
        content = event["content"]
        for i in range(0, len(content), 40):
            yield {"type": "delta", "content": content[i:i + 40]}
