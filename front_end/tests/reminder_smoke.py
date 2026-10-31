"""Real browser/HTTP/scheduler tests; no model or weather charges."""
import json, os, socket, sys, tempfile, threading, time, unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import uvicorn
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'back_end'))
import personal, config, dialogue
from main import app

class ReminderBrowserTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path_patch=patch.object(personal,'PATH',Path(self.tmp.name)/'personal.db');self.path_patch.start()
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  self.base=f'http://127.0.0.1:{port}';self.server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',lifespan='off'))
  self.thread=threading.Thread(target=self.server.run,daemon=True);self.thread.start()
  deadline=time.monotonic()+10
  while not self.server.started:
   if time.monotonic()>deadline:raise RuntimeError('server startup failed')
   time.sleep(.02)
  self.pw=sync_playwright().start();self.browser=self.pw.chromium.launch(executable_path=os.environ.get('ZHIMAI_CHROMIUM','/usr/bin/chromium'),args=['--no-sandbox'])
  self.context=self.browser.new_context(timezone_id='UTC',viewport={'width':390,'height':844})
  self.page=self.context.new_page();self.errors=[];self.page.on('pageerror',lambda e:self.errors.append(str(e)))
 def tearDown(self):
  self.browser.close();self.pw.stop();self.server.should_exit=True;self.thread.join(5);self.path_patch.stop();self.tmp.cleanup();self.assertEqual(self.errors,[])
 def test_manual_once_reminder_fires_on_chat_without_desktop_permission(self):
  self.page.goto(self.base+'/personal.html?tab=tasks')
  self.page.get_by_role('button',name='新增提醒',exact=True).click()
  expect(self.page.locator('[data-weather-field]')).to_be_hidden()
  self.page.locator('[name=name]').fill('给麦苗补拍近景')
  target=(personal.now()+timedelta(minutes=2)).replace(second=0,microsecond=0)
  self.page.locator('[name=run_at]').fill(target.strftime('%Y-%m-%dT%H:%M'))
  self.page.locator('[name=notes]').fill('拍清楚叶背')
  self.page.get_by_role('button',name='确认设置提醒',exact=True).click()
  expect(self.page.locator('article')).to_contain_text('仅一次')
  # UTC browser still displays the Beijing clock selected by the farmer.
  expect(self.page.locator('.task-clock')).to_contain_text(target.strftime('%H:%M'))
  self.page.goto(self.base+'/index.html')
  self.assertNotEqual(self.page.evaluate('Notification.permission'),'granted')
  with patch.object(personal,'now',return_value=target+timedelta(seconds=1)),patch.object(personal.weather,'get_weather') as weather:
   stop=personal.start()
   try:
    expect(self.page.locator('#reminderAlert')).to_be_visible(timeout=12000)
    expect(self.page.locator('#reminderAlert')).to_contain_text('拍清楚叶背')
    self.page.get_by_role('button',name='知道了',exact=True).click()
    expect(self.page.locator('#reminderAlert')).to_have_count(0)
    self.page.reload();expect(self.page.locator('#messageInput')).to_be_visible()
    self.assertTrue(self.context.request.get(self.base+'/api/personal/notifications').json()[0]['read'])
    weather.assert_not_called()
   finally:stop.set()
 def test_agent_confirmation_saves_to_reminders_page(self):
  target=personal.now()+timedelta(minutes=3)
  output=json.dumps({'action':'tool','tool':'prepare_reminder','args':{'name':'复查麦苗','concern':'补拍新叶','recurrence':'once','run_at':target.isoformat()}})
  with patch.object(config,'SPARK_API_PASSWORD','test'),patch.object(dialogue.llm,'chat_stream',return_value=iter([output])):
   self.page.goto(self.base+'/index.html');self.page.locator('#messageInput').fill('三分钟后提醒我复查麦苗');self.page.locator('#sendButton').click()
   expect(self.page.get_by_role('button',name='确认设置',exact=True)).to_be_visible()
   self.assertEqual(self.context.request.get(self.base+'/api/personal/tasks').json(),[])
   self.page.get_by_role('button',name='确认设置',exact=True).click()
   expect(self.page.locator('.reminder-draft')).to_contain_text('已设置，已保存')
   self.assertEqual(len(self.context.request.get(self.base+'/api/personal/tasks').json()),1)
   self.page.get_by_role('link',name='去提醒页查看',exact=True).click()
   expect(self.page.locator('article')).to_contain_text('复查麦苗')
 def test_unread_notification_survives_page_closed_and_read_ack(self):
  self.page.goto(self.base+'/index.html');self.page.locator('#messageInput').wait_for()
  target=personal.now()+timedelta(minutes=2)
  response=self.context.request.put(self.base+'/api/personal/tasks/offline',headers={'X-Zhimai-Personal':'1'},data={'name':'回来复查','task_type':'reminder','recurrence':'once','run_at':target.isoformat(),'notes':'拍新叶'})
  self.assertTrue(response.ok);self.page.close()
  with patch.object(personal,'now',return_value=target+timedelta(seconds=1)):personal.tick()
  self.page=self.context.new_page();self.page.on('pageerror',lambda e:self.errors.append(str(e)))
  self.page.goto(self.base+'/history.html');expect(self.page.locator('#reminderAlert')).to_be_visible(timeout=10000)
  expect(self.page.locator('#reminderAlert')).to_contain_text('回来复查')
  self.page.get_by_role('button',name='知道了',exact=True).click();expect(self.page.locator('#reminderAlert')).to_have_count(0)

if __name__=='__main__':unittest.main(verbosity=2)
