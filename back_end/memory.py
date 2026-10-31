"""Owned, sourced long-term facts and case history. No raw photos or model text in logs."""
import hashlib
import json
import re
import secrets
from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
import personal

router = APIRouter(prefix='/api/memory')


@contextmanager
def db():
    with personal.db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS memory_cases(id TEXT PRIMARY KEY,owner TEXT NOT NULL,title TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS memory_turns(id TEXT PRIMARY KEY,case_id TEXT NOT NULL,owner TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS memory_facts(id TEXT NOT NULL,owner TEXT NOT NULL,case_id TEXT NOT NULL,label TEXT NOT NULL,content TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(owner,id))')
        c.execute('CREATE TABLE IF NOT EXISTS memory_deleted(id TEXT PRIMARY KEY,owner TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS memory_recovery(owner TEXT PRIMARY KEY,digest TEXT UNIQUE NOT NULL)')
        yield c


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise HTTPException(400, '资料编号格式不正确')
    return value


def owned(c, who, case_id):
    row = c.execute('SELECT * FROM memory_cases WHERE id=? AND owner=?', (case_id, who)).fetchone()
    if row is None:
        raise HTTPException(404, '这条案例不属于当前身份，或已被删除')
    return row


def write_owner(request):
    if request.headers.get('X-Zhimai-Personal') != '1':
        raise HTTPException(403)
    return personal.owner(request)


def guard_deleted(c,who,case_id):
    deleted=c.execute('SELECT owner FROM memory_deleted WHERE id=?',(case_id,)).fetchone()
    if deleted:
        raise HTTPException(410 if deleted['owner']==who else 404,'案例已删除或不属于当前身份，请开始新问题')


def case_meta(row):
    return {'id': row['id'], 'title': row['title'], 'created_at': row['created'], 'updated_at': row['updated'], 'archived': bool(row['archived'])}


def facts(who, case_id=''):
    with db() as c:
        return [{'id':r['id'],'case_id':r['case_id'],'label':r['label'],'content':r['content'],'updated_at':r['updated'],
                 'source_type':'user_confirmed','notice':'用户确认的资料，不是独立农技核验'}
                for r in c.execute('SELECT * FROM memory_facts WHERE owner=? AND case_id=? ORDER BY updated DESC', (who,case_id))]


def cases(who, query=''):
    # Search only titles, user statements, and confirmed facts. Inferences never
    # become evidence for matching a diagnosis. Return summaries, not full chats.
    tokens = [query[i:i+2] for i in range(len(query)-1)] if len(query)>1 else [query]
    tokens = [t for t in tokens if t.strip() and t not in ('上次','之前','那个','问题','小麦','记得')]
    with db() as c:
        rows=c.execute('SELECT * FROM memory_cases WHERE owner=? ORDER BY updated DESC LIMIT 200',(who,)).fetchall()
        results=[]
        for row in rows:
            reports=[]
            for turn in c.execute('SELECT body FROM memory_turns WHERE owner=? AND case_id=? ORDER BY created DESC LIMIT 30',(who,row['id'])):
                reports.append(json.loads(turn['body'])['user']['text'])
            confirmed=[r['content'] for r in c.execute('SELECT content FROM memory_facts WHERE owner=? AND case_id=?',(who,row['id']))]
            text=row['title']+' '.join(reports+confirmed)
            score=sum(t in text for t in tokens)
            if query and tokens and score==0:continue
            results.append({**case_meta(row),'summary':(reports[0] if reports else row['title'])[:150], '_score':score,
                            'notice':'用户历史描述，仅作候选案例，请先确认关联'})
    if query:results.sort(key=lambda x:x['_score'],reverse=True)
    return [{k:v for k,v in r.items() if k!='_score'} for r in results[:(3 if query else 100)]]


def get_case(who, case_id):
    with db() as c:
        row=owned(c,who,case_id)
        turns=[{**json.loads(r['body']),'created_at':r['created'],'turn_id':r['id']} for r in reversed(c.execute('SELECT * FROM memory_turns WHERE owner=? AND case_id=? ORDER BY created DESC,rowid DESC LIMIT 200',(who,case_id)).fetchall())]
    return {**case_meta(row),'turns':turns,'facts':facts(who,case_id),'photos_stored':False}


def fact_context(who, case_id=None):
    items=facts(who)[:10]
    if case_id:
        with db() as c:
            guard_deleted(c,who,case_id)
            row=c.execute('SELECT owner FROM memory_cases WHERE id=?',(case_id,)).fetchone()
            if row and row['owner']!=who:raise HTTPException(404,'案例不属于当前身份')
        items=facts(who,case_id)[:10]+items
    return items[:20]


def save_turn(who,case_id,turn_id,message,answer,vision,tool_results,has_image,photo_id=""):
    identifier(case_id);identifier(turn_id)
    body={'user':{'id':turn_id+'-u','role':'user','text':message or '帮我看看这张照片','source_type':'user_reported','had_image':bool(has_image), 'photoId':photo_id if has_image else ''},
          'assistant':{'id':turn_id+'-a','role':'assistant','type':'agent','text':answer,'source_type':'model_inference',
                       'vision':vision,'toolResults':tool_results,'notice':'模型判断未确诊，不自动写入已确认事实'}}
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        guard_deleted(c,who,case_id)
        existing=c.execute('SELECT * FROM memory_cases WHERE id=?',(case_id,)).fetchone()
        if existing and existing['owner']!=who:raise HTTPException(404,'案例不属于当前身份')
        if not existing:
            if c.execute('SELECT count(*) FROM memory_cases WHERE owner=?',(who,)).fetchone()[0]>=200:raise ValueError('case limit')
            c.execute('INSERT INTO memory_cases VALUES(?,?,?,?,?,0)',(case_id,who,(message or '照片中的小麦情况')[:80],personal.now().isoformat(),personal.now().isoformat()))
        other=c.execute('SELECT case_id,owner FROM memory_turns WHERE id=?',(turn_id,)).fetchone()
        if other and (other['owner']!=who or other['case_id']!=case_id):raise HTTPException(409,'请求编号已使用')
        inserted=c.execute('INSERT OR IGNORE INTO memory_turns VALUES(?,?,?,?,?)',(turn_id,case_id,who,json.dumps(body,ensure_ascii=False),personal.now().isoformat()))
        if inserted.rowcount:
            c.execute('UPDATE memory_cases SET updated=?,archived=0 WHERE id=?',(personal.now().isoformat(),case_id))


class Fact(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    label:str=Field(min_length=1,max_length=80)
    content:str=Field(min_length=1,max_length=2000)
    case_id:str=Field(default='',max_length=80)


@router.get('/profile')
def profile(request:Request,response:Response):
    who=personal.owner(request);response.headers['Cache-Control']='no-store'
    with db() as c:recovery=c.execute('SELECT 1 FROM memory_recovery WHERE owner=?',(who,)).fetchone()
    return {'facts':facts(who),'recovery_enabled':bool(recovery),'identity':'browser_owned','photos_stored':False}


@router.get('/cases')
def list_cases(request:Request,response:Response,q:str=''):
    response.headers['Cache-Control']='no-store'
    if len(q)>200:raise HTTPException(400,'检索文字过长')
    return cases(personal.owner(request),q)


@router.get('/cases/{case_id}')
def read_case(case_id:str,request:Request,response:Response):
    response.headers['Cache-Control']='no-store'
    return get_case(personal.owner(request),case_id)


class CaseEdit(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    title:str=Field(min_length=1,max_length=80)
    archived:bool=False


@router.patch('/cases/{case_id}')
def update_case(case_id:str,item:CaseEdit,request:Request):
    who=write_owner(request)
    with db() as c:
        owned(c,who,case_id)
        c.execute('UPDATE memory_cases SET title=?,archived=?,updated=? WHERE owner=? AND id=?',(item.title,int(item.archived),personal.now().isoformat(),who,case_id))
    return {'saved':True}


@router.delete('/cases/{case_id}')
def delete_case(case_id:str,request:Request):
    who=write_owner(request)
    with db() as c:
        c.execute('BEGIN IMMEDIATE');owned(c,who,case_id)
        c.execute('DELETE FROM memory_facts WHERE owner=? AND case_id=?',(who,case_id))
        c.execute('DELETE FROM memory_turns WHERE owner=? AND case_id=?',(who,case_id))
        c.execute('DELETE FROM memory_cases WHERE owner=? AND id=?',(who,case_id))
        c.execute('INSERT OR REPLACE INTO memory_deleted VALUES(?,?)',(case_id,who))
    return {'deleted':True}


@router.put('/facts/{fact_id}')
def put_fact(fact_id:str,item:Fact,request:Request):
    who=write_owner(request);identifier(fact_id)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if item.case_id:owned(c,who,item.case_id)
        old=c.execute('SELECT 1 FROM memory_facts WHERE owner=? AND id=?',(who,fact_id)).fetchone()
        if not old and c.execute('SELECT count(*) FROM memory_facts WHERE owner=? AND case_id=?',(who,item.case_id)).fetchone()[0]>=30:raise HTTPException(400,'每个范围最多30条，请先整理旧资料')
        c.execute('INSERT INTO memory_facts VALUES(?,?,?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET case_id=excluded.case_id,label=excluded.label,content=excluded.content,updated=excluded.updated',(fact_id,who,item.case_id,item.label,item.content,personal.now().isoformat()))
    return {'saved':True,'source_type':'user_confirmed'}


@router.delete('/facts/{fact_id}')
def delete_fact(fact_id:str,request:Request):
    who=write_owner(request)
    with db() as c:c.execute('DELETE FROM memory_facts WHERE owner=? AND id=?',(who,fact_id))
    return {'deleted':True}


class Recovery(BaseModel):
    model_config=ConfigDict(extra='forbid')
    code:str=Field(min_length=40,max_length=100)


@router.post('/recovery')
def recovery(request:Request,response:Response):
    who=write_owner(request);code=secrets.token_urlsafe(40)
    with db() as c:c.execute('INSERT OR REPLACE INTO memory_recovery VALUES(?,?)',(who,hashlib.sha256(code.encode()).hexdigest()))
    response.headers['Cache-Control']='no-store'
    return {'code':code,'notice':'请离线保管，不要发给他人；重置后旧码失效'}


@router.post('/restore')
def restore(item:Recovery,request:Request,response:Response):
    write_owner(request)
    with db() as c:row=c.execute('SELECT owner FROM memory_recovery WHERE digest=?',(hashlib.sha256(item.code.strip().encode()).hexdigest(),)).fetchone()
    if not row:raise HTTPException(400,'恢复码无效')
    response.set_cookie('zhimai_owner',row['owner'],httponly=True,samesite='strict',max_age=31536000)
    response.headers['Cache-Control']='no-store'
    return {'restored':True,'notice':'已切换资料身份；本机旧照片不会自动同步'}


class ImportedMessage(BaseModel):
    model_config=ConfigDict(extra='ignore',str_strip_whitespace=True)
    id:str=Field(max_length=100)
    role:Literal['user','assistant']
    text:str=Field(default='',max_length=6000)


class CaseImport(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(max_length=80)
    title:str=Field(min_length=1,max_length=80)
    messages:list[ImportedMessage]=Field(min_length=1,max_length=200)
    demo:bool=False


@router.post('/import')
def import_case(item:CaseImport,request:Request):
    who=write_owner(request);identifier(item.id)
    if item.demo:raise HTTPException(400,'演示记录不能作为真实长期记忆同步')
    pairs=[];pending=None
    for m in item.messages:
        if m.role=='user':
            if pending:pairs.append((pending,None))
            pending=m
        elif pending:
            pairs.append((pending,m));pending=None
    if pending:pairs.append((pending,None))
    if not pairs:raise HTTPException(400,'缺少用户描述，不能同步为空案例')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        guard_deleted(c,who,item.id)
        existing=c.execute('SELECT owner FROM memory_cases WHERE id=?',(item.id,)).fetchone()
        if existing:
            if existing['owner']!=who:raise HTTPException(404,'案例不属于当前身份')
            raise HTTPException(409,'此案例已经同步，请直接查看服务端案例')
        if c.execute('SELECT count(*) FROM memory_cases WHERE owner=?',(who,)).fetchone()[0]>=200:raise HTTPException(400,'案例数量已达上限')
        c.execute('INSERT INTO memory_cases VALUES(?,?,?,?,?,0)',(item.id,who,item.title,personal.now().isoformat(),personal.now().isoformat()))
        for index,(u,a) in enumerate(pairs):
            turn_id='import-'+hashlib.sha256((item.id+str(index)).encode()).hexdigest()[:32]
            body={'user':{'id':u.id,'role':'user','text':u.text,'source_type':'imported_user_reported'},
                  'assistant':{'id':a.id if a else turn_id+'a','role':'assistant','type':'agent','text':a.text if a else '此前用户记录，尚无模型判断。','source_type':'imported_unverified_inference','vision':[],'toolResults':[]}}
            c.execute('INSERT INTO memory_turns VALUES(?,?,?,?,?)',(turn_id,item.id,who,json.dumps(body,ensure_ascii=False),personal.now().isoformat()))
    return {'saved':True,'case_id':item.id,'notice':'仅同步文字，未上传旧照片；历史判断未升级为事实'}


class CaseSearch(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    query:str=Field(default='',max_length=200)


@router.post('/search')
def search_cases(item:CaseSearch,request:Request,response:Response):
    who=write_owner(request);response.headers['Cache-Control']='no-store'
    return cases(who,item.query)
