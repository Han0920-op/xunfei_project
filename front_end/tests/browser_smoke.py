"""Farmer frontend regression tests. Lookup HTTP boundaries are mocked; no models."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
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
        self.errors, self.requests = [], []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.on('dialog', lambda d: d.accept())
        self.page.on('request', lambda r: self.requests.append(r.url))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def go(self, path='index.html'):
        self.page.goto(self.base+'/'+path)

    def send(self, text):
        self.page.locator('#messageInput').fill(text)
        self.page.locator('#sendButton').click()

    def diagnosis(self):
        self.go()
        self.send('叶片局部发黄')
        self.page.get_by_role('button',name='局部一片',exact=True).click()
        self.page.get_by_role('button',name='不清楚',exact=True).click()
        expect(self.page.locator('.answer-card')).to_be_visible()

    def medicine(self, number='DEMO-WHEAT-001', target='白粉病'):
        self.go('index.html?intent=medicine')
        self.send(number)
        self.page.get_by_role('button',name=target,exact=True).click()
        expect(self.page.locator('.answer-card')).to_be_visible()

    def mock_lookup(self, status='source_unavailable'):
        payload = {
            'status': status, 'heading': '登记资料暂不可用',
            'summary': '请核对官方登记信息及有效标签。', 'checks': [],
            'source': None, 'checked_at': '2026-10-26T10:00:00+08:00',
            'explanation': '人工核验快照，不是官方实时查询。',
            'registration_number': 'PD202600001', 'crop': '小麦', 'target': '白粉病',
        }
        self.page.route('**/api/pesticides/check', lambda r: r.fulfill(json=payload))
        return payload

    def test_real_check_sends_only_confirmed_text_and_keeps_source(self):
        self.mock_lookup()
        self.medicine('PD202600001')
        expect(self.page.locator('.answer-source')).to_contain_text('非官方实时查询')
        self.page.get_by_text('查询来源与时间',exact=True).click()
        expect(self.page.locator('.answer-card')).to_contain_text('没有可展示的登记来源')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].messages.at(-1).verification.status'), 'source_unavailable')
        self.page.reload()
        expect(self.page.locator('.answer-source')).to_contain_text('人工核验登记快照')

    def test_network_failure_preserves_target_and_retry(self):
        self.page.route('**/api/pesticides/check', lambda r: r.abort())
        self.go('index.html?intent=medicine')
        self.send('PD202600001')
        self.page.get_by_role('button',name='白粉病',exact=True).click()
        expect(self.page.locator('#sendError')).to_contain_text('连接不上')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].step'), 'target')
        self.page.unroute('**/api/pesticides/check')
        self.mock_lookup()
        self.page.get_by_role('button',name='重新发送',exact=True).click()
        expect(self.page.locator('.answer-card')).to_be_visible()
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].facts.target'), '白粉病')

    def test_invalid_registration_stays_at_number_without_network(self):
        self.go('index.html?intent=medicine')
        self.send('农药生产许可证123')
        expect(self.page.locator('.question-text').last).to_contain_text('格式还不完整')
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].step'), 'number')
        self.assertFalse(any('/api/pesticides/' in u for u in self.requests))

    def test_source_links_escape_untrusted_content(self):
        payload = self.mock_lookup('fields_match')
        payload.update(heading='字段相符', source={
            'url': 'javascript:alert(1)', 'title': '<img src=x onerror=alert(1)>',
            'reviewed_on': '2026-10-26', 'reviewer': '测试', 'label_version': '测试版本',
        })
        self.medicine('PD202600001')
        self.page.get_by_text('查询来源与时间',exact=True).click()
        expect(self.page.locator('.explanation a')).to_have_count(0)
        expect(self.page.locator('.answer-card img')).to_have_count(0)
        expect(self.page.locator('.answer-card')).to_contain_text('<img src=x')

    def test_knowledge_followup_citation_and_same_record(self):
        payload = {
            'status': 'found', 'next_question': '叶片白粉里有小黑点吗？',
            'choices': ['看到了', '没看到', '还没看清'],
            'notice': '用户上传资料，待农技审校，不能确诊。',
            'retrieved_at': '2026-10-27T12:00:00+08:00',
            'results': [{'topic': '小麦白粉病', 'paragraph': 'P0038',
                         'quote': '叶片表面覆盖白色粉状物，后期粉层变灰并出现小黑点。',
                         'source': {'title': '小麦知识库最新版.docx', 'docx_sha256': 'test'}}],
        }
        bodies = []
        def lookup(route):
            bodies.append(route.request.post_data_json)
            route.fulfill(json=payload)
        self.page.route('**/api/knowledge/assist', lookup)
        self.go()
        self.send('叶片上有白色粉状物')
        self.page.get_by_role('button',name='局部一片',exact=True).click()
        self.page.get_by_role('button',name='不清楚',exact=True).click()
        expect(self.page.locator('.question-text').last).to_contain_text('小黑点')
        self.assertEqual(set(bodies[0]), {'description', 'distribution', 'stage'})
        self.page.get_by_role('button',name='没看到',exact=True).click()
        expect(self.page.locator('.answer-card')).to_contain_text('先不要按相似病名判断')
        self.page.locator('.answer-card').get_by_text('参考了哪些资料？', exact=True).click()
        expect(self.page.locator('.answer-card .knowledge-evidence')).to_contain_text('P0038')
        expect(self.page.locator('.answer-card .knowledge-evidence')).to_contain_text('待农技审校')
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'), 1)
        self.page.reload()
        expect(self.page.locator('.answer-card')).to_contain_text('不能确定病因')

    def test_crop_drug_injury_is_not_personal_poisoning(self):
        self.go()
        self.send('麦苗打药后像中毒一样，叶片扭曲')
        expect(self.page.get_by_role('button',name='局部一片',exact=True)).to_be_visible()
        expect(self.page.locator('.answer-card')).to_have_count(0)

    def test_home_has_two_navigation_links_and_no_setup_form(self):
        self.go()
        expect(self.page.locator('nav a')).to_have_count(2)
        expect(self.page.get_by_role('button',name='拍照看病虫害',exact=False)).to_be_visible()
        expect(self.page.locator('aside.sidebar')).to_have_count(0)
        expect(self.page.locator('select')).to_have_count(0)
        expect(self.page.locator('input[name="region"]')).to_have_count(0)
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),0)
        self.go('history.html')
        expect(self.page.get_by_role('heading',name='还没有记录，先从一个问题开始')).to_be_visible()

    def test_text_guidance_is_one_question_at_a_time(self):
        self.go()
        self.send('叶片发黄了')
        expect(self.page.locator('.choices button')).to_have_count(4)
        expect(self.page.get_by_role('button',name='不清楚',exact=True)).to_have_count(0)
        self.page.get_by_role('button',name='还没看清',exact=True).click()
        expect(self.page.locator('.choices button')).to_have_count(5)
        self.page.get_by_role('button',name='不清楚',exact=True).click()
        expect(self.page.locator('.answer-card')).to_contain_text('不能确定病因')
        expect(self.page.locator('.answer-card')).to_contain_text('现在可以这样做')
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),1)
        self.page.reload()
        expect(self.page.locator('.answer-card')).to_be_visible()

    def test_photo_selection_does_not_send_and_recovers_from_indexeddb(self):
        self.go()
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        expect(self.page.locator('.attachment')).to_contain_text('已选好，还没发送')
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),0)
        self.send('请看这张照片')
        expect(self.page.get_by_role('button',name='只有几株',exact=True)).to_be_visible()
        expect(self.page.locator('.user-bubble img')).to_have_attribute('src',re.compile('^blob:'))
        self.page.reload()
        expect(self.page.locator('.user-bubble img')).to_have_attribute('src',re.compile('^blob:'))
        self.assertFalse(any('/vision/' in u or '/chat' in u for u in self.requests))

    def test_invalid_photo_never_reuses_old_attachment(self):
        self.go()
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        expect(self.page.locator('.attachment')).to_be_visible()
        self.page.locator('#photoInput').set_input_files({'name':'not-image.txt','mimeType':'text/plain','buffer':b'not image'})
        expect(self.page.locator('#fileError')).to_contain_text('请选择一张')
        expect(self.page.locator('.attachment')).not_to_be_visible()
        self.send('只发送文字')
        expect(self.page.locator('.choices')).to_be_visible()
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].photos.length'),0)

    def test_broken_image_and_oversize_have_clear_errors(self):
        self.go()
        self.page.locator('#photoInput').set_input_files({'name':'broken.jpg','mimeType':'image/jpeg','buffer':b'not really jpeg'})
        expect(self.page.locator('#fileError')).to_contain_text('照片没有读成功')
        self.page.locator('#photoInput').set_input_files({'name':'large.jpg','mimeType':'image/jpeg','buffer':b'x'*(10*1024*1024+1)})
        expect(self.page.locator('#fileError')).to_contain_text('超过 10 MB')

    def test_repeated_send_blocked_and_shift_enter_keeps_newline(self):
        self.go()
        self.page.locator('#messageInput').fill('第一行')
        self.page.locator('#messageInput').press('Shift+Enter')
        self.page.locator('#messageInput').press('x')
        expect(self.page.locator('#messageInput')).to_have_value('第一行\nx')
        self.page.locator('#sendButton').click()
        expect(self.page.locator('#sendButton')).to_be_disabled()
        expect(self.page.locator('.choices')).to_be_visible()
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].messages.filter(m=>m.role==="user").length'),1)

    def test_registration_number_can_be_sent_directly_from_home(self):
        self.go()
        self.send('PD202600001')
        expect(self.page.get_by_role('button',name='还没确定',exact=True)).to_be_visible()
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].facts.registration'),'PD202600001')
        self.mock_lookup()
        self.page.get_by_role('button',name='还没确定',exact=True).click()
        expect(self.page.locator('.answer-card')).to_contain_text('登记资料暂不可用')

    def test_medicine_stays_in_same_conversation(self):
        self.diagnosis()
        original_url=self.page.url
        self.page.get_by_role('button',name='核对手里的药',exact=True).click()
        expect(self.page.locator('.question-text').last).to_contain_text('登记证号')
        self.assertEqual(self.page.url,original_url)
        self.send('DEMO-INCOMPLETE-001')
        self.page.get_by_role('button',name='还没确定',exact=True).click()
        expect(self.page.locator('.answer-card').last).to_contain_text('缺少关键信息')
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),1)
        self.assertFalse(any('/api/pesticides/' in u for u in self.requests))

    def test_registration_examples_not_real_recommendations(self):
        self.medicine()
        expect(self.page.locator('.answer-card')).to_contain_text('示例字段相符')
        expect(self.page.locator('.answer-card')).to_contain_text('不是实际产品或用药建议')
        self.go()
        self.page.get_by_role('button',name='手里的药，能不能用？',exact=False).click()
        self.send('DEMO-MISMATCH-001')
        self.page.get_by_role('button',name='白粉病',exact=True).click()
        expect(self.page.locator('.answer-card')).to_contain_text('不匹配')
        expect(self.page.locator('.label-facts')).to_contain_text('水稻')

    def test_packaging_photo_requires_manual_number(self):
        self.go('index.html?intent=medicine')
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        expect(self.page.locator('.attachment')).to_be_visible()
        self.page.locator('#sendButton').click()
        expect(self.page.locator('.question-text').last).to_contain_text('不能识别登记号')
        self.assertIsNone(self.page.evaluate('FarmerStore.records()[0].facts.registration || null'))
        self.send('DEMO-INCOMPLETE-001')
        self.page.get_by_role('button',name='白粉病',exact=True).click()
        expect(self.page.locator('.answer-card')).to_contain_text('缺少关键信息')

    def test_followup_combines_new_photo_and_feedback(self):
        self.go()
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        expect(self.page.locator('.attachment')).to_be_visible()
        self.send('发现小虫子')
        self.page.get_by_role('button',name='只有几株',exact=True).click()
        self.page.get_by_role('button',name='不清楚',exact=True).click()
        expect(self.page.locator('.answer-card')).to_be_visible()
        self.go('history.html')
        self.page.get_by_role('button',name='来复查',exact=False).click()
        expect(self.page.get_by_role('button',name='更严重了',exact=True)).to_be_visible()
        self.page.locator('#photoInput').set_input_files(str(ROOT/'assets/wheat-gold.jpg'))
        expect(self.page.locator('.attachment')).to_be_visible()
        self.page.get_by_role('button',name='更严重了',exact=True).click()
        expect(self.page.locator('.answer-card').last).to_contain_text('农技人员现场复核')
        expect(self.page.locator('.photo-pair img')).to_have_count(2)
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].followups.length'),1)
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),1)

    def test_followup_without_new_photo_does_not_relabel_old_photo(self):
        self.diagnosis()
        self.go('history.html')
        self.page.get_by_role('button',name='来复查',exact=False).click()
        self.page.get_by_role('button',name='说不清楚',exact=True).click()
        expect(self.page.locator('.answer-card').last).to_contain_text('尚不能据此确认病因或药效')
        expect(self.page.locator('.photo-pair')).to_have_count(0)
        self.assertIsNone(self.page.evaluate('FarmerStore.records()[0].followups[0].photoId'))

    def test_action_schedule_export_and_archive(self):
        self.diagnosis()
        self.page.get_by_role('button',name='记下我做了什么',exact=False).click()
        dialog=self.page.locator('dialog')
        dialog.locator('[name="note"]').fill('还没有用药，先补拍了照片。')
        dialog.get_by_role('button',name='记下来',exact=True).click()
        expect(dialog).not_to_be_visible()
        self.assertEqual(self.page.evaluate('FarmerStore.records()[0].actions.length'),1)
        self.page.get_by_role('button',name='约个时间复查',exact=False).click()
        dialog.locator('[name="date"]').fill('2026-11-01')
        dialog.get_by_role('button',name='记下这个日期',exact=True).click()
        expect(self.page.locator('.followup-date')).to_contain_text('暂不推送通知')
        self.page.get_by_role('button',name='这条记录的更多操作').click()
        with self.page.expect_download() as info:
            dialog.get_by_role('button',name='下载文字摘要').click()
        self.assertIn('问题摘要.txt',info.value.suggested_filename)
        dialog.get_by_role('button',name='结束这次跟踪').click()
        expect(self.page.locator('.closed-record')).to_be_visible()
        self.page.get_by_role('button',name='继续跟踪',exact=True).click()
        expect(self.page.locator('#messageInput')).to_be_visible()

    def test_failed_save_keeps_draft_and_removes_orphan_photo(self):
        self.go()
        self.page.locator('#photoInput').set_input_files(str(PHOTO))
        expect(self.page.locator('.attachment')).to_be_visible()
        self.page.evaluate("() => {window.oldSetItem=Storage.prototype.setItem;Storage.prototype.setItem=()=>{throw new Error('quota')};}")
        self.send('不能丢失的描述')
        expect(self.page.locator('#sendError')).to_contain_text('没有保存成功')
        expect(self.page.locator('#messageInput')).to_have_value('不能丢失的描述')
        expect(self.page.locator('.attachment')).to_be_visible()
        self.assertEqual(self.page.evaluate('FarmerStore.records().length'),0)
        count=self.page.evaluate("""async()=>{const db=await new Promise(r=>{const q=indexedDB.open('zhimai.farmer.photos',1);q.onsuccess=()=>r(q.result)});return await new Promise(r=>{const q=db.transaction('photos').objectStore('photos').count();q.onsuccess=()=>r(q.result)});} """)
        self.assertEqual(count,0)
        self.page.evaluate('() => {Storage.prototype.setItem=window.oldSetItem;}')
        self.page.get_by_role('button',name='重新发送',exact=True).click()
        expect(self.page.locator('.choices')).to_be_visible()

    def test_legacy_records_not_reset_or_duplicate_images(self):
        old={'version':1,'fields':[{'id':'field-one','name':'原地块'}],'records':[],'tasks':[],'chats':[],'cases':[], 'clinicalCases':[{'id':'old-case','title':'原有叶片异常','symptoms':'旧版现场描述','image':'assets/wheat-green.jpg','demo':True,'createdAt':'2026-04-18','actions':[],'followups':[]}]}
        self.context.add_init_script(f"if(!localStorage.getItem('zhimai.frontend.v1'))localStorage.setItem('zhimai.frontend.v1',{json.dumps(json.dumps(old,ensure_ascii=False))});")
        self.go('history.html')
        self.page.get_by_role('button',name='来复查',exact=False).click()
        self.page.get_by_role('button',name='没有明显变化',exact=True).click()
        expect(self.page.locator('.answer-card')).to_be_visible()
        actual=self.page.evaluate("JSON.parse(localStorage.getItem('zhimai.frontend.v1'))")
        self.assertEqual(actual['fields'],old['fields'])
        self.assertEqual(actual['clinicalCases'],old['clinicalCases'])
        self.assertEqual(actual['farmerThreads'][0]['photos'][0]['legacyCaseId'],'old-case')
        self.assertNotIn('url',actual['farmerThreads'][0]['photos'][0])

    def test_unreadable_storage_never_overwritten(self):
        self.context.add_init_script("localStorage.setItem('zhimai.frontend.v1','not-json');")
        self.go()
        expect(self.page.locator('.storage-error')).to_contain_text('不会覆盖保存')
        self.send('叶片发黄')
        expect(self.page.locator('#sendError')).to_contain_text('不会覆盖保存')
        self.assertEqual(self.page.evaluate("localStorage.getItem('zhimai.frontend.v1')"),'not-json')

    def test_html_messages_display_as_text(self):
        self.go()
        self.send('<img src=x onerror=window.xss=1><script>window.xss=2</script>')
        expect(self.page.locator('.choices')).to_be_visible()
        expect(self.page.locator('.user-bubble')).to_contain_text('<img')
        expect(self.page.locator('.user-bubble img')).to_have_count(0)
        self.assertIsNone(self.page.evaluate('window.xss'))

    def test_explicit_other_crop_does_not_enter_wheat_investigation(self):
        self.go()
        self.send('我种的是玉米，叶片发黄了')
        expect(self.page.locator('.answer-card')).to_contain_text('对应作物的农技人员')
        expect(self.page.locator('.choices')).to_have_count(0)
        expect(self.page.get_by_role('button',name='核对手里的药',exact=True)).to_have_count(0)

    def test_personal_exposure_does_not_offer_crop_medication_actions(self):
        self.go()
        self.send('有人误服了农药')
        expect(self.page.locator('.answer-card')).to_contain_text('当地急救')
        expect(self.page.get_by_role('button',name='核对手里的药',exact=True)).to_have_count(0)
        expect(self.page.get_by_role('button',name='下载问题摘要',exact=True)).to_be_visible()

    def test_mobile_desktop_layout_and_legacy_links(self):
        for width in [1440,768,390,320]:
            self.page.set_viewport_size({'width':width,'height':900})
            for path in ['index.html','history.html','medication.html']:
                self.go(path)
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width,path)
                expect(self.page.locator('main h1')).to_be_visible()
        self.go('fields.html')
        expect(self.page).to_have_url(self.base+'/history.html')
        self.go('diagnosis.html')
        expect(self.page).to_have_url(self.base+'/index.html')

if __name__ == '__main__':
    unittest.main(verbosity=2)
