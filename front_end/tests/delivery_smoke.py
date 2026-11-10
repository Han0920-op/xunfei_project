import json, unittest
from unittest.mock import patch
from playwright.sync_api import expect
import casework_smoke as helper
import dialogue, config, web_search, execution_plans


class DeliveryBrowserTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def test_title_and_real_tool_events_render_sources(self):
        call = json.dumps(
            {"action": "tool", "tool": "search_web", "args": {"query": "小麦穗部异常"}}
        )
        answer = json.dumps(
            {
                "action": "answer",
                "title": "小麦穗部异常排查",
                "content": "资料供排查参考。",
            },
            ensure_ascii=False,
        )
        result = {
            "status": "ok",
            "results": [
                {
                    "title": "小麦观察资料",
                    "url": "https://www.moa.gov.cn/example",
                    "summary": "症状描述",
                }
            ],
        }
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=[iter([call]), iter([answer])]
        ), patch.object(web_search, "search_web", return_value=result):
            # tools registry holds the original wrapper; patch its function dependency instead.
            with patch.object(
                dialogue.tools.TOOLS["search_web"],
                "func",
                return_value=json.dumps(result),
            ):
                self.page.goto(self.base + "/index.html")
                self.page.locator("#messageInput").fill("查小麦穗部异常")
                self.page.locator("#sendButton").click()
                expect(
                    self.page.get_by_role(
                        "heading", name="小麦穗部异常排查", exact=True
                    )
                ).to_be_visible()
                expect(
                    self.page.get_by_role("region", name="联网搜索相关网页")
                ).to_be_visible()
                expect(
                    self.page.get_by_role("link", name="小麦观察资料", exact=True)
                ).to_be_visible()
                self.overflow()
                self.page.reload()
                expect(
                    self.page.get_by_role(
                        "heading", name="小麦穗部异常排查", exact=True
                    )
                ).to_be_visible()

    def test_plan_chat_save_list_and_detail(self):
        payload = json.dumps(
            {
                "title": "小麦黄叶变化排查",
                "steps": ["photograph", "observe", "consult"],
            },
            ensure_ascii=False,
        )
        call = json.dumps(
            {
                "action": "tool",
                "tool": "save_execution_plan",
                "args": {"plan_json": payload},
            }
        )
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", return_value=iter([call])
        ):
            self.page.goto(self.base + "/index.html?case=case")
            self.page.locator("#messageInput").fill("为我生成一份执行方案")
            self.page.locator("#sendButton").click()
            self.page.get_by_role(
                "link", name="查看已保存的执行方案", exact=True
            ).click()
            view = self.page.frame_locator("iframe.app-navigation-view:not([hidden])")
            expect(
                view.get_by_role("heading", name="排查方案：小麦黄叶变化排查")
            ).to_be_visible()
            self.overflow()
            view.get_by_role("link", name="执行方案", exact=True).click()
            expect(
                view.get_by_role("link", name="排查方案：小麦黄叶变化排查")
            ).to_be_visible()

    def test_plan_repair_persists_link_after_reload(self):
        def call(payload):
            return json.dumps(
                {
                    "action": "tool",
                    "tool": "save_execution_plan",
                    "args": {"plan_json": payload},
                },
                ensure_ascii=False,
            )

        frames = [
            call({"title": "白穗排查", "steps": [{"description": "补拍照片"}]}),
            call(
                {
                    "title": "白穗排查",
                    "steps": [
                        {"action": "photograph"},
                        "observe",
                        "check_label",
                        "consult",
                    ],
                }
            ),
        ]
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", side_effect=[iter([f]) for f in frames]
        ) as model:
            self.page.goto(self.base + "/index.html?case=case")
            self.page.locator("#messageInput").fill(
                "请为这个案例保存排查执行方案，说明补拍、记录变化、核实标签和联系农技人员的条件"
            )
            self.page.locator("#sendButton").click()
            link = self.page.get_by_role(
                "link", name="查看已保存的执行方案", exact=True
            )
            expect(link).to_be_visible()
            self.assertEqual(model.call_count, 2)
            self.page.reload()
            link.click()
            view = self.page.frame_locator("iframe.app-navigation-view:not([hidden])")
            expect(
                view.get_by_role("heading", name="排查方案：白穗排查", exact=True)
            ).to_be_visible()
            expect(
                view.get_by_role("heading", name="3. 核对药品标签", exact=True)
            ).to_be_visible()
            expect(
                view.get_by_role("heading", name="4. 请农技人员复核", exact=True)
            ).to_be_visible()
            self.overflow()

    def test_plan_storage_error_does_not_render_saved_link(self):
        import sqlite3

        call = json.dumps(
            {
                "action": "tool",
                "tool": "save_execution_plan",
                "args": {"plan_json": {"title": "现场排查", "steps": ["observe"]}},
            }
        )
        with patch.object(config, "SPARK_API_PASSWORD", "test"), patch.object(
            dialogue.llm, "chat_stream", return_value=iter([call])
        ), patch.object(
            execution_plans,
            "save",
            side_effect=sqlite3.OperationalError("private db error"),
        ):
            self.page.goto(self.base + "/index.html?case=case")
            self.page.locator("#messageInput").fill("保存排查方案")
            self.page.locator("#sendButton").click()
            expect(
                self.page.get_by_text("服务端处理或存储异常", exact=False).first
            ).to_be_visible()
            expect(
                self.page.get_by_role("link", name="查看已保存的执行方案", exact=True)
            ).to_have_count(0)
            self.assertEqual(
                self.context.request.get(self.base + "/api/plans").json(), []
            )
