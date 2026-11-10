"""Real page/in-page weather demos without real warnings or external notifications."""

import json, unittest
from datetime import timedelta
from unittest.mock import patch
from playwright.sync_api import expect
import casework_smoke as helper
import personal, weather_alerts as w


class WeatherAlertBrowserTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def sub(self, weather=False):
        r = self.context.request.put(
            self.base + "/api/intelligence/subscriptions/zz",
            headers={"X-Zhimai-Personal": "1"},
            data={
                "province": "河南",
                "city": "郑州",
                "pests": [] if weather else ["条锈病"],
                "weather_enabled": weather,
                # This flow checks delivery, independent of the wall-clock quiet window.
                "quiet_start": "00:00",
                "quiet_end": "00:00",
            },
        )
        self.assertEqual(r.status, 200)

    def test_four_scenarios_popup_guidance_and_no_real_data_pollution(self):
        self.sub()
        self.page.add_init_script(
            "window.notificationCalls=0;window.Notification=class{static permission='granted';constructor(){window.notificationCalls++}}"
        )
        self.page.goto(self.base + "/weather-alerts.html")
        expect(
            self.page.get_by_role("heading", name="天气预警", exact=True)
        ).to_be_visible()
        self.overflow()
        self.page.get_by_label("演示地区", exact=True).select_option("zz")
        before = self.context.request.get(self.base + "/api/memory/cases").json()
        for label in ("暴雨橙色", "大风黄色", "寒潮蓝色", "霜冻橙色"):
            self.page.get_by_role(
                "button", name="演示" + label + "提醒", exact=True
            ).click()
            box = self.page.locator("#reminderAlert")
            expect(box).to_be_visible()
            expect(box).to_contain_text("非真实预警")
            expect(box).to_contain_text("河南 郑州")
            expect(box.locator("ol li")).to_have_count(3)
            self.page.evaluate("ZhimaiReminders.refresh()")
            expect(box).to_be_visible()
            expect(self.page.locator("#demoResult")).to_contain_text(
                "不代表当地正在发生"
            )
            self.overflow()
            box.get_by_role("button", name="知道了", exact=True).click()
            expect(box).to_have_count(0)
        self.assertEqual(self.page.evaluate("notificationCalls"), 0)
        self.assertEqual(
            self.context.request.get(self.base + "/api/personal/notifications").json(),
            [],
        )
        self.assertEqual(
            self.context.request.get(self.base + "/api/memory/cases").json(), before
        )
        self.page.reload()
        expect(self.page.locator("#demoResult")).to_be_empty()

    def test_demo_upgrade_cancel_and_weather_only_subscription_form(self):
        self.page.goto(self.base + "/intelligence.html")
        self.page.get_by_role("button", name="新增地区订阅", exact=True).click()
        self.page.locator("[name=province]").select_option(label="河南")
        self.page.locator("[name=city]").fill("郑州")
        self.page.get_by_label("接收匹配地区的真实气象预警", exact=True).check()
        self.page.get_by_role("button", name="确认订阅", exact=True).click()
        expect(
            self.page.get_by_role("heading", name="河南 郑州", exact=True)
        ).to_be_visible()
        self.assertTrue(
            self.context.request.get(
                self.base + "/api/intelligence/subscriptions"
            ).json()["subscriptions"][0]["weather_enabled"]
        )
        self.page.get_by_role("button", name="打开导航", exact=True).click()
        self.page.get_by_role("link", name="天气预警", exact=True).click()
        for action in ("升级", "解除"):
            self.page.get_by_label("演示阶段", exact=True).select_option(label=action)
            self.page.get_by_role("button", name="演示暴雨橙色提醒", exact=True).click()
            expect(self.page.locator("#reminderAlert")).to_contain_text("预警" + action)
            self.page.locator("#reminderAlert").get_by_role(
                "button", name="知道了", exact=True
            ).click()
        expect(self.page.locator("#demoResult")).to_contain_text("演示情景")
        self.overflow()

    def test_expired_warning_remains_history_without_interrupting_chat(self):
        now = personal.now()
        old = {
            "name": "过期合成预警",
            "message": "仅用于测试历史记录",
            "task_type": "weather_alert",
            "created_at": (now - timedelta(hours=2)).isoformat(),
            "read": False,
            "warning": {
                "status": "active",
                "publisher": "测试替身",
                "issued_at": (now - timedelta(hours=2)).isoformat(),
                "expires_at": (now - timedelta(hours=1)).isoformat(),
            },
            "advice": ["历史观察建议"],
        }
        with personal.db() as c:
            c.execute(
                "INSERT INTO entries VALUES(?,?,?,?,?)",
                (self.who, "expired-warning", "notifications", json.dumps(old), ""),
            )
        self.page.goto(self.base + "/index.html")
        self.page.evaluate("ZhimaiReminders.refresh()")
        expect(self.page.locator("#reminderAlert")).to_have_count(0)
        self.page.goto(self.base + "/personal.html?tab=notifications")
        expect(self.page.locator(".personal-badge")).to_contain_text(
            "历史预警 · 已过期"
        )
        expect(self.page.locator("#reminderAlert")).to_have_count(0)

    def test_real_notification_arrives_in_chat_and_expired_records_do_not_popup(self):
        self.sub(weather=True)
        now = personal.now()
        record = {
            "id": "fixture-real-flow",
            "headline": "测试替身：郑州暴雨橙色预警",
            "senderName": "测试替身气象台",
            "pubTime": now.isoformat(),
            "startTime": now.isoformat(),
            "endTime": (now + timedelta(hours=2)).isoformat(),
            "typeName": "暴雨",
            "level": "橙色",
            "areaCodes": ["410100"],
            "status": "active",
        }
        with patch.object(w, "fetch_records", return_value=[record]):
            w.refresh()
        w.deliver()
        self.page.goto(self.base + "/index.html")
        expect(self.page.locator("#reminderAlert")).to_contain_text("天气预警发布")
        expect(self.page.locator("#reminderAlert")).to_contain_text("雷雨")
        self.page.locator("#reminderAlert").get_by_role(
            "button", name="知道了", exact=True
        ).click()
        (
            self.page.get_by_role("link", name="天气预警", exact=True).click()
            if self.page.get_by_role("link", name="天气预警", exact=True).count()
            else self.page.goto(self.base + "/weather-alerts.html")
        )
        expect(self.page.locator(".personal-grid")).to_contain_text("测试替身气象台")


if __name__ == "__main__":
    unittest.main()
