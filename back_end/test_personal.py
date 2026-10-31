import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import personal
from main import app

class PersonalTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.patch=patch.object(personal,'PATH',Path(self.temp.name)/'personal.db');self.patch.start()
  self.a=TestClient(app);self.b=TestClient(app)
  self.a.get('/api/personal/session');self.b.get('/api/personal/session')
  self.headers={'X-Zhimai-Personal':'1'}
 def tearDown(self):self.patch.stop();self.temp.cleanup()
 def test_inventory_isolation_update_delete_and_write_header(self):
  path='/api/personal/medicines/a'
  self.assertEqual(self.a.put(path,json={'name':'测试药'}).status_code,403)
  self.assertEqual(self.a.put(path,json={'name':'测试药'},headers=self.headers).status_code,200)
  self.assertEqual(len(self.a.get('/api/personal/medicines').json()),1)
  self.assertEqual(self.b.get('/api/personal/medicines').json(),[])
  self.b.delete(path,headers=self.headers)
  self.assertEqual(len(self.a.get('/api/personal/medicines').json()),1)
  self.a.put(path,json={'name':'修改后'},headers=self.headers)
  self.assertEqual(self.a.get('/api/personal/medicines').json()[0]['name'],'修改后')
  self.a.delete(path,headers=self.headers)
  self.assertEqual(self.a.get('/api/personal/medicines').json(),[])
 def test_daily_check_failure_is_saved_once_and_pause_stops(self):
  body={'name':'麦苗检查','location':'郑州','time':'08:00','notes':'看看之前发黄的麦苗'}
  self.assertEqual(self.a.put('/api/personal/tasks/t',json=body,headers=self.headers).status_code,200)
  with personal.db() as c:c.execute("UPDATE entries SET next='2020-01-01T08:00:00+08:00' WHERE kind='tasks'")
  with patch.object(personal.weather,'get_weather',return_value=json.dumps({'status':'unavailable'})) as weather:
   personal.tick();personal.tick();weather.assert_called_once_with('郑州','today')
  rows=self.a.get('/api/personal/notifications').json()
  self.assertEqual(len(rows),1);self.assertIn('天气查询失败',rows[0]['message']);self.assertIn(body['notes'],rows[0]['message'])
  self.assertEqual(self.b.get('/api/personal/notifications').json(),[])
  self.a.put('/api/personal/tasks/t',json={**body,'enabled':False},headers=self.headers)
  with patch.object(personal.weather,'get_weather') as weather:personal.tick();weather.assert_not_called()
 def test_agent_inventory_scope_and_task_draft(self):
  import config, dialogue
  from runtime import STREAM_PROTOCOL
  self.a.put('/api/personal/medicines/a',json={'name':'仅属于A的药'},headers=self.headers)
  calls=[]
  def model(messages,**kwargs):
   calls.append(list(messages))
   if len(calls)%2: return iter([json.dumps({'action':'tool','tool':'list_my_medicines','args':{}})])
   return iter(['已读取个人资料，仍需核对登记。'])
  with patch.object(config,'SPARK_API_PASSWORD','test'),patch.object(dialogue.llm,'chat_stream',side_effect=model):
   self.a.post('/api/agent/chat',data={'message':'看看我手里的药'},headers={'X-Zhimai-Stream-Protocol':STREAM_PROTOCOL})
   self.b.post('/api/agent/chat',data={'message':'看看我手里的药'},headers={'X-Zhimai-Stream-Protocol':STREAM_PROTOCOL})
  self.assertIn('仅属于A的药',calls[1][-1]['content'])
  self.assertNotIn('仅属于A的药',calls[3][-1]['content'])
  from diagnostics import Trace
  trace=Trace();trace.owner=self.a.cookies.get('zhimai_owner')
  draft=dialogue._tool_result('prepare_weather_check',{'location':'郑州','time':'08:00','concern':'看看发黄麦苗'},set(),trace)
  self.assertEqual(draft['status'],'draft')
  self.assertEqual(self.a.get('/api/personal/tasks').json(),[])

 def test_once_reminder_without_weather_and_read_ack_isolation(self):
  from datetime import timedelta
  target=personal.now()+timedelta(minutes=2)
  body={'name':'补拍黄叶','task_type':'reminder','recurrence':'once','run_at':target.isoformat(),'notes':'补拍叶背'}
  result=self.a.put('/api/personal/tasks/once',json=body,headers=self.headers)
  self.assertEqual(result.status_code,200)
  with patch.object(personal,'now',return_value=target+timedelta(seconds=1)),patch.object(personal.weather,'get_weather') as weather:
   personal.tick();personal.tick();weather.assert_not_called()
  rows=self.a.get('/api/personal/notifications').json()
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['message'],'补拍叶背');self.assertFalse(rows[0]['read'])
  task=self.a.get('/api/personal/tasks').json()[0]
  self.assertFalse(task['enabled']);self.assertTrue(task['_completed_at']);self.assertEqual(task['next'],'')
  path='/api/personal/notifications/'+rows[0]['id']+'/read'
  self.assertEqual(self.b.post(path,headers=self.headers).status_code,404)
  self.assertEqual(self.a.post(path,headers=self.headers).status_code,200)
  self.assertTrue(self.a.get('/api/personal/notifications').json()[0]['read'])

 def test_past_or_ambiguous_once_dates_rejected(self):
  for value in ['2020-01-01T15:00','tomorrow','2099-01-01']:
   body={'name':'检查','task_type':'reminder','recurrence':'once','run_at':value}
   self.assertEqual(self.a.put('/api/personal/tasks/once',json=body,headers=self.headers).status_code,400)

 def test_agent_ordinary_reminder_requires_confirmation_and_is_idempotent(self):
  import config,dialogue
  from datetime import timedelta
  from runtime import STREAM_PROTOCOL
  args={'name':'检查黄叶','recurrence':'once','run_at':(personal.now()+timedelta(minutes=3)).isoformat(),'concern':'补拍叶背'}
  response_text=json.dumps({'action':'tool','tool':'prepare_reminder','args':args})
  with patch.object(config,'SPARK_API_PASSWORD','test'),patch.object(dialogue.llm,'chat_stream',return_value=iter([response_text])):
   response=self.a.post('/api/agent/chat',data={'message':'三分钟后提醒我检查黄叶'},headers={'X-Zhimai-Stream-Protocol':STREAM_PROTOCOL})
  events=[json.loads(line[5:]) for line in response.text.splitlines() if line.startswith('data:')]
  draft=next(e['result'] for e in events if e['type']=='tool_result')
  self.assertEqual(draft['task_type'],'reminder');self.assertEqual(draft['status'],'draft')
  self.assertEqual(self.a.get('/api/personal/tasks').json(),[])
  body={k:draft[k] for k in personal.Entry.model_fields}
  for _ in range(2):self.assertEqual(self.a.put('/api/personal/tasks/confirmed',json=body,headers=self.headers).status_code,200)
  self.assertEqual(len(self.a.get('/api/personal/tasks').json()),1)

 def test_scheduler_status_and_pending_job_recovery(self):
  from datetime import timedelta
  self.assertFalse(self.a.get('/api/personal/status').json()['scheduler_running'])
  body={'name':'检查','task_type':'reminder','recurrence':'daily','time':'08:00'}
  self.a.put('/api/personal/tasks/recover',json=body,headers=self.headers)
  with personal.db() as c:
   task=c.execute("SELECT * FROM entries WHERE id='recover'").fetchone()
   c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',(task['owner'],'recovered-job',task['id'],task['body'],'2020-01-01T08:00:00+08:00',(personal.now()-timedelta(minutes=1)).isoformat()))
  personal.tick()
  self.assertTrue(self.a.get('/api/personal/status').json()['scheduler_running'])
  self.assertEqual(self.a.get('/api/personal/status').json()['pending_jobs'],0)
  self.assertEqual(len(self.a.get('/api/personal/notifications').json()),1)

 def test_invalid_time_and_location_rejected(self):
  for data in [{'name':'检查','location':'河南','time':'08:00'},{'name':'检查','location':'郑州','time':'25:00'}]:
   self.assertIn(self.a.put('/api/personal/tasks/t',json=data,headers=self.headers).status_code,[400,422])

if __name__=='__main__':unittest.main()
