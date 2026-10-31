# SSE HTTP 200 后返回 error：排查记录与最小修复建议

## 结论及证据范围

1. 用户的 `/api/agent/capabilities` 截图只有 `chat_configured`、`vision_configured`、`weather_configured` 与 note，没有 `server_version` / `stream_protocol`。配合旧版统一错误文案及 `Cache-Control: no-cache`，可以确认浏览器访问的响应来自旧版后端实现，而非 GitHub `31b2226` 的接口。可能仍运行旧进程，或启动了另一份代码目录。刷新前端不能替换后端进程。三个 configured=true 只表示变量非空。
2. 在当前云环境使用已有配置、仅发送固定测试文字（无照片、无私人会话），实际重现了业务错误被误判为空回答的链路：上游 HTTP 200 + SSE `{code:11200,message:...}` + `[DONE]`，未返回 choices；解析器忽略该帧，回答校验抛出 `ValueError("empty model response")`，再包装为 `ResponseFormatError` 并被 Agent 转为 error 事件。本次没有记录 message 原文。
3. 云环境有效配置是旧接口 `spark-api-open.xf-yun.com/v1` + `generalv3.5`，并未指定此前用户所用的 X2.6 URL/model。不能据此断言用户电脑配置相同，也不将11200擅自解释为某一种密钥错误。服务端业务拒绝的具体原因须结合对应服务控制台核验。当前云环境网络白名单不包含 MaaS 域名，因此未做 X2.6 成功调用验证。
4. 另有可复现的多轮格式失败：历史中含此前图片观察时，即使本轮不发图片，`require_checks` 仍为 true；模型若返回普通文本而不是含检查字段的回答，会抛 `ValueError("missing evidence header")`。这是既有校验规则的结果，不是 PNG 格式错误。本次没有放宽规则。

## 实测异常链（不含原始响应文本）

本次云端固定测试请求的关联编号为 `e38608ef8fca`：

```text
sse.start
agent.context_ready: has_image=false, requires_checks=false
model.start: tool_round=0
model.http_response: status_code=200
model.provider_business_error: provider_code=11200
agent.answer_validation_failed:
  ResponseFormatError (response_stream.py)
  caused by ValueError (response_stream.py): reason=empty_model_response
sse.error: model_calls=1, upstream_content_chunks=0
```

这次约1.6秒失败，没有执行工具，没有进入多轮工具调用，足以排除“工具太慢或图片过大”是此固定文字复现的原因。这个编号属于云环境测试，不是用户截图中的请求。

## HTTP 200 为什么不是成功

请求路径是 `POST /api/agent/chat`（不是旧版其他聊天接口）：

```text
FastAPI 参数及图片校验
  → StreamingResponse 建立 HTTP 200 / text/event-stream
  → SSE 生成器
  → dialogue.run_turn 构建图片和历史上下文
  → llm.chat_stream 请求模型
  → response_stream 解析工具 JSON 或校验回答
  → 必要时执行工具并进入下一轮模型调用
  → answer + done（成功）或 error（失败）
```

HTTP 响应头已经发出后，模型失败只能由 SSE error 事件报告，不能再把已发送的200改成500。客户端必须判断最终事件，不能只判断 HTTP 状态。浏览器 Response 标签的“没有可预览内容”也不能替代 EventStream 内容作为结论。

解析器目前只处理 `event.error`，而将缺少 choices 的帧视为可跳过的 usage 帧。`code != 0` 的业务错误也被跳过，是本次已确认的协议错误处理缺口。最末端的“回答格式错误”掩盖了最初的业务拒绝。

## 本次改动：仅可观测性

- SSE 响应头 `X-Request-ID`、start/error 事件与服务端日志使用同一服务端生成编号。
- capability 增加 `diagnostics_version: safe-trace-v1`，用于确认补丁确实加载。
- 显式传递 Trace 对象，避免同步生成器跨线程恢复时丢失或串用请求上下文。
- 记录 SSE、上下文准备、模型各轮、工具执行、图片失败和回答校验边界。
- 记录异常类型及原因链、仓库内文件名/行号、受控原因码、HTTP状态、数字业务错误码、计数和耗时。
- 不使用普通 `logger.exception` / `exc_info=True`，不格式化异常全文、不输出源码行或栈局部变量；Pydantic输入值、未知字段名、URL、响应body、API Key、图片、用户问题、工具参数和模型原文均不记录。
- 模型参数、超时、工具选择、证据门槛、重试策略、回答接受规则均保持不变。业务错误帧现在会被记录，但仍按原流程失败，以便先确定原因再单独修复。

## 用户电脑上的复现步骤

### 1. 先确认运行的是这份代码

关闭原智麦后端窗口。在实际项目根目录的 PowerShell 执行：

```powershell
git pull origin main
git log -1 --oneline
.\start.bat
```

如果提示8000端口被占用，不要反复启动。可先查监听PID：

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
```

识别并正常关闭自己启动的旧智麦终端后重试，不盲目结束未知进程。

重新打开 `http://127.0.0.1:8000/api/agent/capabilities?diagnostic=1`，应包含：

```json
{"server_version":"2026.10.30.1","stream_protocol":"zhimai-chat-sse-v2","diagnostics_version":"safe-trace-v1"}
```

本补丁仅增加后端日志，未更换前端资源版本。若依然没有这些字段，检查是否更新了另一份项目目录。不要清理浏览器本地记录。

### 2. 先测固定文字，不发送照片和私人历史

```powershell
curl.exe -N -i -H "X-Zhimai-Stream-Protocol: zhimai-chat-sse-v2" --form-string "message=hello" --form-string "history=[]" http://127.0.0.1:8000/api/agent/chat
```

这会真实调用已配置文字模型；可使用命令行看到的 `X-Request-ID` 在后端窗口查找同号 `chat_diagnostic` 日志。若固定文字成功，再在网页里分别测试新会话图片和含图片历史的后续提问，比较 `requires_checks`、失败阶段和业务码。无需向维护人员提供照片、密钥或 `.env`。

### 3. 不依赖接口额度的代码级复现

安装项目依赖与 httpx 后，从 back_end 目录运行：

```powershell
python -m unittest test_diagnostics -v
```

测试覆盖11200错误帧→空回答异常、外层200/上游401、图片历史触发格式校验、工具异常后的正常收尾、生成器准备失败、并发请求编号隔离和日志隐私。上游替身数据只用于测试，不作为生产回复。

## 最小修复建议（与本次诊断补丁分开）

1. **配置修正优先**：如果使用 X2.6，核对同一服务下的 API Key、开通模型与地址；不能只替换 Key 而沿用默认 generalv3.5。控制台示例对应：

   ```dotenv
   SPARK_BASE_URL=https://maas-api.cn-huabei-1.xf-yun.com/v2
   SPARK_MODEL=spark-x2.6-4b
   ```

   `SPARK_API_PASSWORD` 填对应服务的 Key 本体，不加 Bearer。不修改或提交现有密钥。修改配置后重启后端；仅在云环境运行时还需通过正常网络配置流程允许该 MaaS 域名。

2. **最小协议补丁**：在 llm.py 的 choices 判断之前识别服务已定义的非零业务 code，立即抛带数字业务码的受控 LLMError。保留正常 usage 帧跳过逻辑和 `[DONE]` 校验，使失败显示“模型服务拒绝请求”，而不再误判为回答格式问题。这只能修正错误归类，不能消除上游业务拒绝；新增非零code、零code、usage、正常分块的回归用例后再实施。
3. **多轮校验另行处理**：仅在用户日志明确出现 missing_evidence_header / ValidationError 时处理模型输出契约问题。不要为解决11200删除证据检查，也不要通过延长超时或把未校验文本作为成功回答来掩盖问题。

当前尚缺用户电脑更新后的同编号日志，不能宣称已修复其真实接口调用。本次已经拿到云环境原始异常类型/位置及业务错误码，并提供了独立可复现测试。
