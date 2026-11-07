# DeepSeek 接入与网页来源卡片（2026-11-07）

## 交付状态

- 文字决策、工具选择和最终回答已接入 DeepSeek 的 OpenAI 兼容接口，推荐 `deepseek-chat` 非推理聊天配置。保留流式输出、一次格式纠正、工具结果校验、重试恢复和站内切换。
- 图片已适配单独部署的 DeepSeek-VL2 视觉推理接口，推荐先验证 `deepseek-ai/deepseek-vl2-small`。它支持视觉问答，选择 Small 是为了兼顾部署成本与观察能力，并非已经证明其农业识别效果或速度最优。
- **用户目前只有 DeepSeek 官方文字 API Key，没有提供可用的 VL2 推理服务。图片实际切换尚未完成，不能宣称真实识别已跑通。** 本补丁不会把文字 API Key 自动发给视觉服务，不把 `deepseek-chat` 当作视觉模型，也不在 DeepSeek 失败时偷偷调用讯飞。
- 联网搜索结果直接显示在回答下方：网页标题、站点、可用的发布日期、摘要及原文入口。点击原文打开新标签页；重载案例后卡片仍保留。搜索失败时显示明确失败状态和手动搜索入口；入口不是已检索到的证据。

## 文字配置

在现有 `back_end/.env` 中新增或修改以下项，不要覆盖其他配置、提交密钥或把密钥发送到聊天：

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=在本机填写你的官方APIKey
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TEMPERATURE=0.3
DEEPSEEK_MAX_TOKENS=2048
```

`BASE_URL` 不包含 `/chat/completions`。已有仅配置星火的部署，在未设置 `LLM_PROVIDER` 时保持兼容；添加 DeepSeek Key 后自动优先选择 DeepSeek。明确设置 `LLM_PROVIDER=deepseek` 后缺少 Key 会报未配置，不回退旧 Key。

## 图片配置及缺失条件

已核对的官方模型说明：<https://github.com/deepseek-ai/DeepSeek-VL2>。VL2 是视觉语言模型家族，不是官方文字接口的另一个随意可填的 model 名称；OCR 模型面向文字提取，不能替代麦穗、叶片视觉观察。

需要用户另行取得/部署一个实际支持 DeepSeek-VL2、OpenAI 兼容 `image_url` 输入的视觉推理服务，然后配置：

```dotenv
VISION_PROVIDER=deepseek
DEEPSEEK_VISION_BASE_URL=https://你的视觉服务地址/v1
DEEPSEEK_VISION_API_KEY=该视觉服务自己的密钥
DEEPSEEK_VISION_MODEL=deepseek-ai/deepseek-vl2-small
VISION_MAX_TOKENS=800
```

模型标识以实际服务部署的名称为准。私有自托管服务不要求鉴权时可留空视觉 Key；公网服务应使用 HTTPS 和鉴权。不能将普通 `https://api.deepseek.com` 或文字模型 `deepseek-chat`、`deepseek-reasoner` 填入该视觉方案。

没有视觉端点时明确提示图片未识别，仍可依据文字交流。现有讯飞图片实现保留为**显式** `VISION_PROVIDER=xfyun` 的兼容选项，是否继续使用由部署者决定；它不是 DeepSeek 失败后的自动回退。

文字接口和视觉接口都有独立超时与错误处理；截断、空回复和格式异常不会当成成功图片观察。上传主链路继续压缩图片并去除定位信息。

## 搜索展示

网页来源展示由真实工具结果生成，模型正文里的网址不被当作已检索来源。网页标题、摘要转义，拒绝脚本协议和本地网络地址。来源属于农业农村部域名时才标注相应网站，其余显示实际站点。

“麦穗、麦苗、麦叶”等明确小麦关键词在搜索时补充“小麦”语境，不自动补成某一种病名。Bing 无可用结果时沿用有限官方文章的实时补充读取，并明确标注历史文章，不能作为当前地区预警。

本次用公开问题“小麦 麦穗发白”真实检索，通用搜索未取得结果，官方页面补充读取取得两篇农业农村部文章，发布日期分别为 2026-04-20、2026-02-28。这验证了当前环境的官方补充路径，不代表通用搜索或所有网络环境均稳定。

## 验证边界

后端全量 246 项通过；浏览器验证覆盖 65 项场景。新用例的原文测试页面补齐 UTF-8 声明后，新增 3 项浏览器用例复测通过，其余 62 项在全量回归中通过。

新增测试覆盖 DeepSeek 请求地址、模型与鉴权、推理正文隔离、缺少密钥不回退、独立视觉凭证、真实图片字节编码、错误/截断图片回复拒绝、公开配置不泄密，以及照片→观察→决策→搜索→回答→网页卡片→打开原文的浏览器链路。

模型测试使用替身接口，没有用户的官方 Key 或可用视觉端点，未进行付费模型调用、真实延迟对比或农业图片准确率评测。接口适配通过不等于模型服务已经开通。

拉取代码后重启 `start.bat`，浏览器 Ctrl+F5。`/api/agent/capabilities` 会显示文字/视觉各自的 provider、model 和 configured；configured 仅表示必要配置存在，不保证授权或连通成功。版本为 `2026.11.07.deepseek`。
