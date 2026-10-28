"""Browser -> real API -> orchestration/tools, with explicit model/provider test doubles.

No paid requests; production code never includes this fake-model configuration.
"""
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import uvicorn
from playwright.sync_api import sync_playwright, expect
from PIL import Image
import io

BACKEND = Path(__file__).resolve().parents[2] / 'back_end'
sys.path.insert(0, str(BACKEND))
import config
import dialogue
import weather
from main import app


class FreeChatIntegration(unittest.TestCase):
    def test_photo_context_weather_registration_and_missing_config(self):
        def decide(messages):
            latest = messages[-1]['content']
            if latest.startswith('【工具执行结果'):
                result = json.loads(latest.split('\n', 1)[1])
                if result.get('provider') == '高德天气预报':
                    self.assertEqual(result['status'], 'ok')
                    return '查到郑州明天白天多云，预报温度10~20℃。这是城市预报，不能单凭它判断可以施药。'
                self.assertEqual(result['status'], 'found')
                return '图片观察到叶片有浅色粉状区域，资料P0038有相似描述，但尚不能确诊。请补一张异常叶片的近景。'
            if 'PD20250010' in latest:
                return json.dumps({'action':'tool','tool':'check_pesticide','args':{'registration_number':'PD20250010','target':'赤霉病'}})
            if '郑州' in latest and '天气' in latest:
                return json.dumps({'action':'tool','tool':'get_weather','args':{'location':'郑州','date':'tomorrow'}})
            if '天气' in latest:
                return '这块麦田在哪个市或县？确认地点后我再查询天气。'
            if '本轮图片模型观察' in latest:
                return json.dumps({'action':'tool','tool':'search_knowledge','args':{'query':'叶片白色粉状物'}})
            return '你可以直接补充最担心的变化，我会接着前面的照片观察看。'

        observed_images = []
        def observe(content, _question):
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                self.assertLessEqual(max(image.size), 1600)
                self.assertNotIn('exif', image.info)
            observed_images.append(content)
            return '测试上游观察：小麦叶片局部浅色粉状区域；仅为观察，不能确诊。'

        now = datetime.now(ZoneInfo('Asia/Shanghai'))
        tomorrow = (now + timedelta(days=1)).date().isoformat()
        payload = {'status':'1','forecasts':[{'adcode':'410100','city':'郑州市','reporttime':now.strftime('%Y-%m-%d %H:%M:%S'),'casts':[{
            'date':tomorrow,'dayweather':'多云','nightweather':'阴','nighttemp':'10','daytemp':'20',
            'daywind':'东','nightwind':'东','daypower':'1-3','nightpower':'1-3',
        }]}]}
        class WeatherResponse:
            status_code = 200
            def json(self): return payload

        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error', lifespan='off'))
        with patch.object(config, 'SPARK_API_PASSWORD', 'test-only-key'), patch.object(config, 'WEATHER_API_KEY', 'test-only-weather'), patch.object(dialogue.llm, 'chat', side_effect=decide), patch.object(dialogue, 'understand_image', side_effect=observe), patch.object(weather.requests, 'get', return_value=WeatherResponse()) as weather_request:
            thread = threading.Thread(target=server.run, daemon=True); thread.start()
            try:
                deadline = time.monotonic() + 10
                while not server.started:
                    if time.monotonic() > deadline: self.fail('临时服务未启动')
                    time.sleep(.05)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(executable_path=os.environ.get('ZHIMAI_CHROMIUM','/usr/bin/chromium'), args=['--no-sandbox'])
                    try:
                        page = browser.new_page(viewport={'width':390,'height':844})
                        errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{port}/index.html')
                        page.locator('#photoInput').set_input_files(str(BACKEND.parent/'front_end/assets/wheat-green.jpg'))
                        expect(page.locator('.attachment')).to_be_visible()
                        page.locator('#sendButton').click()
                        expect(page.locator('.agent-answer').last).to_contain_text('图片观察到')
                        self.assertEqual(len(observed_images), 1)
                        expect(page.locator('.choices')).to_have_count(0)
                        page.get_by_text('本次查看与查询依据', exact=True).last.click()
                        expect(page.locator('.agent-evidence').last).to_contain_text('知识检索')
                        page.reload()
                        expect(page.locator('.agent-answer')).to_contain_text('尚不能确诊')
                        page.locator('#messageInput').fill('明天天气怎样？'); page.locator('#sendButton').click()
                        expect(page.locator('.agent-answer').last).to_contain_text('哪个市或县')
                        weather_request.assert_not_called()
                        page.locator('#messageInput').fill('我在郑州，查明天天气'); page.locator('#sendButton').click()
                        expect(page.locator('.agent-answer').last).to_contain_text('多云')
                        self.assertEqual(weather_request.call_count, 1)
                        self.assertEqual(len(observed_images), 1, '旧照片不能每轮重传')
                        last = page.evaluate('FarmerStore.records()[0].messages.at(-1)')
                        self.assertEqual(last['toolResults'][0]['result']['forecast_date'], tomorrow)
                        page.locator('#messageInput').fill('PD20250010能用于小麦赤霉病吗？'); page.locator('#sendButton').click()
                        expect(page.locator('.agent-answer').last).to_contain_text('暂不能据此施药')
                        count = page.evaluate('FarmerStore.records()[0].messages.length')
                        config.SPARK_API_PASSWORD = ''
                        page.locator('#messageInput').fill('接着看看'); page.locator('#sendButton').click()
                        expect(page.locator('#sendError')).to_contain_text('尚未配置')
                        expect(page.locator('#messageInput')).to_have_value('接着看看')
                        self.assertEqual(page.evaluate('FarmerStore.records()[0].messages.length'), count)
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.should_exit = True; thread.join(timeout=5)
                self.assertFalse(thread.is_alive())


if __name__ == '__main__': unittest.main(verbosity=2)
