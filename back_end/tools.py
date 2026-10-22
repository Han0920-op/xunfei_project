"""工具注册表与内置工具（天气 / 土壤 / 知识库占位）。

每个工具 = 名称 + 用途描述 + 参数 JSON Schema + 执行函数。
模型通过「Prompt 驱动 ReAct」决定是否调用工具，本文件只负责「注册 + 执行」，
不关心模型怎么决策（决策循环在 agent.py）。

天气数据源：优先高德天气真实 API（需 WEATHER_API_KEY），未配置 / 请求失败 /
地点未收录时回退到内置「模拟」数据，并在结果里带 source 字段标注。
"""

import json
from dataclasses import dataclass
from typing import Callable

import requests

import config


@dataclass
class Tool:
    name: str
    description: str                 # 给模型看的用途说明
    parameters: dict                 # 参数 JSON Schema（给模型看）
    func: Callable[..., str]         # 执行函数，返回 JSON 字符串结果
    simulated: bool = False          # 结果是否恒为模拟数据


TOOLS: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """把工具挂到全局注册表，后续 Agent 循环按名称查找执行。"""
    TOOLS[tool.name] = tool


def tools_prompt() -> str:
    """把注册表渲染成注入系统提示词的工具清单。"""
    if not TOOLS:
        return "（当前没有可用工具）"
    lines = ["可用工具清单："]
    for i, tool in enumerate(TOOLS.values(), start=1):
        params = json.dumps(tool.parameters, ensure_ascii=False)
        lines.append(
            f"{i}. {tool.name}\n"
            f"   用途：{tool.description}\n"
            f"   参数：{params}"
        )
    return "\n".join(lines)


def execute(name: str, args: dict) -> str:
    """按名称执行工具，返回 JSON 字符串结果；任何错误都封装成 JSON 回传，不抛异常。

    这样设计是为了让「工具失败」也能作为一条普通结果拼回对话，交给模型决定
    修正参数还是放弃调用，而不是让整个诊断请求 502。
    """
    tool = TOOLS.get(name)
    if tool is None:
        return json.dumps(
            {"error": f"未知工具「{name}」，可选工具：{list(TOOLS.keys())}"},
            ensure_ascii=False,
        )
    try:
        return tool.func(**(args or {}))
    except TypeError as exc:
        return json.dumps({"error": f"工具参数错误：{exc}"}, ensure_ascii=False)
    except Exception as exc:  # 工具内部出错也不打断 Agent 循环
        return json.dumps({"error": f"工具执行失败：{exc}"}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 天气工具
# ---------------------------------------------------------------------------
# 主要小麦产区 + 常用城市 → 高德行政区编码（adcode）。查不到就走模拟。
_LOCATION_ADCODE = {
    "郑州": "410100", "河南": "410000",
    "济南": "370100", "山东": "370000",
    "石家庄": "130100", "河北": "130000",
    "南京": "320100", "江苏": "320000",
    "合肥": "340100", "安徽": "340000",
    "西安": "610100", "陕西": "610000",
    "武汉": "420100", "湖北": "420000",
    "北京": "110000", "天津": "120000",
    "上海": "310000", "重庆": "500000",
    "成都": "510100", "四川": "510000",
    "太原": "140100", "山西": "140000",
    "兰州": "620100", "甘肃": "620000",
}


def _mock_weather(location: str) -> str:
    """内置的小麦产区模拟天气，字段与真实源对齐，明确标注「模拟」。"""
    return json.dumps(
        {
            "location": location,
            "weather": "晴间多云",
            "temperature": "18~26℃",
            "wind": "东南风 2-3级",
            "precipitation": "未来3天无明显降水",
            "forecast": [
                {"date": "今天", "day": "晴", "temp": "18~26℃"},
                {"date": "明天", "day": "多云", "temp": "17~24℃"},
                {"date": "后天", "day": "阴", "temp": "16~23℃"},
            ],
            "source": "模拟",
            "note": "未配置真实天气密钥或查询失败，返回内置模拟数据",
        },
        ensure_ascii=False,
    )


def _precipitation_text(casts: list) -> str:
    parts = []
    for c in casts:
        wx = f"{c.get('dayweather', '')}/{c.get('nightweather', '')}"
        parts.append(f"{c.get('date', '')} {wx}")
    return "未来几天：" + "；".join(parts)


def _real_weather(location: str, adcode: str) -> str:
    """调用高德天气（extensions=all 返回预报），裁剪成小麦管理关心的字段。"""
    url = "https://restapi.amap.com/v3/weather/weatherInfo"
    try:
        resp = requests.get(
            url,
            params={"city": adcode, "key": config.WEATHER_API_KEY, "extensions": "all"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"请求高德天气失败：{exc}") from exc
    resp.encoding = "utf-8"
    data = resp.json()
    if data.get("status") != "1":
        raise RuntimeError(data.get("info", "高德天气接口返回错误"))
    forecast = (data.get("forecasts") or [{}])[0]
    casts = forecast.get("casts") or []
    if not casts:
        raise RuntimeError("天气接口未返回预报数据")

    today = casts[0]
    result = {
        "location": forecast.get("city") or location,
        "weather": f"白天{today.get('dayweather', '')} / 夜间{today.get('nightweather', '')}",
        "temperature": f"{today.get('nighttemp', '')}~{today.get('daytemp', '')}℃",
        "wind": f"{today.get('daywind', '')} {today.get('daypower', '')}级",
        "precipitation": _precipitation_text(casts),
        "forecast": [
            {
                "date": c.get("date", ""),
                "day": c.get("dayweather", ""),
                "temp": f"{c.get('nighttemp', '')}~{c.get('daytemp', '')}℃",
            }
            for c in casts[:3]
        ],
        "source": "实时",
    }
    return json.dumps(result, ensure_ascii=False)


def get_weather(location: str, date: str = "today") -> str:
    """查询某地天气，返回 JSON 字符串。真实源失败时回退到模拟并标注。"""
    location = (location or "").strip()
    adcode = _LOCATION_ADCODE.get(location)
    if adcode and config.WEATHER_API_KEY:
        try:
            return _real_weather(location, adcode)
        except Exception:
            pass  # 任何失败都回退到模拟，绝不让天气接口中断整个诊断
    return _mock_weather(location or "未知地区")


# ---------------------------------------------------------------------------
# 土壤墒情工具（当前仅模拟数据）
# ---------------------------------------------------------------------------
def get_soil(location: str) -> str:
    """查询某地土壤墒情。真实土壤数据源尚未接入，先返回模拟数据并明确标注。"""
    location = (location or "").strip()
    return json.dumps(
        {
            "location": location or "未知地区",
            "soil_moisture": "田间持水量 65%（适宜）",
            "soil_type": "壤土",
            "ph": "6.8（中性，适宜小麦）",
            "suitability": "当前墒情适宜小麦生长，无需立即灌溉",
            "source": "模拟",
            "note": "土壤墒情为内置模拟数据，仅供演示",
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 知识库检索占位（RAG 尚未接入）
# ---------------------------------------------------------------------------
def search_knowledge(query: str) -> str:
    """知识库检索占位：供 P1-2 RAG 落地时替换为真实检索，当前返回明确提示。"""
    return json.dumps(
        {
            "query": query,
            "results": [],
            "source": "模拟",
            "note": "知识库检索（RAG）尚未接入，请基于已有信息回答",
        },
        ensure_ascii=False,
    )


register(Tool(
    name="get_weather",
    description="查询指定地点（中文城市名，如「郑州」）的天气，返回温度、天气现象、降水、风力，用于判断是否适合浇水/施肥/打药。",
    parameters={
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "中文城市名或省名，如 郑州 / 河南"},
            "date": {"type": "string", "description": "可选，默认 today；可为 today/tomorrow"},
        },
        "required": ["location"],
    },
    func=get_weather,
))

register(Tool(
    name="get_soil",
    description="查询指定地点（中文城市名）的土壤墒情（土壤湿度、类型、pH、是否适宜灌溉）。当前返回模拟数据。",
    parameters={
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "中文城市名或省名，如 郑州 / 河南"},
        },
        "required": ["location"],
    },
    func=get_soil,
    simulated=True,
))

register(Tool(
    name="search_knowledge",
    description="检索小麦种植知识库（病害/栽培/施肥等农业知识）。当前为占位，尚未接入真实知识库。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索关键词或问题"},
        },
        "required": ["query"],
    },
    func=search_knowledge,
    simulated=True,
))
