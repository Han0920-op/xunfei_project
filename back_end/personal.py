"""Persistent browser-owned inventory and daily weather checks."""
import json, secrets, sqlite3, threading
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, Field, ConfigDict
import weather

PATH = Path(__file__).parent / 'data/local/personal.db'
TZ = ZoneInfo('Asia/Shanghai')
router = APIRouter(prefix='/api/personal')

def db():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(PATH, timeout=15); c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS entries(owner TEXT,id TEXT,kind TEXT,body TEXT,next TEXT,PRIMARY KEY(owner,id))')
    c.execute('CREATE TABLE IF NOT EXISTS jobs(owner TEXT,id TEXT,task_id TEXT,body TEXT,scheduled TEXT,lease TEXT,PRIMARY KEY(owner,id))')
    return c

def owner(request):
    token=request.cookies.get('zhimai_owner','')
    if len(token)!=64 or any(x not in '0123456789abcdef' for x in token):
        raise HTTPException(401,'请刷新页面建立个人资料连接')
    return token

@router.get('/session')
def session(request:Request,response:Response):
    token=request.cookies.get('zhimai_owner','')
    if len(token)!=64 or any(x not in '0123456789abcdef' for x in token): token=secrets.token_hex(32)
    response.set_cookie('zhimai_owner',token,httponly=True,samesite='strict',max_age=31536000)
    response.headers['Cache-Control']='no-store'
    return {'ready':True}

class Entry(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=100)
    number:str=Field(default='',max_length=30)
    notes:str=Field(default='',max_length=500)
    location:str=Field(default='',max_length=80)
    time:str=Field(default='08:00',pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    enabled:bool=True

def next_time(clock):
    now=datetime.now(TZ); h,m=map(int,clock.split(':'))
    target=now.replace(hour=h,minute=m,second=0,microsecond=0)
    if target<=now:target+=timedelta(days=1)
    return target.isoformat()

def listing(who,kind):
    with db() as c:return [{**json.loads(r['body']),'id':r['id'],'next':r['next']} for r in c.execute('SELECT * FROM entries WHERE owner=? AND kind=? ORDER BY rowid DESC',(who,kind))]

@router.get('/{kind}')
def items(kind:str,request:Request):
    if kind not in ('medicines','tasks','notifications'):raise HTTPException(404)
    return listing(owner(request),kind)

@router.put('/{kind}/{identifier}')
def save(kind:str,identifier:str,item:Entry,request:Request):
    if request.headers.get('X-Zhimai-Personal')!='1':raise HTTPException(403)
    if kind not in ('medicines','tasks') or len(identifier)>80:raise HTTPException(400)
    if kind=='tasks' and not weather._location_code(item.location):raise HTTPException(400,'请填写支持的城市（如郑州）或六位市县行政区编码')
    who=owner(request)
    with db() as c:
        old=c.execute('SELECT body,next FROM entries WHERE owner=? AND id=?',(who,identifier)).fetchone()
        data=item.model_dump()
        previous=json.loads(old['body']) if old else {}
        previous.pop('_revision',None)
        same=bool(old and previous==data)
        if not same and len(listing(who,kind)) >= (20 if kind=='tasks' else 100) and not old:
            raise HTTPException(400,'保存数量已达上限，请先删除不需要的记录')
        body=old['body'] if same else json.dumps({**data,'_revision':secrets.token_hex(12)},ensure_ascii=False)
        due=old['next'] if same else next_time(item.time) if kind=='tasks' and item.enabled else ''
        c.execute('INSERT INTO entries VALUES(?,?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET body=excluded.body,next=excluded.next',(who,identifier,kind,body,due))
    return {'saved':True}

@router.delete('/{kind}/{identifier}')
def delete(kind:str,identifier:str,request:Request):
    if request.headers.get('X-Zhimai-Personal')!='1':raise HTTPException(403)
    with db() as c:c.execute('DELETE FROM entries WHERE owner=? AND kind=? AND id=?',(owner(request),kind,identifier))
    return {'deleted':True}

def tick():
    now=datetime.now(TZ).isoformat()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        rows=c.execute("SELECT * FROM entries WHERE kind='tasks' AND next!='' AND next<=?",(now,)).fetchall()
        for r in rows:
            c.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?)',(r['owner'],r['id']+'_'+r['next'],r['id'],r['body'],r['next'],''))
            c.execute('UPDATE entries SET next=? WHERE owner=? AND id=?',(next_time(json.loads(r['body'])['time']),r['owner'],r['id']))
        jobs=c.execute("SELECT * FROM jobs WHERE lease='' OR lease<?",(now,)).fetchall()
        lease=(datetime.now(TZ)+timedelta(minutes=5)).isoformat()
        for job in jobs:c.execute('UPDATE jobs SET lease=? WHERE owner=? AND id=?',(lease,job['owner'],job['id']))
    for r in jobs:
        item=json.loads(r['body'])
        try:result=json.loads(weather.get_weather(item['location'],'today'))
        except Exception:result={'status':'unavailable'}
        message=(f"{result.get('location',item['location'])}：{result.get('weather','')} {result.get('temperature','')}。" if result.get('status')=='ok' else '天气查询失败，未取得可靠天气。')
        message+=item['notes']+'。请观察异常范围、新叶和叶背并拍照对比；城市预报不能作为施药许可。'
        with db() as c:
            current=c.execute('SELECT body FROM entries WHERE owner=? AND id=?',(r['owner'],r['task_id'])).fetchone()
            if not current or current['body']!=r['body']:
                c.execute('DELETE FROM jobs WHERE owner=? AND id=?',(r['owner'],r['id']))
                continue
            payload={'name':item['name'],'message':message,'weather':result,'created_at':datetime.now(TZ).isoformat()}
            c.execute('INSERT OR IGNORE INTO entries VALUES(?,?,?,?,?)',(r['owner'],r['id'],'notifications',json.dumps(payload,ensure_ascii=False),''))
            c.execute('DELETE FROM jobs WHERE owner=? AND id=?',(r['owner'],r['id']))

def start():
    stop=threading.Event()
    def loop():
        while not stop.is_set():
            try:tick()
            except Exception:
                import logging
                logging.getLogger("uvicorn.error").warning("personal_scheduler_failed; pending jobs retained")
            stop.wait(15)
    thread=threading.Thread(target=loop,daemon=True);thread.start()
    return stop
