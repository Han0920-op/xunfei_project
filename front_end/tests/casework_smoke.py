"""Real browser workflow for owned cases and regional opt-in, no paid APIs."""

import json, os, socket, sys, tempfile, threading, time, unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import uvicorn
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "back_end"))
import personal, memory, casework, agri_sources
from main import app


class CaseworkBrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(personal, "PATH", Path(self.tmp.name) / "test.db")
        self.p.start()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(
            uvicorn.Config(
                app, host="127.0.0.1", port=port, log_level="error", lifespan="off"
            )
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("server not ready")
            time.sleep(0.02)
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        self.context = self.browser.new_context(viewport={"width": 390, "height": 844})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.context.request.get(self.base + "/api/personal/session")
        self.who = next(
            c["value"] for c in self.context.cookies() if c["name"] == "zhimai_owner"
        )
        memory.save_turn(
            self.who,
            "case",
            "t",
            "黄叶需要复查",
            "请观察新叶",
            [],
            [],
            False,
            assessment={
                "symptoms": "叶尖黄化",
                "candidate_causes": ["原因尚不能确定"],
                "missing_information": ["补拍叶背近照"],
                "review_required": False,
            },
        )

    def tearDown(self):
        self.browser.close()
        self.pw.stop()
        self.server.should_exit = True
        self.thread.join(5)
        self.p.stop()
        self.tmp.cleanup()
        self.assertEqual(self.errors, [])

    def overflow(self):
        self.assertFalse(
            self.page.evaluate("document.documentElement.scrollWidth>innerWidth")
        )

    def test_case_feedback_report_and_case_bound_manual_reminder(self):
        self.page.goto(self.base + "/memory.html?case=case")
        expect(
            self.page.get_by_role("heading", name="待补充信息", exact=True)
        ).to_be_visible()
        self.overflow()
        self.page.get_by_role("button", name="记录变化与措施", exact=True).click()
        self.page.locator("[name=change]").select_option("worse")
        self.page.locator("[name=notes]").fill("新叶也发黄了")
        self.page.locator("[name=measures]").fill("只补充观察，未施药")
        self.page.get_by_role("button", name="确认记录", exact=True).click()
        expect(
            self.page.get_by_role("heading", name="需农技复核", exact=True)
        ).to_be_visible()
        self.assertEqual(
            memory.facts(self.who, "case")[0]["content"], "只补充观察，未施药"
        )
        self.page.get_by_role("button", name="生成依据报告", exact=True).click()
        expect(
            self.page.get_by_role("link", name="下载完整报告", exact=True)
        ).to_be_visible()
        self.page.get_by_role("link", name="约时间复查", exact=True).click()
        self.page.get_by_role("button", name="新增提醒", exact=True).click()
        expect(self.page.locator("[name=task_type]")).to_have_value("followup")
        expect(self.page.locator("[name=case_id]")).to_have_value("case")
        self.page.locator("[name=notes]").fill("补拍新叶和叶背")
        self.page.get_by_role("button", name="确认设置提醒", exact=True).click()
        expect(
            self.page.get_by_role("link", name="查看关联案例", exact=True)
        ).to_be_visible()
        self.assertEqual(personal.listing(self.who, "tasks")[0]["case_id"], "case")
        self.overflow()
        task = personal.listing(self.who, "tasks")[0]
        with patch.object(
            personal, "now", return_value=personal.now() + timedelta(minutes=10)
        ):
            personal.tick()
        self.page.evaluate("ZhimaiReminders.refresh()")
        expect(
            self.page.get_by_role("link", name="回到案例补图与复查", exact=True)
        ).to_be_visible()
        self.page.get_by_role("link", name="回到案例补图与复查", exact=True).click()
        expect(
            self.page.get_by_role("heading", name="需农技复核", exact=True)
        ).to_be_visible()

    def test_region_subscribe_pause_delete_and_no_fake_current_risk(self):
        self.page.goto(self.base + "/intelligence.html")
        expect(
            self.page.get_by_role("heading", name="地区订阅", exact=True)
        ).to_be_visible()
        self.overflow()
        expect(self.page.locator(".personal-banner")).to_contain_text("当前没有")
        self.page.get_by_role("button", name="新增地区订阅", exact=True).click()
        self.page.locator("[name=province]").select_option(label="河南")
        self.page.locator("[name=city]").fill("郑州")
        self.page.get_by_label("条锈病", exact=True).check()
        self.page.get_by_role("button", name="确认订阅", exact=True).click()
        expect(
            self.page.get_by_role("heading", name="河南 郑州", exact=True)
        ).to_be_visible()
        self.assertEqual(agri_sources.subscriptions(self.who)[0]["province"], "河南")
        self.overflow()
        self.page.get_by_role("button", name="编辑与暂停", exact=True).click()
        self.page.locator("[name=enabled]").select_option("false")
        self.page.get_by_role("button", name="确认订阅", exact=True).click()
        expect(self.page.locator(".personal-grid").first).to_contain_text("已暂停")
        self.page.get_by_role("button", name="取消订阅", exact=True).click()
        self.page.get_by_role("button", name="确认取消订阅", exact=True).click()
        expect(
            self.page.get_by_role("heading", name="从一个关心的地区开始", exact=True)
        ).to_be_visible()

    def test_private_photos_recover_in_same_owned_case_from_new_device(self):
        from PIL import Image
        import io

        out = io.BytesIO()
        Image.new("RGB", (30, 30), "green").save(out, format="JPEG")
        memory.save_turn(
            self.who,
            "case",
            "photo-turn",
            "新照片",
            "仍需核实",
            [{"status": "ok", "content": "可见黄叶"}],
            [],
            True,
            "saved-photo",
            out.getvalue(),
        )
        self.page.goto(self.base + "/memory.html?case=case")
        expect(self.page.get_by_alt_text("案例诊断照片")).to_be_visible()
        self.assertTrue(
            self.page.get_by_alt_text("案例诊断照片").evaluate(
                "(img)=>img.complete&&img.naturalWidth>0"
            )
        )
        self.page.get_by_role("link", name="带新照片继续咨询", exact=True).click()
        expect(self.page.locator(".thread-heading h1")).to_have_text("黄叶需要复查")
        self.assertEqual(
            self.page.evaluate("FarmerStore.records()[0].photos[0].serverUrl"),
            "/api/casework/cases/case/photos/saved-photo",
        )
        self.overflow()


if __name__ == "__main__":
    unittest.main()
