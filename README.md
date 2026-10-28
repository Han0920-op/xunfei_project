# 智麦

面向农户的冬小麦病虫害辅助诊断、用药核对与持续复查项目。前端仅保留“问智麦／我的记录”，原生 HTML、CSS、JavaScript；后端 FastAPI，保留讯飞模型和工具编排基础。

## 当前进度（2026-10-28）

- 已改为自由智能体对话：上传图片先调用讯飞图片理解，再结合上下文自主选择回答、补问、知识检索、天气或登记工具；不再走固定问卷。
- 天气工具只查询真实高德预报，明确地点、日期和发布时间，失败不回退模拟天气；不凭城市预报给施药许可。
- 用药核对默认20条官方公告记录，只有1条小麦赤霉病用途；当前状态与有效期待核实，不生成具体用量或直接许可。
- 本地50条知识观察特征待农技审校，模型及图片判断不是确诊。照片与记录仍保存在当前浏览器，但点击发送后本轮照片会交给后端及模型处理。
- **真实模型／天气需要有效密钥与网络配置**；本轮环境缺配置，未做真实付费接口验证。没有服务时明确报错，保留输入，不用演示回复替代。

## 本地启动

Python 3.10+，在仓库根目录：

```sh
python -m venv .venv
# Linux / macOS；Windows 使用 .venv\Scripts\activate
source .venv/bin/activate
pip install -r back_end/requirements.txt
cd back_end
uvicorn main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/index.html`。前后端同源。先按 `back_end/.env.example` 配置文字、图片及天气服务（请勿覆盖已有 `.env` 或提交密钥）。直接登记／知识接口不需要模型密钥，自由对话需要讯飞文字服务。若使用仓库根目录 `.venv`，请不要将其提交。

- [自由对话智能体、图片和天气接入](docs/conversational-agent.md)
- [知识库导入、资料审查与检索说明](docs/knowledge-intake.md)
- [登记资料格式、核对逻辑及测试方法](docs/pesticide-data.md)
- [前端说明与本地记录保护](front_end/README.md)
- [简洁版页面设计](docs/frontend-simple.md)
- [三个场景与开发优先级](docs/agent-scenarios.md)
