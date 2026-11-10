"""Inventory filters and task/message state views against the real owned API."""

import unittest
from datetime import timedelta
from unittest.mock import patch
from playwright.sync_api import expect
import casework_smoke as helper
import personal


class PersonalWorkspaceTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def save(self, kind, key, body):
        r = self.context.request.put(
            self.base + "/api/personal/" + kind + "/" + key,
            headers={"X-Zhimai-Personal": "1"},
            data=body,
        )
        self.assertEqual(r.status, 200)

    def test_inventory_filters_search_refresh_and_narrow_layout(self):
        self.save(
            "medicines",
            "one",
            {"name": "已登记号资料", "number": "PD20250010", "notes": "请核对包装"},
        )
        self.save("medicines", "two", {"name": "待补资料"})
        self.page.goto(self.base + "/personal.html")
        expect(self.page.locator(".workspace-metric strong")).to_have_text(
            ["2", "1", "1"]
        )
        self.page.locator("[data-filter=missing]").click()
        expect(self.page.locator("article")).to_have_count(1)
        expect(self.page.locator("article")).to_contain_text("待补资料")
        self.page.get_by_role("button", name="编辑", exact=True).click()
        self.page.locator("[name=number]").fill("WP20120033")
        self.page.get_by_role("button", name="确认保存", exact=True).click()
        expect(self.page.locator("article")).to_have_count(0)
        expect(self.page.locator(".workspace-metric strong")).to_have_text(
            ["2", "2", "0"]
        )
        self.page.get_by_role("button", name="查看全部", exact=True).click()
        self.page.locator("[data-filter=noted]").click()
        self.page.get_by_role("searchbox", name="搜索农药").fill("不存在")
        expect(self.page.locator("article")).to_have_count(0)
        self.page.get_by_role("searchbox", name="搜索农药").fill("")
        expect(self.page.locator("article")).to_have_count(1)
        self.page.emulate_media(reduced_motion="reduce")
        self.assertEqual(
            self.page.locator(".art-float").evaluate(
                "(el) => getComputedStyle(el).animationName"
            ),
            "none",
        )
        for width in (320, 390, 1440):
            self.page.set_viewport_size({"width": width, "height": 1000})
            self.overflow()

    def test_completed_paused_and_unread_are_distinct(self):
        target = personal.now() + timedelta(minutes=10)
        for key, enabled in [("active", True), ("paused", False)]:
            self.save(
                "tasks",
                key,
                {
                    "name": key,
                    "task_type": "reminder",
                    "recurrence": "once",
                    "run_at": target.isoformat(),
                    "enabled": enabled,
                },
            )
        self.page.goto(self.base + "/personal.html?tab=tasks")
        expect(self.page.locator(".workspace-metric strong")).to_have_text(
            ["1", "0", "1"]
        )
        self.page.locator("[data-filter=paused]").click()
        expect(self.page.locator("article")).to_have_count(1)
        expect(self.page.locator("article")).to_contain_text("paused")
        with patch.object(personal, "now", return_value=target + timedelta(seconds=1)):
            personal.tick()
        self.page.reload()
        expect(self.page.locator(".workspace-metric strong")).to_have_text(
            ["0", "1", "1"]
        )
        self.page.locator("[data-filter=completed]").click()
        expect(self.page.locator("article")).to_contain_text("active")
        self.page.locator("[data-tab=notifications]").click()
        expect(self.page.locator(".workspace-metric strong")).to_have_text(
            ["1", "1", "0"]
        )
        self.page.locator("[data-filter=unread]").click()
        self.page.locator("[data-read]").click()
        expect(self.page.locator(".workspace-metric strong")).to_have_text(
            ["1", "0", "1"]
        )
        expect(self.page.locator("article")).to_have_count(0)
        self.page.locator("[data-filter=read]").click()
        expect(self.page.locator("article")).to_have_count(1)
        self.overflow()


if __name__ == "__main__":
    unittest.main()
