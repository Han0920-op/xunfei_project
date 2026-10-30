# 启动、回答失败与流式输出排查（2026-10-30）

本次核对的 GitHub 基线为 `27a5706`，修复版本为 `2026.10.30.1`。

## 已发现的问题和证据边界

- 用户提供的启动日志出现 `The system cannot find the path specified`，随后等待30秒超时；浏览器为 `127.0.0.1:8000` 的 `ERR_CONNECTION_REFUSED`。说明启动路径有误且服务未就绪，不能归因于讯飞密钥。旧脚本固定依赖 `back_end\venv\Scripts\activate.bat`，与 README 的根目录 `.venv` 不一致；`cd` 路径未加引号也会影响含空格目录。具体缺失哪条路径仍以本机目录为准。
- 原脚本超时后仍打开浏览器；`curl -s` 只检查连接退出码，404/500也可能被当作就绪，且请求没有显式超时。本次用 Python 轮询实际智麦版本接口，验证版本和协议；失败不打开浏览器，不结束其他占用端口的进程。
- 截图中联想域名的 CORS 错误不是智麦 API 请求。不能通过放开智麦 CORS 解决本机端口拒绝连接。
- 页面“智能体服务暂时无法完成回答”来自 `dialogue.run_turn` 的统一异常处理。鉴权、网络、上游截断、回答 JSON 或证据检查失败以前都显示相同提示，不能凭截图判定是密钥错误。图片及带图片历史的回答要求模型输出证据检查字段；未遵守格式也会被拒绝。本次保留校验，增加分类错误和诊断编号，没有把未校验结果当作成功。
- 用户视频中约19秒前一直等待，随后多段回复一起出现，确实没有可见渐进输出。视频中还缺少新版“停止生成”按钮，是旧前端或缓存的线索；不能仅凭录像判断后端版本或讯飞是否分块返回。

## Windows 更新和启动

在仓库根目录打开 PowerShell，先关闭原来的智麦后端窗口：

```powershell
git pull origin main
```

如果已经有根目录 `.venv`，只更新依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r back_end\requirements.txt
```

如果用的是 `back_end\venv`，则改用：

```powershell
.\back_end\venv\Scripts\python.exe -m pip install -r back_end\requirements.txt
```

如果两者都没有，创建虚拟环境（Python 3.10+）：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r back_end\requirements.txt
```

再次双击 `start.bat`。启动器依次识别根目录 `.venv`、`back_end\venv`、`back_end\.venv`，直接使用对应 Python，支持带空格路径。不会自动安装依赖或覆盖 `.env`。

成功后打开 `http://127.0.0.1:8000/index.html`，按一次 Ctrl+F5 更新旧页面。保留后端窗口；关闭窗口会停止本机服务。不要清理浏览器存储，否则可能丢失本地记录。8000端口已有服务时启动器会提示先关闭旧服务，避免更新后继续使用旧进程。

若窗口提示缺少模块，运行上方对应的依赖安装命令。最新版依赖包含 `tzdata`（Windows 时区支持），只拉取代码不会自动更新虚拟环境。若 `.venv` 随项目移动后 Python 不可运行，需要重新建立虚拟环境，保留业务文件与 `.env`。

## 回答失败怎么看

新版错误会区分鉴权失败、接口路径错误、参数错误、限流或额度限制、超时、连接失败、输出截断、流中断、回答格式/证据检查失败和内部错误。页面和后端日志共享诊断编号。日志仅记录编号和受控错误码，不打印密钥、用户输入、模型原文或签名URL。

维护时先提供错误文字及 `chat_failed request_id=... code=...` 日志，不发送 `.env` 或密钥。旧版本吞掉了异常详情，历史截图无法还原其准确原因。

当前 X2.6 配置应与控制台一致：`SPARK_BASE_URL=https://maas-api.cn-huabei-1.xf-yun.com/v2`；代码自动附加 `/chat/completions`。`SPARK_MODEL` 填所开通的模型 ID，`SPARK_API_PASSWORD` 填 API Key 本体，不加 `Bearer `。图片理解仍使用独立的图片服务凭据。

## 确认流式链路

打开 `http://127.0.0.1:8000/api/agent/capabilities`，应看到：

```json
{"server_version":"2026.10.30.1","stream_protocol":"zhimai-chat-sse-v2"}
```

接口还包含是否配置服务的布尔值，配置存在不代表服务调用已成功。页面脚本带版本号，HTML/JS/CSS要求缓存重新验证。新旧前后端混用会明确提示更新和重启。

Windows 终端运行：

```powershell
curl.exe -N http://127.0.0.1:8000/api/agent/stream-check
```

正常情况下3条 `probe` 约每0.4秒到达，随后 `done`。这只是传输诊断，不调用模型、不计费，不是给回答添加打字动画。Linux/macOS使用 `curl -N`。

页面底部“功能范围与数据说明”中的“连接诊断”可查看最近一次请求的版本、编号、分块数量、首段/末段时间；成功记录的文字摘要也包含该诊断。计数中不包含密钥、问题、图片或模型原文。

- 上游内容块数和回答增量数都很少：可能是服务本身一次返回大块内容。仍需结合计时和该请求类型确认；工具控制JSON不直接显示，登记核对的确定性结果可能整段返回。
- 服务端持续产生回答增量，但浏览器集中接收：检查代理缓冲及网络。网络读取次数不等于模型token数，不单凭一个计数定位原因。
- 如使用 Nginx，可检查该 SSE 路径是否设置 `proxy_buffering off`、`proxy_cache off`、`gzip off` 和足够的读超时。直接通过本机8000访问时，先排查本机进程和版本。
- 图片理解和工具查询完成前可能还没有回答正文；会显示真实状态。此时等待不等于流式功能失效。

直接调用 `POST /api/agent/chat` 的集成客户端需增加请求头 `X-Zhimai-Stream-Protocol: zhimai-chat-sse-v2`。服务先返回 `start`，逐步返回 `answer_delta`，结束前返回 `stream_stats`；只有 `answer` 与 `done` 均收到才保存成功记录。旧的其他 API 不受此协议变更影响。

## 验证范围

使用模拟模型和真实本机 HTTP/浏览器验证首段在模型完成前显示、SSE探针逐段到达、失败不保存、照片与输入保留，以及启动失败/端口占用不会打开浏览器。当前执行环境为 Linux，未实机双击 Windows 批处理；没有用户本机密钥，未验证其真实讯飞请求时延。需要在用户更新并启动后，根据新的错误码继续定位实际调用失败。
