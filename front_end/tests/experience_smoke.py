"""User-facing prompt selection, secondary navigation and responsive visuals."""

import unittest
from pathlib import Path
from playwright.sync_api import expect
import casework_smoke as helper

ARTIFACTS = Path("/workspace/artifacts/zhimai-experience")
PHOTO = Path(__file__).resolve().parents[1] / "assets/wheat-green.jpg"


class ExperienceTests(unittest.TestCase):
    setUp = helper.CaseworkBrowserTests.setUp
    tearDown = helper.CaseworkBrowserTests.tearDown
    overflow = helper.CaseworkBrowserTests.overflow

    def test_photo_prompts_are_editable_and_do_not_send(self):
        requests = []
        self.page.on(
            "request",
            lambda r: requests.append(r.url) if "/api/agent/chat" in r.url else None,
        )
        self.page.goto(self.base + "/index.html")
        self.page.locator("#photoInput").set_input_files(str(PHOTO))
        expect(self.page.get_by_role("region", name="图片提问建议")).to_be_visible()
        expect(self.page.locator("#messageInput")).to_contain_text(
            "区分可见症状与可能原因"
        )
        expect(
            self.page.get_by_role("button", name="对比复查", exact=True)
        ).to_have_count(0)
        self.page.get_by_role("button", name="核对农药包装", exact=True).click()
        expect(self.page.locator("#messageInput")).to_have_value(
            "请识别这张农药包装照片上清晰可见的登记号、成分、含量和剂型，看不清的字段请注明，不猜测。请先让我确认识别结果，再提示需要核对的登记与标签信息。"
        )
        self.page.locator("#messageInput").fill(
            "我的包装登记号看不清，请先转录清晰的成分。"
        )
        self.page.locator("#photoInput").set_input_files(str(PHOTO))
        expect(self.page.locator("#messageInput")).to_have_value(
            "我的包装登记号看不清，请先转录清晰的成分。"
        )
        self.assertEqual(requests, [])
        self.overflow()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.screenshot(
            path=str(ARTIFACTS / "photo-prompts-mobile.png"), full_page=True, animations="disabled"
        )

    def test_secondary_navigation_preserves_chat_and_separates_sections(self):
        self.page.set_viewport_size({"width": 1440, "height": 1000})
        self.page.goto(self.base + "/index.html")
        self.page.locator("#messageInput").fill("郑州的小麦，等我看完订阅再继续")
        self.page.locator(".alert-nav > summary").click()
        self.page.get_by_role("link", name="地区订阅", exact=True).click()
        view = self.page.frame_locator("iframe.app-navigation-view:not([hidden])")
        expect(view.get_by_role("heading", name="地区订阅", exact=True)).to_be_visible()
        expect(
            view.get_by_role("heading", name="官方来源与资料状态", exact=True)
        ).to_have_count(0)
        view.get_by_role("link", name="植保资讯", exact=True).click()
        expect(view.get_by_role("heading", name="植保资讯", exact=True)).to_be_visible()
        expect(
            view.get_by_role("heading", name="官方来源与资料状态", exact=True)
        ).to_be_visible()
        expect(
            view.get_by_role("button", name="新增地区订阅", exact=True)
        ).to_have_count(0)
        view.get_by_role("link", name="提醒任务", exact=True).click()
        expect(view.get_by_role("heading", name="提醒任务", exact=True)).to_be_visible()
        view.get_by_role("button", name="检查消息", exact=True).click()
        expect(view.locator("[data-tab=notifications]")).to_have_class("selected")
        self.assertIn("tab=notifications", self.page.url)
        view.get_by_role("navigation", name="主导航").get_by_role(
            "link", name="问智麦", exact=True
        ).click()
        expect(self.page.locator("#messageInput")).to_have_value(
            "郑州的小麦，等我看完订阅再继续"
        )

    def test_home_mobile_navigation_and_reduced_motion(self):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.page.goto(self.base + "/index.html")
        for width in (1440, 390, 320):
            self.page.set_viewport_size({"width": width, "height": 1000})
            expect(
                self.page.get_by_role("heading", name="小麦不对劲？ 拍一张，一起看看。")
            ).to_be_visible()
            self.overflow()
            self.page.screenshot(
                path=str(ARTIFACTS / f"home-{width}.png"), full_page=True, animations="disabled"
            )
        self.page.get_by_role("button", name="打开导航", exact=True).click()
        self.page.locator(".alert-nav > summary").click()
        expect(
            self.page.get_by_role("link", name="植保资讯", exact=True)
        ).to_be_visible()
        self.page.keyboard.press("Escape")
        self.page.emulate_media(reduced_motion="reduce")
        self.assertEqual(
            self.page.locator(".field-wheat > span").first.evaluate(
                "(e) => getComputedStyle(e).animationName"
            ),
            "none",
        )
