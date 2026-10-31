"""Exercise personal pages with the real HTTP API and an isolated temporary DB."""
import os,sys,socket,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
import uvicorn
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'back_end'))
import personal
from main import app

class PersonalBrowserTests(unittest.TestCase):
 def test_inventory_task_creation_edit_and_delete(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(personal,'PATH',Path(directory)/'personal.db'):
   with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',lifespan='off'))
   thread=threading.Thread(target=server.run,daemon=True);thread.start()
   try:
    deadline=time.monotonic()+10
    while not server.started:
     if time.monotonic()>deadline:self.fail('server did not start')
     time.sleep(.02)
    with sync_playwright() as p:
     browser=p.chromium.launch(executable_path=os.environ.get('ZHIMAI_CHROMIUM','/usr/bin/chromium'),args=['--no-sandbox'])
     try:
      page=browser.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
      page.goto(f'http://127.0.0.1:{port}/personal.html')
      page.get_by_role('button',name='新增农药',exact=True).click()
      page.locator('[name=name]').fill('测试农药')
      page.locator('[name=number]').fill('PD20250010')
      page.get_by_role('button',name='确认保存',exact=True).click()
      expect(page.locator('article')).to_contain_text('测试农药')
      page.reload();expect(page.locator('article')).to_contain_text('PD20250010')
      page.get_by_role('button',name='定时天气检查',exact=True).click()
      page.get_by_role('button',name='新增每日检查',exact=True).click()
      page.locator('[name=location]').fill('郑州');page.locator('[name=time]').fill('08:00');page.locator('[name=notes]').fill('看看之前发黄的麦苗')
      page.get_by_role('button',name='确认保存并设置每日检查',exact=True).click()
      expect(page.locator('article')).to_contain_text('郑州 · 每天 08:00 · 已启用')
      page.get_by_role('button',name='编辑',exact=True).click();page.locator('[name=enabled]').select_option('false')
      page.get_by_role('button',name='确认保存并设置每日检查',exact=True).click();expect(page.locator('article')).to_contain_text('已暂停')
      page.on('dialog',lambda d:d.accept());page.get_by_role('button',name='删除',exact=True).click();expect(page.locator('article')).to_have_count(0)
      self.assertEqual(errors,[]);self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
     finally:browser.close()
   finally:server.should_exit=True;thread.join(timeout=5)

if __name__=='__main__':unittest.main()
