"""Persistence, ownership, provenance and explicit memory confirmation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import personal, memory, dialogue, config
from main import app
from runtime import STREAM_PROTOCOL
from diagnostics import Trace

class MemoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=patch.object(personal,'PATH',Path(self.tmp.name)/'memory.db');self.path.start()
  self.a=TestClient(app);self.b=TestClient(app)
  for c in [self.a,self.b]:c.get('/api/personal/session')
  self.headers={'X-Zhimai-Personal':'1'}
 def tearDown(self):self.path.stop();self.tmp.cleanup()
 def chat(self,client,case_id='case-a',turn_id='turn-a',message='幼苗叶片发黄',answer='暂不能确诊，请补拍叶背。'):
  with patch.object(config,'SPARK_API_PASSWORD','test'),patch.object(dialogue.llm,'chat_stream',return_value=iter([answer])):
   return client.post('/api/agent/chat',headers={'X-Zhimai-Stream-Protocol':STREAM_PROTOCOL},data={'case_id':case_id,'turn_id':turn_id,'message':message})
 def test_successful_turn_persists_with_separate_sources(self):
  response=self.chat(self.a)
  self.assertIn('memory_saved',response.text)
  case=self.a.get('/api/memory/cases/case-a').json()
  self.assertEqual(case['turns'][0]['user']['source_type'],'user_reported')
  self.assertEqual(case['turns'][0]['assistant']['source_type'],'model_inference')
  self.assertEqual(case['facts'],[]);self.assertFalse(case['photos_stored'])
  self.assertEqual(len(self.a.get('/api/memory/cases').json()),1)
  self.chat(self.a)
  self.assertEqual(len(self.a.get('/api/memory/cases/case-a').json()['turns']),1)
 def test_failed_answer_does_not_create_case(self):
  with patch.object(config,'SPARK_API_PASSWORD','test'),patch.object(dialogue.llm,'chat_stream',side_effect=RuntimeError('private')):
   response=self.a.post('/api/agent/chat',headers={'X-Zhimai-Stream-Protocol':STREAM_PROTOCOL},data={'message':'test','case_id':'failed','turn_id':'failed-turn'})
  self.assertIn('"type": "error"',response.text);self.assertEqual(self.a.get('/api/memory/cases').json(),[])
 def test_foreign_case_and_fact_access_is_blocked(self):
  self.chat(self.a)
  self.assertEqual(self.b.get('/api/memory/cases/case-a').status_code,404)
  self.assertEqual(self.chat(self.b).status_code,404)
  self.assertEqual(self.b.delete('/api/memory/cases/case-a',headers=self.headers).status_code,404)
  self.assertEqual(self.b.put('/api/memory/facts/f',json={'label':'观察','content':'黄叶','case_id':'case-a'},headers=self.headers).status_code,404)
  self.assertEqual(self.b.get('/api/memory/cases').json(),[])
 def test_profile_fact_recalled_across_new_cases_and_correction_deletion(self):
  data={'label':'常用地区','content':'郑州'}
  self.a.put('/api/memory/facts/location',json=data,headers=self.headers)
  seen=[]
  def model(messages,**kwargs):seen.append(json.dumps(messages[1:],ensure_ascii=False));return iter(['收到。'])
  with patch.object(config,'SPARK_API_PASSWORD','test'),patch.object(dialogue.llm,'chat_stream',side_effect=model):
   for client,case,turn in [(self.a,'case-a','t1'),(self.a,'case-b','t2'),(self.b,'case-c','t3')]:
    client.post('/api/agent/chat',headers={'X-Zhimai-Stream-Protocol':STREAM_PROTOCOL},data={'message':'你记得我的资料吗','case_id':case,'turn_id':turn})
  self.assertIn('郑州',seen[0]);self.assertIn('郑州',seen[1]);self.assertNotIn('郑州',seen[2])
  self.a.put('/api/memory/facts/location',json={**data,'content':'濮阳'},headers=self.headers)
  self.assertEqual(self.a.get('/api/memory/profile').json()['facts'][0]['content'],'濮阳')
  self.a.delete('/api/memory/facts/location',headers=self.headers)
  self.assertEqual(self.a.get('/api/memory/profile').json()['facts'],[])
 def test_search_does_not_use_model_inference_and_history_needs_confirmation(self):
  self.chat(self.a,answer='模型猜测的秘密病名')
  who=self.a.cookies.get('zhimai_owner');trace=Trace();trace.owner=who;trace.case_id='new-case'
  result=dialogue._tool_result('search_user_cases',{'query':'叶片发黄'},set(),trace)
  self.assertEqual(result['status'],'needs_confirmation');self.assertTrue(result['cases'])
  self.assertNotIn('秘密病名',json.dumps(result,ensure_ascii=False))
  self.assertEqual(memory.cases(who,'秘密病名'),[])
  result=dialogue._tool_result('get_case_history',{'case_id':'case-a'},set(),trace)
  self.assertEqual(result['status'],'needs_confirmation');self.assertNotIn('reports',result)
  trace.case_id='case-a'
  self.assertEqual(dialogue._tool_result('get_case_history',{'case_id':'case-a'},set(),trace)['status'],'ok')
 def test_fact_draft_does_not_write_until_confirmed(self):
  trace=Trace();trace.owner=self.a.cookies.get('zhimai_owner');trace.case_id='case-a'
  result=dialogue._tool_result('prepare_memory_fact',{'scope':'user','label':'常用地区','content':'郑州'},set(),trace)
  self.assertEqual(result['status'],'draft');self.assertEqual(self.a.get('/api/memory/profile').json()['facts'],[])
  self.a.put('/api/memory/facts/f',json={'label':result['label'],'content':result['content']},headers=self.headers)
  self.assertEqual(self.a.get('/api/memory/profile').json()['facts'][0]['source_type'],'user_confirmed')
 def test_case_delete_removes_history_facts_and_blocks_late_save(self):
  self.chat(self.a)
  self.a.put('/api/memory/facts/f',json={'label':'观察','content':'叶背发黄','case_id':'case-a'},headers=self.headers)
  self.a.delete('/api/memory/cases/case-a',headers=self.headers)
  self.assertEqual(self.a.get('/api/memory/cases/case-a').status_code,404)
  self.assertEqual(self.chat(self.a,turn_id='late').status_code,410)
  self.assertEqual(self.chat(self.b,turn_id='other-late').status_code,404)
  with memory.db() as c:
   self.assertEqual(c.execute('SELECT count(*) FROM memory_turns').fetchone()[0],0)
   self.assertEqual(c.execute('SELECT count(*) FROM memory_facts').fetchone()[0],0)
 def test_recovery_restores_same_owner_and_reset_revokes_old_code(self):
  self.chat(self.a)
  code=self.a.post('/api/memory/recovery',headers=self.headers).json()['code']
  self.assertEqual(self.b.get('/api/memory/cases').json(),[])
  self.assertEqual(self.b.post('/api/memory/restore',json={'code':code},headers=self.headers).status_code,200)
  self.assertEqual(self.b.get('/api/memory/cases').json()[0]['id'],'case-a')
  self.a.post('/api/memory/recovery',headers=self.headers)
  self.assertEqual(self.b.post('/api/memory/restore',json={'code':code},headers=self.headers).status_code,400)
  with memory.db() as c:
   self.assertNotEqual(c.execute('SELECT digest FROM memory_recovery').fetchone()[0],code)
 def test_legacy_import_is_opt_in_and_never_confirms_model_claims(self):
  body={'id':'old','title':'此前黄叶','messages':[{'id':'u','role':'user','text':'叶尖发黄'},{'id':'a','role':'assistant','text':'模型曾猜测缺氮'}]}
  self.assertEqual(self.a.get('/api/memory/cases').json(),[])
  self.assertEqual(self.a.post('/api/memory/import',json={**body,'demo':True},headers=self.headers).status_code,400)
  self.assertEqual(self.a.post('/api/memory/import',json=body,headers=self.headers).status_code,200)
  case=self.a.get('/api/memory/cases/old').json()
  self.assertEqual(case['facts'],[]);self.assertEqual(case['turns'][0]['assistant']['source_type'],'imported_unverified_inference')
  self.assertEqual(self.a.post('/api/memory/import',json=body,headers=self.headers).status_code,409)
 def test_image_observation_is_saved_but_not_original_image(self):
  from test_dialogue import png,checked
  content=png()
  with patch.object(config,'SPARK_API_PASSWORD','test'),patch.object(dialogue,'understand_image',return_value='幼苗叶尖发黄，不能确诊'),patch.object(dialogue.llm,'chat_stream',return_value=iter([checked('请补拍叶背。')])):
   response=self.a.post('/api/agent/chat',headers={'X-Zhimai-Stream-Protocol':STREAM_PROTOCOL},data={'message':'帮我看叶片','case_id':'photo-case','turn_id':'photo-turn','photo_id':'local-photo'},files={'image':('photo.png',content,'image/png')})
  self.assertIn('memory_saved',response.text)
  case=self.a.get('/api/memory/cases/photo-case').json()
  self.assertFalse(case['photos_stored']);self.assertTrue(case['turns'][0]['user']['had_image'])
  self.assertEqual(case['turns'][0]['user']['photoId'],'local-photo')
  self.assertEqual(case['turns'][0]['assistant']['vision'][0]['content'],'幼苗叶尖发黄，不能确诊')
  import base64
  self.assertNotIn(base64.b64encode(content).decode(),json.dumps(case))

 def test_search_body_is_owned_and_existing_fact_draft_updates_same_slot(self):
  self.chat(self.a)
  result=self.a.post('/api/memory/search',json={'query':'黄叶'},headers=self.headers)
  self.assertEqual(result.status_code,200)
  self.assertEqual(self.b.post('/api/memory/search',json={'query':'黄叶'},headers=self.headers).json(),[])
  self.a.put('/api/memory/facts/location',json={'label':'常用地区','content':'郑州'},headers=self.headers)
  trace=Trace();trace.owner=self.a.cookies.get('zhimai_owner');trace.case_id='case-a'
  draft=dialogue._tool_result('prepare_memory_fact',{'scope':'user','label':'常用地区','content':'濮阳'},set(),trace)
  self.assertEqual(draft['existing_fact_id'],'location')

 def test_case_confirmed_facts_do_not_become_global_profile(self):
  self.chat(self.a)
  self.a.put('/api/memory/facts/treatment',json={'label':'实际处理','content':'只在这次案例做了排水观察','case_id':'case-a'},headers=self.headers)
  self.assertEqual(self.a.get('/api/memory/profile').json()['facts'],[])
  seen=[]
  def model(messages,**kwargs):seen.append(json.dumps(messages[1:],ensure_ascii=False));return iter(['收到。'])
  with patch.object(config,'SPARK_API_PASSWORD','test'),patch.object(dialogue.llm,'chat_stream',side_effect=model):
   for case,turn in [('case-a','same-case'),('case-b','new-case')]:
    self.a.post('/api/agent/chat',headers={'X-Zhimai-Stream-Protocol':STREAM_PROTOCOL},data={'message':'继续看看','case_id':case,'turn_id':turn})
  self.assertIn('只在这次案例做了排水观察',seen[0])
  self.assertNotIn('只在这次案例做了排水观察',seen[1])

 def test_duplicate_turn_does_not_reopen_archived_case(self):
  self.chat(self.a)
  self.a.patch('/api/memory/cases/case-a',headers=self.headers,json={'title':'已结束的问题','archived':True})
  self.chat(self.a)
  self.assertTrue(self.a.get('/api/memory/cases/case-a').json()['archived'])

 def test_write_header_and_invalid_history_id(self):
  self.assertEqual(self.a.put('/api/memory/facts/f',json={'label':'a','content':'b'}).status_code,403)
  self.assertEqual(self.chat(self.a,case_id='../secret').status_code,400)

if __name__=='__main__':unittest.main(verbosity=2)
