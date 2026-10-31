"""Free farmer conversation tests. Model/tool HTTP streams are mocked, never billed."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import hashlib
import os
import re
import threading
import unittest
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / 'assets/wheat-green.jpg'


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


START = {'type':'start', 'server_version':'2026.10.30.1', 'stream_protocol':'zhimai-chat-sse-v2'}

def stream(events):
    events = [START, *events]
    return ''.join('data: ' + json.dumps(event, ensure_ascii=False) + '\n\n' for event in events)


class FarmerFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=os.environ.get('ZHIMAI_CHROMIUM', '/usr/bin/chromium'), headless=True, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width':1440,'height':1000}, accept_downloads=True)
        self.page = self.context.new_page()
        self.errors, self.requests, self.bodies = [], [], []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.on('dialog', lambda d: d.accept())
        self.page.on('request', lambda r: self.requests.append(r.url))
        self.mock()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def mock(self, events=None):
        self.page.unroute('**/api/agent/chat')
        events = events or [{'type':'answer','content':'我先结合你提供的信息判断。请补一张叶背近景，暂不直接确定病因。'}, {'type':'done'}]
        def respond(route):
            self.bodies.append(route.request.post_data_buffer)
            route.fulfill(status=200, content_type='text/event-stream; charset=utf-8', body=stream(events))
        self.page.route('**/api/agent/chat', respond)

    def go(self, path='index.html'):
        self.page.goto(self.base+'/'+path)

    def send(self, text):
        self.page.locator('#messageInput').fill(text)
        self.page.locator('#sendButton').click()

    def answer(self):
        expect(self.page.locator('.agent-answer').last).to_be_visible()

    def test_home_is_free_chat_with_four_sidebar_links(self):
        self.go()
        expect(self.page.locator('nav a')).to_have_count(4)
        expect(self.page.locator('select')).to_have_count(0)
        self.send('小麦叶片发黄，昨天刚下过雨')
        self.answer()
        expect(self.page.locator('.choices')).to_have_count(0)
        expect(self.page.locator('.question-text')).to_have_count(0)
        expect(self.page.locator('.agent-answer')).to_contain_text('叶背近景')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].step'), 'chat')
        self.assertFalse(self.page.evaluate('FarmerStore.records()[0].demo'))

    def test_photo_waits_for_send_and_actual_file_is_uploaded(self):
        self.mock([{'type':'vision_result','status':'ok','content':'图片能看到麦穗，叶片细节不足。'}, {'type':'answer','content':'我看到了麦穗，现有照片不足以区分叶部病害。'}, {'type':'done'}])
        self.go()
        self.page.evaluate("""() => {const old=window.fetch;window.fetch=async(url,options)=>{const file=options?.body instanceof FormData?options.body.get('image'):null;if(file){const bytes=await file.arrayBuffer();window.__sentImageHash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('');}return old(url,options);}}""")
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        expect(self.page.locator('.attachment')).to_contain_text('已选好，还没发送')
        self.assertEqual(len(self.bodies), 0)
        self.page.locator('#sendButton').click()
        self.answer()
        self.assertIn(b'name="image"', self.bodies[0])
        self.assertEqual(self.page.evaluate("window.__sentImageHash"), hashlib.sha256(PHOTO.read_bytes()).hexdigest())
        self.page.reload()
        expect(self.page.locator('.user-bubble img')).to_have_attribute('src', re.compile('^blob:'))
        self.page.get_by_text('本次查看与查询依据', exact=True).click()
        expect(self.page.locator('.agent-evidence')).to_contain_text('叶片细节不足')
        self.assertIn('服务及模型', self.page.locator('.composer-caption').inner_text())

    def start_controlled_stream(self):
        self.page.evaluate("""() => {
          window.fetch = async () => new Response(new ReadableStream({
            start(controller) {
              window.__streamController = controller;
              controller.enqueue(new TextEncoder().encode('data: '+JSON.stringify({type:'start',server_version:'2026.10.30.1',stream_protocol:'zhimai-chat-sse-v2'})+'\\n\\n'));
            }
          }), {headers:{'Content-Type':'text/event-stream'}});
          window.__push = events => window.__streamController.enqueue(new TextEncoder().encode(events.map(e=>'data: '+JSON.stringify(e)+'\\n\\n').join('')));
        }""")

    def test_live_tokens_visible_before_completion_and_not_saved_twice(self):
        self.go()
        self.start_controlled_stream()
        self.send('边生成边看')
        expect(self.page.locator('#sendButton')).to_be_disabled()
        self.page.evaluate("__push([{type:'answer_delta',content:'第一段中文。'}])")
        expect(self.page.locator('#streamingAnswer')).to_be_visible()
        expect(self.page.locator('#streamingAnswer')).to_have_text('第一段中文。')
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'), 0)
        self.page.evaluate("__push([{type:'answer_delta',content:'<img src=x onerror=alert(1)>第二段。'}])")
        expect(self.page.locator('#streamingAnswer img')).to_have_count(0)
        expect(self.page.locator('#streamingAnswer')).to_contain_text('第二段')
        self.page.evaluate("__push([{type:'answer',content:'第一段中文。<img src=x onerror=alert(1)>第二段。'},{type:'done'}]); __streamController.close()")
        self.answer()
        expect(self.page.locator('.agent-answer')).to_have_text('第一段中文。<img src=x onerror=alert(1)>第二段。')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].messages.length'), 2)

    def test_old_backend_is_detected_and_draft_retained(self):
        self.page.unroute('**/api/agent/chat')
        self.page.route('**/api/agent/chat', lambda route: route.fulfill(status=200, content_type='text/event-stream', body='data: {"type":"status","message":"old backend"}\n\n'))
        self.go()
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        self.send('帮我看这张图')
        expect(self.page.locator('#sendError')).to_contain_text('重启后端')
        expect(self.page.locator('#messageInput')).to_have_value('帮我看这张图')
        expect(self.page.locator('.attachment')).to_be_visible()
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'), 0)

    def test_mobile_stop_remains_visible_and_diagnostics_record_real_chunks(self):
        self.page.set_viewport_size({'width':320,'height':844})
        self.go()
        self.start_controlled_stream()
        self.send('逐段显示')
        stop = self.page.get_by_role('button', name='停止生成', exact=True)
        expect(stop).to_be_visible()
        box = stop.bounding_box()
        self.assertLessEqual(box['x'] + box['width'], 320)
        self.assertGreaterEqual(box['x'], 0)
        self.page.evaluate("__push([{type:'answer_delta',content:'第一段'}])")
        expect(self.page.locator('#streamingAnswer')).to_have_text('第一段')
        self.page.evaluate("__push([{type:'answer_delta',content:'第二段'},{type:'stream_stats',model_calls:1,upstream_content_chunks:2,answer_delta_events:2},{type:'answer',content:'第一段第二段'},{type:'done'}]);__streamController.close()")
        self.answer()
        data = self.page.evaluate('FarmerAssistant.diagnostics().last_request')
        self.assertEqual(data['answer_delta_events'], 2)
        self.assertEqual(data['server']['upstream_content_chunks'], 2)
        self.assertGreaterEqual(data['network_reads'], 2)
        self.assertEqual(data['server_version'], '2026.10.30.1')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].messages.at(-1).transport'), data)

    def test_error_code_survives_for_support_without_saving_failed_record(self):
        self.mock([{'type':'error','code':'model_auth_failed','message':'讯飞文字服务鉴权失败。诊断编号：test123。'}])
        self.go()
        self.send('请判断黄叶原因')
        expect(self.page.locator('#sendError')).to_contain_text('鉴权失败')
        self.assertEqual(self.page.evaluate('FarmerAssistant.diagnostics().last_request.error_code'), 'model_auth_failed')
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'), 0)
        expect(self.page.get_by_role('button', name='重新核对登记号', exact=True)).to_have_count(0)

    def test_stop_and_stream_error_retract_preview_and_preserve_draft(self):
        for stop in [True, False]:
            self.go()
            self.start_controlled_stream()
            self.page.locator('#photoInput').set_input_files(str(PHOTO))
            expect(self.page.locator('.attachment')).to_be_visible()
            self.send('保留我的输入')
            self.page.wait_for_function('Boolean(window.__streamController)')
            self.page.evaluate("__push([{type:'answer_delta',content:'尚未完成的内容'}])")
            expect(self.page.locator('#streamingAnswer')).to_have_text('尚未完成的内容')
            if stop:
                self.page.get_by_role('button', name='停止生成', exact=True).click()
                expect(self.page.locator('#sendError')).to_contain_text('已停止生成')
            else:
                self.page.evaluate("__push([{type:'error',message:'响应中断'}]); __streamController.close()")
                expect(self.page.locator('#sendError')).to_contain_text('响应中断')
            expect(self.page.locator('#streamingAnswer')).to_have_count(0)
            expect(self.page.locator('#messageInput')).to_have_value('保留我的输入')
            expect(self.page.locator('.attachment')).to_be_visible()
            self.assertEqual(self.page.evaluate('FarmerStore.records().length'), 0)

    def test_weather_tool_result_is_shown_and_no_client_fabrication(self):
        events = [{'type':'tool_call','tool':'get_weather','args':{'location':'郑州'}}, {'type':'tool_result','tool':'get_weather','result':{'status':'unavailable','message':'天气密钥未配置，本次没有取得真实天气。'}}, {'type':'answer','content':'我暂时查不到真实天气，不能据此判断施药窗口。'}, {'type':'done'}]
        self.mock(events)
        self.go()
        self.send('帮我查郑州天气')
        self.answer()
        self.page.get_by_text('本次查看与查询依据', exact=True).click()
        expect(self.page.locator('.agent-evidence')).to_contain_text('没有取得真实天气')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].messages.at(-1).toolCalls[0].tool'), 'get_weather')
        self.assertFalse(any('/api/knowledge/assist' in u or '/api/pesticides/check' in u for u in self.requests))

    def test_answer_review_is_saved_shown_and_exported_with_observations(self):
        self.mock([{'type':'vision_result','status':'ok','content':'幼苗状叶片发黄'}, {'type':'answer_review','status':'revised','issue_codes':['history_conflict']}, {'type':'answer','content':'这张照片不能按成熟收获处理。'}, {'type':'done'}])
        self.go()
        self.send('帮我看第二张图')
        self.answer()
        self.page.reload()
        self.page.get_by_text('本次查看与查询依据', exact=True).click()
        expect(self.page.locator('.agent-evidence')).to_contain_text('已调整回答')
        expect(self.page.locator('.agent-evidence')).to_contain_text('不代表农技审校')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].messages.at(-1).review.status'), 'revised')
        with self.page.expect_download() as download:
            self.page.get_by_role('button', name='下载问题摘要').click()
        exported = Path(download.value.path()).read_text()
        self.assertIn('图片观察（ok，非确诊）：幼苗状叶片发黄', exported)
        self.assertIn('history_conflict', exported)

    def test_pending_user_bubble_and_photo_are_ephemeral_until_done(self):
        pending = []
        self.page.unroute('**/api/agent/chat')
        self.page.route('**/api/agent/chat', lambda route: pending.append(route))
        self.go()
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        expect(self.page.locator('.attachment')).to_be_visible()
        self.send('先看这张照片')
        expect(self.page.locator('.pending-message')).to_contain_text('先看这张照片')
        expect(self.page.locator('.pending-message img')).to_have_attribute('src', re.compile('^blob:'))
        expect(self.page.locator('.attachment')).to_be_hidden()
        expect(self.page.locator('#agentProgress')).to_be_visible()
        expect(self.page.locator('#sendButton')).to_be_disabled()
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'), 0)
        self.assertIsNone(self.page.evaluate('localStorage.getItem("zhimai.frontend.v1")'))
        pending.pop().fulfill(content_type='text/event-stream', body=stream([{'type':'answer','content':'图片已经查看，请继续说说你关心的变化。'},{'type':'done'}]))
        self.answer()
        expect(self.page.locator('.pending-message')).to_have_count(0)
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].messages.length'), 2)
        self.send('补充第二句话')
        expect(self.page.locator('.pending-message')).to_contain_text('补充第二句话')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].messages.length'), 2)
        pending.pop().fulfill(content_type='text/event-stream', body=stream([{'type':'error','message':'模型暂时不可用'}]))
        expect(self.page.locator('#sendError')).to_contain_text('模型暂时不可用')
        expect(self.page.locator('.pending-message')).to_have_count(0)
        expect(self.page.locator('#messageInput')).to_have_value('补充第二句话')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].messages.length'), 2)

    def test_prior_conversation_and_only_current_image_are_sent(self):
        self.go()
        self.send('我在郑州，叶片出现白粉')
        self.answer()
        self.send('今天刚发现，是否需要补拍？')
        expect(self.page.locator('.agent-answer')).to_have_count(2)
        self.assertIn('我在郑州'.encode(), self.bodies[-1])
        self.assertIn('我先结合'.encode(), self.bodies[-1])
        self.assertNotIn(b'name="image"', self.bodies[-1])
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'), 1)

    def test_medicine_entry_does_not_start_fixed_number_target_questions(self):
        self.go('index.html?intent=medicine')
        expect(self.page.locator('#messageInput')).to_have_value('我想核对手里的药：')
        self.assertEqual(len(self.bodies), 0)
        self.send('PD20250010，我想防治赤霉病')
        self.answer()
        expect(self.page.locator('.choices')).to_have_count(0)
        self.assertIn('PD20250010'.encode(), self.bodies[0])

    def test_unavailable_model_preserves_photo_and_draft_for_retry(self):
        self.page.unroute('**/api/agent/chat')
        self.page.route('**/api/agent/chat', lambda route: route.fulfill(status=503, json={'detail':'尚未配置讯飞模型，请先配置后重试。'}))
        self.go()
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        expect(self.page.locator('.attachment')).to_be_visible()
        self.send('看看叶片')
        expect(self.page.locator('#sendError')).to_contain_text('尚未配置讯飞模型')
        expect(self.page.locator('#messageInput')).to_have_value('看看叶片')
        expect(self.page.locator('.attachment')).to_be_visible()
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),0)
        self.mock()
        self.page.get_by_role('button',name='重新发送',exact=True).click()
        self.answer()
        self.assertIn(b'name="image"',self.bodies[-1])

    def test_incomplete_stream_never_saves_partial_answer(self):
        self.mock([{'type':'answer','content':'半截回答，不应保存'}])
        self.go()
        self.send('帮我分析')
        expect(self.page.locator('#sendError')).to_contain_text('对话中断')
        expect(self.page.locator('#messageInput')).to_have_value('帮我分析')
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),0)

    def test_sse_error_after_answer_never_commits(self):
        self.mock([{'type':'answer','content':'不完整'}, {'type':'error','message':'模型服务中断，请重试。'}, {'type':'done'}])
        self.go()
        self.send('看看小麦')
        expect(self.page.locator('#sendError')).to_contain_text('模型服务中断')
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),0)

    def test_legacy_wizard_is_readable_but_choices_do_not_resume(self):
        record = {'id':'old-demo','title':'此前异常','step':'distribution','kind':'disease','demo':True,'messages':[{'id':'u','role':'user','text':'旧症状'},{'id':'a','role':'assistant','type':'question','text':'旧固定问题','choices':['只有几株']}], 'photos':[], 'actions':[], 'followups':[], 'facts':{}, 'createdAt':'2026-10-27','updatedAt':'2026-10-27'}
        state={'farmerThreads':[record], 'fields':[{'id':'preserved'}]}
        self.page.add_init_script('localStorage.setItem("zhimai.frontend.v1", '+json.dumps(json.dumps(state)) + ')')
        self.go('index.html?record=old-demo')
        expect(self.page.locator('.choices')).to_have_count(0)
        self.send('继续帮我看看')
        self.answer()
        self.assertEqual(self.page.evaluate('JSON.parse(localStorage.getItem("zhimai.frontend.v1")).fields[0].id'),'preserved')
        self.assertNotIn('旧固定问题'.encode(), self.bodies[-1])
        self.assertIn('旧症状'.encode(), self.bodies[-1])

    def test_followup_is_a_contextual_free_message(self):
        self.go()
        self.send('叶子出现白粉')
        self.answer()
        self.go('history.html')
        self.page.get_by_role('button',name='来复查',exact=False).click()
        expect(self.page.locator('#messageInput')).to_have_value('我来复查这次的问题，现在的情况是：')
        expect(self.page.locator('.choices')).to_have_count(0)
        self.send('我来复查，昨天没有用药，今天白粉更多了')
        expect(self.page.locator('.agent-answer')).to_have_count(2)
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].followups[0].note'),'我来复查，昨天没有用药，今天白粉更多了')

    def test_storage_failure_preserves_inputs_and_removes_orphan_photo(self):
        self.go()
        self.page.evaluate('() => {Storage.prototype.setItem = function(){throw new DOMException("Quota exceeded", "QuotaExceededError")}}')
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        expect(self.page.locator('.attachment')).to_be_visible()
        self.send('保存失败也要保留输入')
        expect(self.page.locator('#sendError')).to_contain_text('没有保存成功')
        expect(self.page.locator('#messageInput')).to_have_value('保存失败也要保留输入')
        expect(self.page.locator('.attachment')).to_be_visible()
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),0)
        count=self.page.evaluate('''() => new Promise((resolve,reject)=>{const r=indexedDB.open("zhimai.farmer.photos",1);r.onsuccess=()=>{const q=r.result.transaction("photos").objectStore("photos").count();q.onsuccess=()=>resolve(q.result)}})''')
        self.assertEqual(count,0)

    def test_model_and_tool_html_are_text(self):
        self.mock([{'type':'tool_result','tool':'get_weather','result':{'status':'unavailable','message':'<img src=x onerror=alert(1)>'}}, {'type':'answer','content':'<script>alert(1)</script>\n保持不确定。'}, {'type':'done'}])
        self.go()
        self.send('<img src=x onerror=alert(1)>')
        self.answer()
        expect(self.page.locator('.agent-answer')).to_contain_text('<script>')
        self.page.get_by_text('本次查看与查询依据', exact=True).click()
        expect(self.page.locator('.agent-evidence img')).to_have_count(0)
        expect(self.page.locator('.agent-evidence')).to_contain_text('<img src=x')

    def test_actual_action_schedule_export_and_archive_still_work(self):
        self.go()
        self.send('发现小虫')
        self.answer()
        self.page.get_by_role('button',name='记下我做了什么',exact=False).click()
        self.page.locator('#actionText').fill('尚未用药，已补拍照片')
        self.page.get_by_role('button',name='记下来',exact=True).click()
        expect(self.page.locator('.messages')).to_contain_text('尚未用药，已补拍照片')
        self.page.get_by_role('button',name='约个时间复查',exact=False).click()
        self.page.locator('input[name="date"]').fill('2099-01-01')
        self.page.get_by_role('button',name='记下这个日期',exact=True).click()
        expect(self.page.locator('.followup-date')).to_contain_text('2099.01.01')
        self.page.get_by_role('button',name='这条记录的更多操作',exact=True).click()
        with self.page.expect_download() as dl:
            self.page.get_by_role('button',name='下载文字摘要',exact=False).click()
        self.assertIn('问题摘要',dl.value.suggested_filename)
        self.page.get_by_role('button',name='结束这次跟踪',exact=False).click()
        expect(self.page.locator('.closed-record')).to_be_visible()
        self.page.get_by_role('button',name='继续跟踪',exact=True).click()
        expect(self.page.locator('#messageInput')).to_be_visible()

    def test_prior_vision_and_dated_weather_are_context_not_new_evidence(self):
        self.mock([{'type':'vision_result','status':'ok','content':'上一轮图像显示叶尖局部发黄。'}, {'type':'tool_result','tool':'get_weather','result':{'status':'ok','location':'郑州','report_time':'2026-10-27T10:00:00+08:00'}}, {'type':'answer','content':'很长的此前回复。'*600}, {'type':'done'}])
        self.go()
        self.send('先帮我记录情况')
        self.answer()
        self.send('接着看昨天的情况')
        expect(self.page.locator('.agent-answer')).to_have_count(2)
        self.assertIn('上一轮图像显示叶尖局部发黄'.encode(),self.bodies[-1])
        self.assertIn('非本轮新识别'.encode(),self.bodies[-1])
        self.assertIn('历史天气记录'.encode(),self.bodies[-1])
        self.assertIn(b'2026-10-27T10:00:00',self.bodies[-1])

    def test_unreadable_storage_is_never_overwritten(self):
        self.page.add_init_script('localStorage.setItem("zhimai.frontend.v1", "{broken")')
        self.go()
        expect(self.page.locator('.storage-error')).to_be_visible()
        self.send('不要覆盖旧记录')
        expect(self.page.locator('#sendError')).to_contain_text('不会覆盖保存')
        self.assertEqual(self.page.evaluate('localStorage.getItem("zhimai.frontend.v1")'),'{broken')

    def test_invalid_photo_does_not_replace_current_file(self):
        self.go()
        self.page.locator('#photoInput').set_input_files({'name':'bad.jpg','mimeType':'image/jpeg','buffer':b'not an image'})
        expect(self.page.locator('#fileError')).to_contain_text('照片没有读成功')
        self.assertEqual(len(self.bodies),0)

    def test_mobile_and_desktop_have_no_horizontal_overflow(self):
        for width in [1440,768,390,320]:
            self.page.set_viewport_size({'width':width,'height':900})
            self.go()
            self.send('直接聊小麦情况')
            self.answer()
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width)

    def test_fragmented_utf8_sse_and_progress_callbacks(self):
        self.go()
        result=self.page.evaluate('''async () => {
          const data = 'data: '+JSON.stringify({type:'start',server_version:'2026.10.30.1',stream_protocol:'zhimai-chat-sse-v2'})+'\\n\\n'+'data: '+JSON.stringify({type:'status',message:'正在查看照片'})+'\\r\\n\\r\\n'+'data: '+JSON.stringify({type:'answer',content:'中文图片观察'})+'\\n\\n'+'data: '+JSON.stringify({type:'done'})+'\\n\\n';
          const bytes = new TextEncoder().encode(data); const old=window.fetch;
          window.fetch=async()=>new Response(new ReadableStream({start(c){for(let i=0;i<bytes.length;i+=7)c.enqueue(bytes.slice(i,i+7));c.close()}}),{headers:{'content-type':'text/event-stream'}});
          const progress=[];
          try {const record=await FarmerAssistant.respond(null,{text:'测试',onProgress:m=>progress.push(m)});return {text:record.messages.at(-1).text,progress};}finally{window.fetch=old;}
        }''')
        self.assertEqual(result['text'],'中文图片观察')
        self.assertIn('正在查看照片',result['progress'])


if __name__=='__main__':
    unittest.main(verbosity=2)
