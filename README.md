# 智麦

面向农户的冬小麦病虫害辅助诊断、用药核对与持续复查项目。前端仅保留“问智麦／我的记录”，原生 HTML、CSS、JavaScript；后端 FastAPI，保留讯飞模型和工具编排基础。

## 当前进度（2026-10-27）

- 用药核对：默认启用20条官方公告登记记录，支持作物／对象核对、原药母药排除、标签限制与来源展示。
- **本批仅1条小麦赤霉病用途，当前状态与到期日全部待核实**。范围相符也不会直接判为可以施药；未知或不匹配分别提示。
- 症状文字已接入上传《小麦知识库最新版》的本地检索与有引用补问，包含 50 条待审校观察特征；不识别照片、不确诊。复查为用户反馈记录，尚无云同步。
- `DEMO-` 编号仅为虚构交互样例，不对应实际产品。当前所有流程均不提供剂量、混配或安全间隔期建议。

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

打开 `http://127.0.0.1:8000/index.html`。前后端同源，无需配置前端地址；核对服务不需要模型密钥。若使用仓库根目录 `.venv`，请不要将其提交。

- [知识库导入、资料审查与检索说明](docs/knowledge-intake.md)
- [登记资料格式、核对逻辑及测试方法](docs/pesticide-data.md)
- [前端说明与本地记录保护](front_end/README.md)
- [简洁版页面设计](docs/frontend-simple.md)
- [三个场景与开发优先级](docs/agent-scenarios.md)
