import os

from dotenv import load_dotenv

load_dotenv()

SPARK_API_PASSWORD = os.getenv("SPARK_API_PASSWORD", "")
SPARK_BASE_URL = os.getenv("SPARK_BASE_URL", "https://spark-api-open.xf-yun.com/v1")
SPARK_MODEL = os.getenv("SPARK_MODEL", "generalv3.5")
SPARK_TEMPERATURE = float(os.getenv("SPARK_TEMPERATURE", "0.7"))
SPARK_MAX_TOKENS = int(os.getenv("SPARK_MAX_TOKENS", "2048"))

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "你是「智麦」，一个面向小麦生长管理的农业辅助智能体。请基于用户的问题给出专业、清晰、稳妥的回答；"
    "涉及施肥剂量等不确定信息时，请明确提示需要进一步确认，不要随意编造具体数字。",
)
