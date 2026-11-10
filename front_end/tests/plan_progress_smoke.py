"""Real plan progress and linked follow-up, with isolated owned case data."""

import json
import unittest
from pathlib import Path
from playwright.sync_api import expect
import casework_smoke as helper
import execution_plans


class PlanProgressBrowserTests(unittest.TestCase):
    def setUp(self):
        helper.CaseworkBrowserTests.setUp(self)
        result = execution_plans.save(
            self.who,
            "case",
            "plan",
            json.dumps(
                {
                    "title": "小麦现场排查",
                    "steps": ["photograph", "observe", "followup"],
                }
            ),
        )
        self.plan_id = result["plan_id"]
        self.url = self.base + "/api/plans/" + self.plan_id
        self.page.goto(self.base + "/" + result["url"])
        expect(self.page.get_by_role("heading", name="接下来这样排查")).to_be_visible()

    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def test_progress_survives_reload_and_followup_is_confirmed_in_original_case(self):
        check = self.page.get_by_role(
            "checkbox", name="标记完成：补拍关键部位", exact=True
        )
        check.check()
        expect(self.page.locator("#planSaveStatus")).to_have_text("执行进度已保存。")
        self.page.reload()
        expect(check).to_be_checked()
        expect(
            self.page.get_by_role("progressbar", name="方案执行进度")
        ).to_have_attribute("value", "1")
        self.overflow()
        self.page.get_by_role("link", name="安排案例复查", exact=True).click()
        expect(self.page.get_by_role("dialog")).to_be_visible()
        expect(self.page.locator("[name=case_id]")).to_have_value("case")
        expect(self.page.locator("[name=task_type]")).to_have_value("followup")
        self.assertEqual(
            self.context.request.get(self.base + "/api/personal/tasks").json(), []
        )
        self.page.get_by_role("button", name="确认设置提醒", exact=True).click()
        expect(self.page.get_by_role("dialog")).not_to_be_visible()
        tasks = self.context.request.get(self.base + "/api/personal/tasks").json()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["case_id"], "case")
        self.page.goto(self.base + "/plans.html")
        expect(self.page.locator(".plan-progress")).to_contain_text("已完成 1 / 3 项")
        expect(self.page.locator(".plan-list-card")).to_contain_text("进行中")

    def test_failed_write_rolls_back_display_and_can_retry(self):
        self.page.route(
            "**/api/plans/*/steps/*",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"detail": "暂时无法保存，请重试"}),
            ),
        )
        check = self.page.get_by_role(
            "checkbox", name="标记完成：补拍关键部位", exact=True
        )
        check.check()
        expect(self.page.locator("#planSaveError")).to_contain_text("暂时无法保存")
        expect(check).not_to_be_checked()
        self.assertEqual(
            self.context.request.get(self.url).json()["progress"]["completed"], 0
        )
        self.page.unroute("**/api/plans/*/steps/*")
        self.page.get_by_role("button", name="重试保存进度", exact=True).click()
        expect(self.page.locator("#planSaveStatus")).to_have_text("执行进度已保存。")
        expect(check).to_be_checked()

    def test_other_page_changes_are_refreshed_without_overwrite(self):
        r = self.context.request.patch(
            self.url + "/steps/2",
            headers={"X-Zhimai-Personal": "1"},
            data={"completed": True, "revision": 0},
        )
        self.assertEqual(r.status, 200)
        first = self.page.get_by_role(
            "checkbox", name="标记完成：补拍关键部位", exact=True
        )
        first.check()
        expect(self.page.locator("#planSaveError")).to_contain_text("已读取最新状态")
        expect(first).not_to_be_checked()
        expect(
            self.page.get_by_role("checkbox", name="标记完成：记录异常变化", exact=True)
        ).to_be_checked()
        first.check()
        expect(self.page.locator("#planSaveStatus")).to_have_text("执行进度已保存。")
        expect(
            self.page.get_by_role("progressbar", name="方案执行进度")
        ).to_have_attribute("value", "2")

    def test_disconnected_write_keeps_checkbox_and_reports_unconfirmed_save(self):
        self.page.route("**/api/plans/*/steps/*", lambda route: route.abort("failed"))
        check = self.page.get_by_role(
            "checkbox", name="标记完成：补拍关键部位", exact=True
        )
        check.check()
        expect(self.page.locator("#planSaveError")).to_contain_text(
            "连接中断，进度尚未确认保存"
        )
        expect(check).not_to_be_checked()
        expect(
            self.page.get_by_role("button", name="重试保存进度", exact=True)
        ).to_be_visible()
        self.assertEqual(
            self.context.request.get(self.url).json()["progress"]["completed"], 0
        )

    def test_completed_and_archived_states_on_mobile(self):
        for n in range(1, 4):
            self.context.request.patch(
                self.url + f"/steps/{n}",
                headers={"X-Zhimai-Personal": "1"},
                data={"completed": True, "revision": n - 1},
            )
        self.page.reload()
        expect(self.page.locator(".receipt-state")).to_contain_text("步骤已完成")
        self.page.get_by_role(
            "checkbox", name="标记完成：记录异常变化", exact=True
        ).uncheck()
        expect(self.page.locator("#planSaveStatus")).to_have_text("执行进度已保存。")
        expect(self.page.locator(".receipt-state")).to_contain_text("进行中")
        self.overflow()
        directory = Path("/workspace/artifacts/zhimai-experience")
        directory.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(
            path=str(directory / "plan-progress-mobile.png"),
            full_page=True,
            animations="disabled",
        )
        self.context.request.patch(
            self.base + "/api/memory/cases/case",
            headers={"X-Zhimai-Personal": "1"},
            data={"title": "小麦现场排查", "archived": True},
        )
        self.page.reload()
        expect(
            self.page.get_by_role("checkbox", name="标记完成：记录异常变化", exact=True)
        ).to_be_disabled()
        expect(
            self.page.get_by_role("link", name="安排案例复查", exact=True)
        ).to_have_count(0)
        expect(self.page.locator(".plan-archived")).to_contain_text("案例已结束")
