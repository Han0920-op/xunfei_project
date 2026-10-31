"""Long-term memory through real HTTP and browser UI, with a fake model only."""
import json,os,socket,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
import uvicorn
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'back_end'))
import personal,config,dialogue
from main import app

class MemoryBrowserTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patches=[patch.object(personal,'PATH',Path(self.tmp.name)/'db.sqlite'),patch.object(config,'SPARK_API_PASSWORD','test')]
  for p in self.patches:p.start()
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  self.base=f'http://127.0.0.1:{port}';self.server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',lifespan='off'))
  self.thread=threading.Thread(target=self.server.run,daemon=True);self.thread.start()
  deadline=time.monotonic()+10
  while not self.server.started:
   if time.monotonic()>deadline:raise RuntimeError('server startup failed')
   time.sleep(.02)
  self.pw=sync_playwright().start();self.browser=self.pw.chromium.launch(executable_path=os.environ.get('ZHIMAI_CHROMIUM','/usr/bin/chromium'),args=['--no-sandbox'])
  self.context=self.browser.new_context(viewport={'width':390,'height':844});self.page=self.context.new_page();self.errors=[];self.page.on('pageerror',lambda e:self.errors.append(str(e)))
 def tearDown(self):
  self.browser.close();self.pw.stop();self.server.should_exit=True;self.thread.join(5)
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup();self.assertEqual(self.errors,[])
 def send(self,text):self.page.locator('#messageInput').fill(text);self.page.locator('#sendButton').click()
 def test_confirm_profile_then_new_conversation_uses_it_and_can_delete(self):
  captured=[]
  def model(messages,**kwargs):
   captured.append(messages)
   if '请记住' in messages[-1]['content']:
    return iter([json.dumps({'action':'tool','tool':'prepare_memory_fact','args':{'scope':'user','label':'常用地区','content':'河南濮阳'}})])
   return iter(['我会参考你确认的常用地区，并核实本次具体情况。'])
  with patch.object(dialogue.llm,'chat_stream',side_effect=model):
   self.page.goto(self.base+'/index.html');self.send('请记住我的常用地区是河南濮阳')
   expect(self.page.get_by_role('button',name='确认记住',exact=True)).to_be_visible()
   self.assertEqual(self.context.request.get(self.base+'/api/memory/profile').json()['facts'],[])
   self.page.get_by_role('button',name='确认记住',exact=True).click();expect(self.page.get_by_role('button',name='已记住',exact=True)).to_be_visible()
   self.page.goto(self.base+'/index.html');self.send('你记得我的资料吗')
   expect(self.page.locator('.agent-answer')).to_contain_text('常用地区')
   self.assertIn('河南濮阳',json.dumps(captured[-1],ensure_ascii=False))
   self.assertEqual(len(self.context.request.get(self.base+'/api/memory/cases').json()),2)
  self.page.goto(self.base+'/memory.html');expect(self.page.get_by_role('heading',name='常用地区',exact=True)).to_be_visible()
  self.page.get_by_role('button',name='更正',exact=True).click();self.page.locator('[name=content]').fill('河南郑州');self.page.get_by_role('button',name='确认记住',exact=True).click()
  expect(self.page.locator('.personal-card').filter(has=self.page.get_by_role('heading',name='常用地区',exact=True))).to_contain_text('河南郑州')
  self.page.get_by_role('button',name='删除记忆',exact=True).click();self.page.get_by_role('button',name='确认删除',exact=True).click()
  expect(self.page.get_by_role('heading',name='常用地区',exact=True)).to_have_count(0)
 def test_old_case_selection_restores_history_and_recovery_works_on_new_browser(self):
  def model(messages,**kwargs):
   if '上次' in messages[-1]['content']:return iter([json.dumps({'action':'tool','tool':'search_user_cases','args':{'query':'黄叶'}})])
   return iter(['先观察新叶及叶背，目前证据不足。'])
  with patch.object(dialogue.llm,'chat_stream',side_effect=model):
   self.page.goto(self.base+'/index.html');self.send('麦苗黄叶，昨天才发现')
   expect(self.page.locator('.agent-answer')).to_be_visible();first_id=self.page.evaluate('FarmerStore.records()[0].id')
   self.page.goto(self.base+'/index.html');self.send('上次黄叶那件事')
   expect(self.page.get_by_role('link',name='是这次，继续这个案例',exact=True)).to_be_visible()
   self.page.get_by_role('link',name='是这次，继续这个案例',exact=True).click()
   expect(self.page.locator('.thread-heading h1')).to_have_text('麦苗黄叶，昨天才发现')
   self.assertIn(first_id,self.page.url)
  self.page.goto(self.base+'/memory.html');self.page.get_by_role('button',name='生成恢复码',exact=True).click();self.page.locator('#dialog').get_by_role('button',name='生成恢复码',exact=True).click()
  code=self.page.get_by_role('textbox',name='恢复码',exact=True).input_value()
  other=self.browser.new_context();p=other.new_page();p.on('pageerror',lambda e:self.errors.append(str(e)))
  p.goto(self.base+'/memory.html');p.get_by_role('button',name='用恢复码找回资料',exact=True).click();p.locator('[name=code]').fill(code);p.get_by_role('button',name='确认恢复',exact=True).click()
  expect(p.get_by_role('heading',name='麦苗黄叶，昨天才发现',exact=True)).to_be_visible()
  p.locator('.personal-card').filter(has=p.get_by_role('heading',name='麦苗黄叶，昨天才发现',exact=True)).get_by_role('link',name='确认这次，继续咨询',exact=True).click()
  expect(p.locator('.thread-heading h1')).to_have_text('麦苗黄叶，昨天才发现')
  other.close()
 def test_legacy_import_requires_click_and_preserves_local_record(self):
  self.page.goto(self.base+'/index.html')
  self.page.evaluate("""()=>{const r=FarmerAssistant.create();r.id='local-old';r.title='本机旧案例';r.messages=[{id:'old-u',role:'user',text:'叶片发黄'},{id:'old-a',role:'assistant',type:'agent',text:'旧模型判断，未核实'}];FarmerStore.save(r)}""")
  self.page.goto(self.base+'/memory.html');self.assertEqual(self.context.request.get(self.base+'/api/memory/cases').json(),[])
  self.page.get_by_role('button',name='同步文字',exact=True).click();self.page.get_by_role('button',name='确认同步',exact=True).click()
  expect(self.page.get_by_role('link',name='查看事实与时间线',exact=True)).to_be_visible()
  self.assertEqual(self.page.evaluate('FarmerStore.get("local-old").messages.length'),2)
  self.page.get_by_role('button',name='删除案例',exact=True).click();self.page.get_by_role('button',name='确认删除',exact=True).click()
  expect(self.page.get_by_role('link',name='查看事实与时间线',exact=True)).to_have_count(0)

if __name__=='__main__':unittest.main(verbosity=2)
