"""Browser regression checks for the static frontend.

Run: python front_end/tests/browser_smoke.py
Requires: playwright Python package and Chromium. No backend or API keys are used.
Live-mode checks intercept HTTP with contract-shaped responses; they do not validate
the real FastAPI service or the external model provider.
"""

import json
import os
from pathlib import Path
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright, expect


FRONTEND = Path(__file__).resolve().parents[1]
PHOTO = FRONTEND / "assets/wheat-green.jpg"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


class BackendDouble:
    """Controlled HTTP responses, with request capture for context assertions."""

    def __init__(self):
        self.uploads = []
        self.chats = []
        self.upload_error = False
        self.chat_error = False
        self.truncate = False
        self.hold_upload = False
        self.held = []

    def handle(self, route):
        request = route.request
        path = request.url.split("/api", 1)[1]
        if path == "/vision/upload":
            self.uploads.append(request.post_data_buffer)
            if self.hold_upload and len(self.uploads) == 1:
                self.held.append(route)
                return
            if self.upload_error:
                route.fulfill(status=502, json={"detail": "测试视觉服务不可用"})
            else:
                route.fulfill(json={"result": f"**本次真实接口测试描述 {len(self.uploads)}**\n\n叶片特征待结合现场确认。", "image_path": "/uploads/test.jpg", "case_id": 7})
        elif path == "/chat/stream":
            self.chats.append(request.post_data_json)
            if self.chat_error:
                route.fulfill(status=502, json={"detail": "测试模型暂不可用"})
                return
            events = [
                {"tool_call": {"tool": "get_weather", "args": {"location": "郑州"}}},
                {"tool_result": {"tool": "get_weather", "result": json.dumps({"source": "模拟", "weather": "测试天气"}, ensure_ascii=False)}},
                {"delta": "**接口测试回答**\n\n- 这是可核对的测试内容。\n- <img src=x onerror=window.__xss=1>"},
            ]
            if not self.truncate:
                events.append({"done": True, "conversation_id": 42, "case_id": self.chats[-1].get("case_id")})
            body = "".join("data: " + json.dumps(e, ensure_ascii=False) + "\n\n" for e in events)
            route.fulfill(content_type="text/event-stream; charset=utf-8", body=body)
        elif path == "/conversation/42/messages":
            route.fulfill(json=[{"role": "user", "content": "已保存问题", "created_at": "2026-04-18 10:00"}, {"role": "assistant", "content": "**已保存回答**", "created_at": "2026-04-18 10:00"}])
        elif path == "/history/list":
            route.fulfill(json=[{"id": 7, "thumbnail": "", "create_time": "2026-04-18 10:00", "status": "进行中", "summary": "<img src=x onerror=window.__xss=1> 历史摘要", "conversation_id": 42}])
        elif path == "/history/detail/7":
            route.fulfill(json={"id": 7, "image": "", "create_time": "2026-04-18 10:00", "status": "进行中", "recognition": "**实际接口测试描述**", "diagnosis": "<script>window.__xss=1</script>", "advice": "", "conversation_id": 42, "recheck_count": 2})
        elif path.endswith("/finish"):
            route.fulfill(json={"ok": True, "status": "已完成"})
        elif request.method == "DELETE":
            route.fulfill(json={"ok": True})
        else:
            route.fulfill(status=404, json={"detail": "测试未配置该路径"})


class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(FRONTEND)))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=os.environ.get("ZHIMAI_CHROMIUM", "/usr/bin/chromium"), headless=True, args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [], "Uncaught browser errors")

    def go(self, path):
        self.page.goto(self.base + "/" + path)

    def live(self, backend):
        settings = json.dumps({"zhimai.mode": "live", "zhimai.apiBase": self.base + "/api"})
        self.context.add_init_script(f"for (const [k,v] of Object.entries({settings})) localStorage.setItem(k,v);")
        self.context.route("**/api/**", backend.handle)

    def send(self, text):
        self.page.locator("#chatInput").fill(text)
        self.page.locator("#sendBtn").click()

    def test_pages_desktop_mobile_and_navigation(self):
        paths = ["index.html", "fields.html", "field.html?id=east", "compare.html", "tasks.html", "history.html", "diagnosis.html"]
        for width in [1440, 768, 390, 320]:
            self.page.set_viewport_size({"width": width, "height": 900})
            for path in paths:
                with self.subTest(width=width, path=path):
                    self.go(path)
                    expect(self.page.locator("main h1").first).to_be_visible()
                    self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
        self.page.get_by_role("button", name="展开导航").click()
        expect(self.page.get_by_role("link", name="我的地块", exact=True)).to_be_visible()
        self.page.get_by_role("link", name="我的地块", exact=True).click()
        expect(self.page).to_have_url(self.base + "/fields.html")

    def test_field_record_comparison_and_export(self):
        self.go("fields.html")
        self.page.get_by_role("button", name="新建地块", exact=True).click()
        dialog = self.page.locator("dialog")
        name = '测试麦田 <img src=x onerror=window.__xss=1>'
        dialog.locator('[name="name"]').fill(name)
        dialog.locator('[name="location"]').fill("河南省郑州市")
        dialog.locator('[name="area"]').fill("12.5")
        dialog.get_by_role("button", name="保存", exact=True).click()
        expect(self.page.locator(".field-detail-copy h1")).to_have_text(name)
        self.assertIsNone(self.page.evaluate("window.__xss"))
        field_id = self.page.url.split("id=", 1)[1]
        for day, title in [("2026-10-20", "第一次现场观察"), ("2026-10-22", "第二次现场观察")]:
            self.page.get_by_role("button", name="记录新观察", exact=True).click()
            dialog.locator('[name="date"]').fill(day)
            dialog.locator('[name="title"]').fill(title)
            dialog.locator('[name="note"]').fill("保留现场特征，尚未确认变化原因。")
            dialog.locator('[name="photo"]').set_input_files(str(PHOTO))
            dialog.get_by_role("button", name="保存", exact=True).click()
            expect(dialog).not_to_be_visible()
        self.page.reload()
        expect(self.page.locator(".timeline-entry")).to_have_count(2)
        with self.page.expect_download() as info:
            self.page.get_by_role("button", name="导出文字档案").click()
        self.assertIn("生长档案.md", info.value.suggested_filename)
        self.go("compare.html?fieldId=" + field_id)
        expect(self.page.locator(".comparison-shot")).to_have_count(2)
        self.page.get_by_role("button", name="滑动对比", exact=True).click()
        self.page.locator("#compareSlider").fill("30")
        expect(self.page.locator("#sliderValue")).to_have_text("30%")
        self.page.get_by_label("同一采样点", exact=True).check()
        self.page.locator("#comparisonNote").fill("两次观察均已记录；不直接根据光照差异判断长势。")
        self.page.get_by_role("button", name="保存对比记录").click()
        self.go("field.html?id=" + field_id)
        expect(self.page.locator(".timeline-entry")).to_have_count(3)
        expect(self.page.locator(".timeline-entry").first).to_contain_text("同一采样点")

    def test_tasks_persist_complete_and_reopen(self):
        self.go("tasks.html")
        original = self.page.locator(".task-row").count()
        self.page.locator(".task-check").first.click()
        expect(self.page.locator(".task-row")).to_have_count(original - 1)
        self.page.reload()
        expect(self.page.locator(".task-row")).to_have_count(original - 1)
        self.page.get_by_role("button", name="已完成", exact=True).click()
        row = self.page.locator(".task-row").filter(has_text="补拍固定采样点全景")
        expect(row).to_be_visible()
        row.locator(".task-check").click()
        self.page.get_by_role("button", name="待完成", exact=True).click()
        expect(self.page.locator(".task-row")).to_have_count(original)
        self.page.get_by_role("button", name="创建跟踪任务", exact=True).click()
        dialog = self.page.locator("dialog")
        dialog.locator('[name="title"]').fill("检查固定采样点")
        dialog.locator('[name="note"]').fill("带回新的照片")
        dialog.get_by_role("button", name="保存", exact=True).click()
        expect(self.page.locator(".task-row")).to_have_count(original + 1)
        self.page.get_by_role("button", name="搜索地块、任务").click()
        dialog.locator("#globalSearch").fill("检查固定采样点")
        dialog.locator('[data-result-task]').click()
        expect(dialog.locator("h2")).to_have_text("检查固定采样点")

    def test_demo_image_never_calls_backend_and_chat_restores(self):
        outgoing = []
        self.page.on("request", lambda r: outgoing.append(r.url) if "/chat" in r.url or "/vision/" in r.url else None)
        self.go("diagnosis.html")
        self.page.locator("#imageInput").set_input_files(str(PHOTO))
        expect(self.page.locator("#visionStatus")).to_contain_text("演示图片已就绪")
        expect(self.page.locator(".message-item")).to_have_count(0)
        self.send("叶片发黄，怎么补充信息？ <img src=x onerror=window.__xss=1>")
        expect(self.page.locator(".message-followups")).to_be_visible(timeout=10000)
        self.assertEqual(outgoing, [])
        self.assertIsNone(self.page.evaluate("window.__xss"))
        self.page.locator("#removeImage").click()
        expect(self.page.locator(".message-item")).to_have_count(2)
        self.page.reload()
        expect(self.page.locator(".message-item")).to_have_count(2)
        expect(self.page.locator(".message-bubble").last).to_contain_text("固定诊断场景演示")
        self.page.get_by_role("button", name="加入地块记录").click()
        expect(self.page.locator('dialog [name="note"]')).to_have_value(__import__('re').compile("以下为固定演示回答"))
        self.page.locator('dialog [data-close]').first.click()
        self.go("history.html")
        self.assertGreaterEqual(self.page.locator(".case-card").count(), 3)

    def test_live_text_image_context_and_safe_markdown(self):
        backend = BackendDouble()
        self.live(backend)
        self.go("diagnosis.html")
        self.send("先进行纯文本对话")
        expect(self.page.locator(".message-followups")).to_be_visible()
        self.assertIsNone(backend.chats[0]["vision_result"])
        self.page.locator("#imageInput").set_input_files(str(PHOTO))
        expect(self.page.locator("#visionStatus")).to_contain_text("图片识别完成")
        self.assertEqual(len(backend.chats), 1, "Selecting an image must not send chat")
        self.send("结合这张图分析")
        expect(self.page.locator(".message-followups")).to_have_count(2)
        self.assertIn("测试描述 1", backend.chats[-1]["vision_result"])
        self.assertEqual(backend.chats[-1]["image_path"], "/uploads/test.jpg")
        self.assertEqual(backend.chats[-1]["conversation_id"], 42)
        self.send("继续追问")
        expect(self.page.locator(".message-followups")).to_have_count(3)
        self.assertIsNone(backend.chats[-1]["vision_result"])
        self.assertEqual(self.page.locator(".message-bubble img").count(), 0)
        self.assertIsNone(self.page.evaluate("window.__xss"))
        expect(self.page.locator(".message-bubble strong").last).to_have_text("接口测试回答")
        expect(self.page.locator(".tool-trace").last).to_contain_text("模拟")
        self.page.reload()
        expect(self.page.locator(".message-bubble").last).to_contain_text("已保存回答")

    def test_demo_seed_case_followup_keeps_its_conversation(self):
        self.go("diagnosis.html?caseId=demo-east")
        expect(self.page.locator(".recheck-banner")).to_contain_text("东坡示范田")
        self.send("我补充了一条田间观察")
        expect(self.page.locator(".message-followups")).to_have_count(2, timeout=10000)
        self.page.reload()
        expect(self.page.locator(".message-item.user")).to_have_count(1)
        expect(self.page.locator(".message-bubble").last).to_contain_text("固定诊断场景演示")

    def test_failed_upload_clears_old_result_and_can_retry(self):
        backend = BackendDouble()
        self.live(backend)
        self.go("diagnosis.html")
        self.page.locator("#imageInput").set_input_files(str(PHOTO))
        expect(self.page.locator("#visionResult")).to_contain_text("测试描述 1")
        backend.upload_error = True
        self.page.locator("#imageInput").set_input_files(str(FRONTEND / "assets/wheat-gold.jpg"))
        expect(self.page.locator("#visionStatus")).to_contain_text("识别未完成")
        expect(self.page.locator("#visionResult")).not_to_contain_text("测试描述 1")
        self.send("不能使用旧图片结果")
        self.assertEqual(len(backend.chats), 0)
        backend.upload_error = False
        self.page.locator("#retryImage").click()
        expect(self.page.locator("#visionResult")).to_contain_text("测试描述 3")
        self.send("使用重试后的结果")
        expect(self.page.locator(".message-followups")).to_be_visible()
        self.assertIn("测试描述 3", backend.chats[-1]["vision_result"])

    def test_replaced_upload_ignores_late_response(self):
        backend = BackendDouble()
        backend.hold_upload = True
        self.live(backend)
        self.go("diagnosis.html")
        self.page.locator("#imageInput").set_input_files(str(PHOTO))
        expect(self.page.locator("#visionStatus")).to_contain_text("正在请求")
        self.page.locator("#imageInput").set_input_files(str(FRONTEND / "assets/wheat-gold.jpg"))
        expect(self.page.locator("#visionResult")).to_contain_text("测试描述 2")
        if backend.held:
            try:
                backend.held[0].fulfill(json={"result": "迟到的旧结果", "case_id": 999})
            except Exception:
                pass  # Aborting the first request may already have closed the route.
        expect(self.page.locator("#visionResult")).not_to_contain_text("迟到的旧结果")
        self.send("使用最新图片")
        expect(self.page.locator(".message-followups")).to_be_visible()
        self.assertEqual(backend.chats[-1]["case_id"], 7)
        self.assertIn("测试描述 2", backend.chats[-1]["vision_result"])

    def test_chat_failure_retry_and_truncation(self):
        backend = BackendDouble()
        backend.chat_error = True
        self.live(backend)
        self.go("diagnosis.html")
        self.send("测试失败后的重试")
        expect(self.page.locator(".message-error")).to_contain_text("测试模型暂不可用")
        backend.chat_error = False
        self.page.get_by_role("button", name="重试此问题").click()
        expect(self.page.locator(".message-followups")).to_be_visible()
        expect(self.page.locator(".message-item.user")).to_have_count(1)
        backend.truncate = True
        self.send("测试中断")
        expect(self.page.locator(".message-error")).to_contain_text("未收到完成确认")
        expect(self.page.locator(".message-bubble").last).to_contain_text("接口测试回答")

    def test_live_history_and_legacy_recheck_link(self):
        backend = BackendDouble()
        self.live(backend)
        self.go("history.html")
        expect(self.page.locator(".case-card")).to_have_count(1)
        self.page.locator(".case-card").click()
        expect(self.page.locator("dialog .rich-text").first).to_contain_text("实际接口测试描述")
        self.assertIsNone(self.page.evaluate("window.__xss"))
        self.page.get_by_role("link", name="继续对话与复查").click()
        expect(self.page.locator(".recheck-banner")).to_contain_text("案例 #7")
        expect(self.page.locator(".message-bubble").last).to_contain_text("已保存回答")
        self.go("index.html?caseId=7&conversationId=42")
        expect(self.page).to_have_url(self.base + "/diagnosis.html?caseId=7&conversationId=42")

    def test_sse_utf8_crlf_and_missing_terminal_event(self):
        self.go("diagnosis.html")
        result = self.page.evaluate("""async () => {
          const original=window.fetch;
          const results=[];
          async function run(text) {
            window.fetch=async()=>new Response(new ReadableStream({start(c){
              const bytes=new TextEncoder().encode(text);
              for(let i=0;i<bytes.length;i+=5)c.enqueue(bytes.slice(i,i+5));
              c.close();
            }}),{headers:{'Content-Type':'text/event-stream'}});
            let content='';
            try {const meta=await ZhimaiAPI.sendChatStream({message:'测试'},s=>content+=s);return {content,done:meta.done};}
            catch(e){return {content,error:e.message};}
          }
          try {
            results.push(await run('data: '+JSON.stringify({delta:'小麦中文🌾'})+'\\r\\n\\r\\ndata: '+JSON.stringify({done:true,conversation_id:1})+'\\r\\n\\r\\n'));
            results.push(await run('data: '+JSON.stringify({delta:'部分回复'})+'\\n\\n'));
            return results;
          } finally {window.fetch=original;}
        }""")
        self.assertEqual(result[0], {"content": "小麦中文🌾", "done": True})
        self.assertEqual(result[1]["content"], "部分回复")
        self.assertIn("未收到完成确认", result[1]["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
