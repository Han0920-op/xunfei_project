import os

from dotenv import load_dotenv

load_dotenv()

SPARK_API_PASSWORD = os.getenv("SPARK_API_PASSWORD", "")
SPARK_BASE_URL = os.getenv("SPARK_BASE_URL", "https://spark-api-open.xf-yun.com/v1")
SPARK_MODEL = os.getenv("SPARK_MODEL", "generalv3.5")
SPARK_TEMPERATURE = float(os.getenv("SPARK_TEMPERATURE", "0.7"))
SPARK_MAX_TOKENS = int(os.getenv("SPARK_MAX_TOKENS", "2048"))
XFYUN_APP_ID = os.getenv("XFYUN_APP_ID", "")
XFYUN_API_KEY = os.getenv("XFYUN_API_KEY", "")
XFYUN_API_SECRET = os.getenv("XFYUN_API_SECRET", "")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "你是「智麦」，一个面向小麦生长管理的农业辅助智能体。请基于用户的问题给出专业、清晰、稳妥的回答；"
    "涉及施肥剂量等不确定信息时，请明确提示需要进一步确认，不要随意编造具体数字。",
)

# ---------- 工具调用相关 ----------
# 天气数据源密钥（高德天气 Web 服务 key）。留空则自动回退到内置「模拟」天气数据。
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
# Agent 编排循环最多调用几轮工具，防止模型反复调用工具导致死循环。
MAX_TOOL_ITERATIONS = int(os.getenv("MAX_TOOL_ITERATIONS", "4"))
# Agent 系统提示词（工具清单与输出格式由 agent.py 在运行时追加）。
AGENT_SYSTEM_PROMPT = os.getenv(
    "AGENT_SYSTEM_PROMPT",
    "你是「智麦」，一个面向小麦生长管理的农业辅助智能体。\n"
    "你的职责：基于用户问题和已掌握的图片识别信息，给出专业、清晰、稳妥的诊断与管理建议。\n"
    "在需要外部数据（如天气、土壤墒情）来支撑判断时，先调用相应工具获取数据，再综合回答。\n"
    "必须遵守：\n"
    "1. 涉及施肥剂量等不确定信息时，明确提示需要进一步确认，不要编造具体数字。\n"
    "2. 工具返回的数据若标注为「模拟」，必须在回答中向用户说明这是模拟数据。\n"
    "3. 只有在确实需要外部数据时才调用工具；能直接回答时不要调用。",
)
