"""Real browser -> uvicorn -> temporary synthetic catalog integration test.

No model, official service, existing DB or user records are touched.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, expect

BACKEND = Path(__file__).resolve().parents[2] / "back_end"
sys.path.insert(0, str(BACKEND))
from test_pesticides import fixture  # synthetic records, never production data
from pesticides import DEFAULT_CATALOG


class LiveBackendTest(unittest.TestCase):
    def test_real_lookup_source_persistence_and_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "synthetic.json"
            data = fixture()
            data['records'][0]['source']['reviewed_on'] = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
            catalog.write_text(json.dumps(data), encoding='utf-8')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = {**os.environ, 'PYTHONPATH': str(BACKEND), 'PESTICIDE_CATALOG_PATH': str(catalog)}
            process = subprocess.Popen(
                [sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port)],
                cwd=directory, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            base = f'http://127.0.0.1:{port}'
            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        with urlopen(base + '/health', timeout=1) as response:
                            self.assertEqual(response.status, 200)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            self.fail('临时后端未启动')
                        time.sleep(0.1)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(executable_path=os.environ.get('ZHIMAI_CHROMIUM', '/usr/bin/chromium'), args=['--no-sandbox'])
                    try:
                        page = browser.new_page(viewport={'width':390,'height':844})
                        errors = []
                        page.on('pageerror', lambda e: errors.append(str(e)))
                        page.goto(base + '/index.html?intent=medicine')
                        page.locator('#messageInput').fill('PD20990001')
                        page.locator('#sendButton').click()
                        page.get_by_role('button', name='白粉病', exact=True).click()
                        expect(page.locator('.answer-card')).to_contain_text('快照中的作物和对象相符')
                        self.assertEqual(page.evaluate('FarmerStore.records()[0].messages.at(-1).verification.status'), 'fields_match')
                        page.get_by_text('查询来源与时间', exact=True).click()
                        expect(page.get_by_role('link', name='打开来源核实')).to_have_attribute('href', 'https://www.icama.org.cn/')
                        page.reload()
                        expect(page.locator('.answer-card')).to_contain_text('快照中的作物和对象相符')
                        # Real file failure must become unavailable, never a cached match.
                        catalog.write_text('{invalid', encoding='utf-8')
                        page.get_by_role('button', name='重新核对登记号', exact=True).click()
                        page.locator('#messageInput').fill('PD20990001')
                        page.locator('#sendButton').click()
                        page.get_by_role('button', name='白粉病', exact=True).click()
                        expect(page.locator('.answer-card').last).to_contain_text('登记资料暂不可用')
                        # Replace the explicit fixture file with the actual bundled publication data.
                        # Three real IDs must produce distinct conservative decisions in the same thread.
                        catalog.write_bytes(DEFAULT_CATALOG.read_bytes())
                        for number, target, heading, scope in [
                            ('PD20250010', '赤霉病', '公告范围相符，但现在能否用还未核实', 'match'),
                            ('PD20250008', '白粉病', '资料中的登记作物不匹配', 'mismatch'),
                            ('PD20250005', '赤霉病', '这是原药或母药登记，不能直接用于田间', 'not_applicable'),
                        ]:
                            page.get_by_role('button', name='重新核对登记号', exact=True).click()
                            page.locator('#messageInput').fill(number)
                            page.locator('#sendButton').click()
                            page.get_by_role('button', name=target, exact=True).click()
                            expect(page.locator('.answer-card').last).to_contain_text(heading)
                            saved = page.evaluate('FarmerStore.records()[0].messages.at(-1).verification')
                            self.assertEqual(saved['scope_match'], scope)
                            self.assertFalse(saved['recommendation_allowed'])
                            if number == 'PD20250010':
                                card = page.locator('.answer-card').last
                                card.get_by_text('核对标签限制', exact=True).click()
                                expect(card.locator('.label-reference')).to_contain_text('不可和碱性物质')
                                expect(card.get_by_role('link', name='打开公告版完整标签')).to_have_attribute('href', 'https://www.moa.gov.cn/govpublic/ZZYGLS/202511/P020251118315186269661.doc')
                                self.assertNotIn('150-200', card.inner_text())
                                card.get_by_text('查询来源与时间', exact=True).click()
                                expect(card.get_by_role('link', name='打开来源核实')).to_have_attribute('href', 'https://www.moa.gov.cn/govpublic/ZZYGLS/202511/t20251118_6478977.htm')
                        page.reload()
                        expect(page.locator('.answer-card').last).to_contain_text('这是原药或母药登记')
                        # Actual uploaded-document retrieval and grounded follow-up, same backend.
                        page.goto(base + '/index.html')
                        page.locator('#messageInput').fill('叶片上有白色粉状物')
                        page.locator('#sendButton').click()
                        page.get_by_role('button', name='局部一片', exact=True).click()
                        page.get_by_role('button', name='不清楚', exact=True).click()
                        expect(page.locator('.question-text').last).to_contain_text('小黑点')
                        page.get_by_role('button', name='看到了', exact=True).click()
                        expect(page.locator('.answer-card')).to_contain_text('不能确定病因')
                        page.locator('.answer-card').get_by_text('参考了哪些资料？', exact=True).click()
                        expect(page.locator('.answer-card .knowledge-evidence')).to_contain_text('P0038')
                        expect(page.locator('.answer-card .knowledge-evidence')).to_contain_text('小麦知识库最新版.docx')
                        self.assertEqual(page.evaluate('FarmerStore.records().length'), 2)
                        page.reload()
                        expect(page.locator('.answer-card')).to_contain_text('现场细节记下了')
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    unittest.main(verbosity=2)
