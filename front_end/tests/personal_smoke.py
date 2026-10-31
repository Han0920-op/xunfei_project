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
      page.get_by_role('searchbox',name='搜索农药').fill('找不到的药')
      expect(page.locator('article')).to_have_count(0)
      expect(page.get_by_role('heading',name='没有找到这瓶药',exact=True)).to_be_visible()
      page.get_by_role('searchbox',name='搜索农药').fill('')
      expect(page.locator('article')).to_have_count(1)
      page.get_by_role('button',name='打开导航',exact=True).click()
      page.get_by_role('link',name='提醒',exact=True).click()
      page.get_by_role('button',name='新增每日检查',exact=True).click()
      page.locator('[name=location]').fill('郑州');page.locator('[name=time]').fill('08:00');page.locator('[name=notes]').fill('看看之前发黄的麦苗')
      page.get_by_role('button',name='确认保存并设置每日检查',exact=True).click()
      expect(page.locator('article')).to_contain_text('郑州 · 每天 08:00 · 已启用')
      page.get_by_role('button',name='编辑',exact=True).click();page.locator('[name=enabled]').select_option('false')
      page.get_by_role('button',name='确认保存并设置每日检查',exact=True).click();expect(page.locator('article')).to_contain_text('已暂停')
      page.get_by_role('button',name='删除',exact=True).click();page.get_by_role('button',name='确认删除',exact=True).click();expect(page.locator('article')).to_have_count(0)
      self.assertEqual(errors,[]);self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
      page.set_viewport_size({'width':1440,'height':1000})
      expect(page.get_by_role('navigation',name='主导航')).to_be_visible()
      self.assertEqual(page.locator('nav a').all_text_contents(),['问智麦','我的记录','我的农药库','提醒'])
      self.assertEqual(page.locator('nav a[aria-current=page]').inner_text(),'提醒')
      self.assertLessEqual(page.locator('nav').bounding_box()['x'],232)
      page.get_by_role('link',name='我的记录',exact=True).click()
      expect(page.locator('nav a[aria-current=page]')).to_have_text('我的记录')
      page.set_viewport_size({'width':320,'height':844})
      page.get_by_role('button',name='打开导航',exact=True).click()
      expect(page.get_by_role('link',name='我的农药库',exact=True)).to_be_visible()
      page.keyboard.press('Escape')
      expect(page.locator('#appSidebar')).to_be_hidden()
      self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),320)
     finally:browser.close()
   finally:server.should_exit=True;thread.join(timeout=5)

if __name__=='__main__':unittest.main()
