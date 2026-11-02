# 智麦

面向冬小麦种植户的辅助诊断、用药核对与持续复查工具。原生HTML/CSS/JavaScript前端，FastAPI后端，提示词驱动ReAct工具循环；左侧四个入口为“问智麦 / 我的记录 / 我的农药库 / 提醒”。不建设地块档案。

## 当前进度（2026-11-02）

本轮按五大能力文档完成案例、复查和地区订阅的软件链路，详见[交付与验收](docs/development-roadmap.md)、[运行维护说明](docs/casework-and-intelligence.md)。

- 案例保存症状、去除定位信息的压缩照片、模型候选原因、缺失证据、查询引用与用户确认措施，并有明确状态。三轮结构化追问仍不足转农技复核，不把模型猜测写成事实。
- 用户及案例长期记忆按浏览器身份隔离，支持恢复码、旧文字手动同步、资料更正和删除；旧本机照片不自动上传。
- 案例页支持反馈变化、前后观察、生成带引用和规则核对的JSON/可打印报告。案例复查任务可手动设置或通过智麦确认卡创建，通知回到同一案例补图，结束案例停用任务。
- 个人农药库支持增删改和对话读取；天气查询只使用真实高德预报。普通提醒、天气检查及地区订阅共用站内提示，桌面通知需授权并保持网页打开，尚无关闭网页后的Web Push/微信/短信。
- 天气预警页支持暴雨、大风、寒潮、霜冻的明确标注演示，网页内弹出提醒并展示防护、观察和复查建议。演示不写入真实预警或案例。公开官方源有独立的时间/地区校验与去重链路，当前云环境访问受限、来源格式尚未真实联调，不能宣称已获得实时官方预警。详见[天气演示与来源边界](docs/weather-warnings.md)。
- 聊天可选择订阅地区作为参考，单个启用订阅默认参考，多个订阅分别选择；当前文字明确的其他地点优先，不把订阅当作照片所在地。
- 已接入农业农村部栏目获取、来源变更复核与自愿地区订阅，支持有效期、地区/病虫害筛选、静默、频控和去重。新增原文先待核对，没有有效情报就不生成风险通知。真实可访问的春季资料不能充作当前秋季预警。
- 原有50条观察片段待农技审校，20条登记公告仅1条涉及小麦用途，当前有效性和完整标签尚不足以提供施药许可。报告与工具保留这些局限，不提供未经核验的用量、混配或间隔。

软件测试不替代农技审校、真实模型联调和农户实机试用。官方源连接验证见[获取记录](docs/research/official-source-connectivity.json)。

## 本地启动

HTTP 200 后出现 SSE error 的排查、日志隐私和最小修复建议见[异常链排查记录](docs/sse-error-investigation.md)。

Windows 可双击 `start.bat`；启动器识别根目录 `.venv` 或 `back_end\venv`，确认后端就绪后才打开页面。首次安装及报错处理见[启动、回答失败与流式输出排查](docs/startup-and-streaming-troubleshooting.md)。更新代码后也请更新对应虚拟环境的依赖。

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

- [最新开发计划：我的农药库、定时任务与持续复查](docs/development-roadmap.md)（本轮交付与验收状态）
- [自由对话智能体、图片和天气接入](docs/conversational-agent.md)
- [知识库导入、资料审查与检索说明](docs/knowledge-intake.md)
- [登记资料格式、核对逻辑及测试方法](docs/pesticide-data.md)
- [前端说明与本地记录保护](front_end/README.md)
- [简洁版页面设计](docs/frontend-simple.md)
- [三个场景与开发优先级](docs/agent-scenarios.md)
