# 案例、复查与官方情报运行说明

## 数据与启动

延续现有启动方法，不覆盖.env。安装 `back_end/requirements.txt` 后重启后端并强制刷新浏览器；发布版本 `2026.11.01.casework`，SSE协议保持兼容。

所有新增个人/案例资料在被Git忽略的 `back_end/data/local/personal.db`。新增表：case_states、case_events、case_photos、case_reports、official_documents、region_subscriptions、risk_deliveries、source_status。`CREATE TABLE IF NOT EXISTS` 迁移幂等，不删除旧记录。备份应包含整个数据库，备份本身也应限制访问。

后端运行时，原提醒调度3秒扫描，官方情报独立线程4小时获取、30秒筛选，不让官网超时阻塞聊天或普通提醒。多进程通过SQLite事务去重通知；当前建议单worker，避免重复抓取。

## 官方来源整理

种子与栏目配置在 `back_end/data/knowledge/official_feeds.json`，当前代码限定农业农村部 `https://www.moa.gov.cn/xw/` 及同站域名。新增其他官方站点需要同时审查代码白名单、页面解析器和部署网络权限，不能只改成任意URL。

单独获取官方原文（默认不参与推荐或预警）：

```sh
cd back_end
python -m agri_sources https://www.moa.gov.cn/xw/zwdt/202604/t20260420_6483403.htm
```

维护人员读完原文后，按**原文明确适用的范围与实际有效期**整理元数据。以下是语法示意，不可原样用于历史文章：

```text
python -m agri_sources <官方文章URL> --kind bulletin --regions 河南 --cities 郑州 --pests 条锈病 --valid-until <原文明示的有效日期> --reviewer <整理人> --note <原文适用条件与有效期依据>
```

- `guideline` 表示技术指导，`bulletin` 表示病虫情报；情报须明确病虫害和省份，不能由天气或普通工作新闻代替。
- regions使用页面下拉中的省级名称，多个值逗号分隔，全国指导用“全国”；cities仅在原文有明确市县限制时填写，用户未选择相同城市不匹配。
- 无法核对时不要填写有效期，不批准进入主动提示。病虫情报有效期最长距发布日期30天，只是额外技术上限，**不能因此默认延长原文有效期**。
- 元数据核对始终不提升 `agronomic_review=pending_review`，本轮没有供随意提升农技可信等级的接口。
- 原文内容哈希变化会自动回到待核对，农技来源矛盾须人工核实；抓取失败不编造文章和风险，超24小时未重新取得的情报不触发通知。

## 关键接口

| 接口 | 用途 |
| --- | --- |
| GET /api/memory/cases/{id} | 原长期记忆案例及新增状态、事件、私有照片元数据 |
| GET /api/casework/cases/{id} | 案例进度与证据时间线 |
| GET /api/casework/cases/{id}/photos/{photo} | 当前所属身份读取压缩照片，no-store |
| POST /api/casework/cases/{id}/photos | 手动补存压缩照片；仅存图，不冒充完成视觉分析 |
| PUT /api/casework/cases/{id}/state | 用户改变状态，关闭停用关联任务 |
| POST /api/casework/cases/{id}/feedback | 用户复查变化及实际措施 |
| GET /api/casework/cases/{id}/comparison | 成功图片观察前后对照及局限 |
| POST /api/casework/cases/{id}/reports | 从已保存案例生成规则核对报告快照 |
| GET /api/casework/cases/{id}/reports/{report} | 读取报告JSON；尾缀/print返回可打印页 |
| GET /api/intelligence/sources | 公开原文元数据及最近获取状态 |
| GET/PUT/DELETE /api/intelligence/subscriptions[/{id}] | 所属身份管理自愿地区订阅 |

所有个人接口遵循原浏览器凭据，写入需要 `X-Zhimai-Personal: 1`。关联case_id由服务端复核，不能用修改请求参数访问别人照片、报告、事实或任务。恢复码找回同一身份；它不替代正式多用户登录。

## 验证命令与范围

项目的 `test_vision.py` 是依赖本地真实照片与付费服务的手动脚本，不能作为无外部依赖的unittest发现模块。自动化运行：

```sh
PYTHONPATH=back_end python - <<'PY'
import pathlib,unittest
names=[p.stem for p in pathlib.Path('back_end').glob('test_*.py') if p.stem!='test_vision']
r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromNames(names))
raise SystemExit(not r.wasSuccessful())
PY
python -m unittest discover -s front_end/tests -p '*smoke.py' -q
```

浏览器用Playwright与Chromium；可按已有测试说明安装依赖。新测试覆盖归属隔离、去EXIF、重复请求、三轮追问停止、失败回滚、复查改期/关闭、报告来源快照、官方源变更撤销核对、过期/未来/错误地区/错误对象过滤、静默、频控、去重、暂停退订与浏览器闭环。模型使用固定替身验证软件行为，不将其作为真实农业诊断准确性证明。另有只含非敏感元数据的真实官方来源获取记录。

## 2026-11-01验证结果

自动化后端测试及37项浏览器测试通过，新增案例浏览器闭环在最终界面调整后再次通过。官方两篇原文已真实获取，元数据与哈希见research目录记录；没有将其审批成当前预警。

本环境真实模型最小问候请求返回HTTP 200、非零业务码11200、无choices；它与新增工具和图片无关。补丁后正确归为model_request_failed并保留安全数字码，不再误报空回答格式错误。这不证明用户电脑也使用相同服务配置；应在用户目前可用的模型端点下验证新工具协议，不能将替身测试当作真实联调通过。未延长超时、未记录上游message、密钥、用户图片或私人会话。
