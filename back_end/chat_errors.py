"""Allowlisted public errors; never include provider bodies or signed URLs."""
MESSAGES = {
    "model_auth_failed": "讯飞文字服务鉴权失败，请检查 API Key 是否有效、是否开通所选模型。",
    "model_endpoint_invalid": "讯飞接口地址未找到，请检查 SPARK_BASE_URL；填写到 /v2，不要重复填写 /chat/completions。",
    "model_request_invalid": "讯飞未接受请求参数，请检查模型名称及接口配置。",
    "model_rate_limited": "讯飞当前限制请求频率或额度，请检查控制台额度，稍后重试。",
    "model_unavailable": "讯飞服务暂时不可用，请稍后重试。",
    "model_timeout": "等待讯飞响应超时，请稍后重试。",
    "model_connection_failed": "后端无法连接讯飞，请检查运行后端的电脑网络及代理设置。",
    "model_truncated": "模型输出达到长度限制，回答未完成，请缩短问题；维护人员可检查输出长度配置。",
    "model_filtered": "模型未正常完成这次回答，请调整描述后重试。",
    "model_stream_invalid": "讯飞返回的流式数据格式不符合预期，请检查接口兼容性。",
    "model_stream_interrupted": "讯飞连接在回答完成前中断，请重试。",
    "answer_format_invalid": "模型返回的回答未通过格式或证据自检，本次没有保存。请重新发送。",
    "model_request_failed": "讯飞未能完成这次请求，请稍后重试。",
    "internal_error": "智麦处理本次请求时发生内部错误，请联系维护人员查看诊断编号。",
}


def error_event(code):
    code = code if code in MESSAGES else "internal_error"
    return {"type": "error", "code": code,
            "message": MESSAGES[code] + " 输入和照片已保留。"}
