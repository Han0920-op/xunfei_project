"""Browser-owned inventory, persisted reminder jobs and readable delivery status."""
import json
import logging
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
import weather

PATH = Path(__file__).parent / 'data/local/personal.db'
TZ = ZoneInfo('Asia/Shanghai')
router = APIRouter(prefix='/api/personal')


def now():
    return datetime.now(TZ)


@contextmanager
def db():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(PATH, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        c.execute('CREATE TABLE IF NOT EXISTS entries(owner TEXT,id TEXT,kind TEXT,body TEXT,next TEXT,PRIMARY KEY(owner,id))')
        c.execute('CREATE TABLE IF NOT EXISTS jobs(owner TEXT,id TEXT,task_id TEXT,body TEXT,scheduled TEXT,lease TEXT,PRIMARY KEY(owner,id))')
        c.execute('CREATE TABLE IF NOT EXISTS scheduler_meta(key TEXT PRIMARY KEY,value TEXT)')
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


def owner(request):
    token = request.cookies.get('zhimai_owner', '')
    if len(token) != 64 or any(x not in '0123456789abcdef' for x in token):
        raise HTTPException(401, '请刷新页面建立个人资料连接')
    return token


@router.get('/session')
def session(request: Request, response: Response):
    token = request.cookies.get('zhimai_owner', '')
    if len(token) != 64 or any(x not in '0123456789abcdef' for x in token):
        token = secrets.token_hex(32)
    response.set_cookie('zhimai_owner', token, httponly=True, samesite='strict', max_age=31536000)
    response.headers['Cache-Control'] = 'no-store'
    return {'ready': True}


@router.get('/status')
def status(request: Request, response: Response):
    who = owner(request)
    response.headers['Cache-Control'] = 'no-store'
    with db() as c:
        heartbeat = c.execute("SELECT value FROM scheduler_meta WHERE key='heartbeat'").fetchone()
        pending = c.execute('SELECT count(*) FROM jobs WHERE owner=?', (who,)).fetchone()[0]
    last = heartbeat['value'] if heartbeat else None
    return {'scheduler_running': bool(last and timedelta(0) <= now()-datetime.fromisoformat(last) < timedelta(seconds=90)),
            'last_scan': last, 'pending_jobs': pending, 'timezone': 'Asia/Shanghai'}


class Entry(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    number: str = Field(default='', max_length=30)
    notes: str = Field(default='', max_length=500)
    location: str = Field(default='', max_length=80)
    time: str = Field(default='08:00', pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    enabled: bool = True
    task_type: Literal['weather', 'reminder'] = 'weather'
    recurrence: Literal['daily', 'once'] = 'daily'
    run_at: str = Field(default='', max_length=40)


def next_time(clock):
    current = now()
    h, m = map(int, clock.split(':'))
    target = current.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return target.isoformat()


def due_time(item):
    if not item.enabled:
        return ''
    if item.recurrence == 'daily':
        return next_time(item.time)
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?', item.run_at):
            raise ValueError('explicit date and clock required')
        target = datetime.fromisoformat(item.run_at)
        if target.tzinfo is None:
            target = target.replace(tzinfo=TZ)
        target = target.astimezone(TZ)
    except ValueError:
        raise HTTPException(400, '请填写明确的提醒日期和时间（北京时间）') from None
    if target <= now():
        raise HTTPException(400, '这个时间已经过去，请重新选择未来的日期和时间')
    return target.isoformat()


def validate_task(item):
    if item.task_type == 'weather' and not weather._location_code(item.location):
        raise HTTPException(400, '请填写支持的城市（如郑州）或六位市县行政区编码')
    return due_time(item)


def listing(who, kind):
    with db() as c:
        rows = c.execute('SELECT * FROM entries WHERE owner=? AND kind=? ORDER BY rowid DESC LIMIT 200', (who, kind)).fetchall()
    return [{**({'task_type': 'weather', 'recurrence': 'daily'} if kind == 'tasks' else {}),
             **json.loads(r['body']), 'id': r['id'], 'next': r['next']} for r in rows]


@router.get('/{kind}')
def items(kind: str, request: Request, response: Response):
    if kind not in ('medicines', 'tasks', 'notifications'):
        raise HTTPException(404)
    response.headers['Cache-Control'] = 'no-store'
    return listing(owner(request), kind)


@router.put('/{kind}/{identifier}')
def save(kind: str, identifier: str, item: Entry, request: Request):
    if request.headers.get('X-Zhimai-Personal') != '1':
        raise HTTPException(403)
    if kind not in ('medicines', 'tasks') or not identifier or len(identifier) > 80:
        raise HTTPException(400)
    who = owner(request)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        old = c.execute('SELECT * FROM entries WHERE owner=? AND id=?', (who, identifier)).fetchone()
        if old and old['kind'] != kind:
            raise HTTPException(409, '记录编号已使用，请刷新后重试')
        data = item.model_dump()
        previous = json.loads(old['body']) if old else {}
        previous.pop('_revision', None)
        previous.pop('_completed_at', None)
        same = bool(old and previous == data)
        if not old and c.execute('SELECT count(*) FROM entries WHERE owner=? AND kind=?', (who, kind)).fetchone()[0] >= (20 if kind == 'tasks' else 100):
            raise HTTPException(400, '保存数量已达上限，请先删除不需要的记录')
        due = old['next'] if same else validate_task(item) if kind == 'tasks' else ''
        body = old['body'] if same else json.dumps({**data, '_revision': secrets.token_hex(12)}, ensure_ascii=False)
        c.execute('INSERT INTO entries VALUES(?,?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET body=excluded.body,next=excluded.next', (who, identifier, kind, body, due))
    return {'saved': True, 'id': identifier, 'next': due}


@router.post('/notifications/{identifier}/read')
def mark_read(identifier: str, request: Request):
    if request.headers.get('X-Zhimai-Personal') != '1':
        raise HTTPException(403)
    with db() as c:
        row = c.execute("SELECT body FROM entries WHERE owner=? AND id=? AND kind='notifications'", (owner(request), identifier)).fetchone()
        if not row:
            raise HTTPException(404)
        body = json.loads(row['body'])
        body['read'] = True
        c.execute('UPDATE entries SET body=? WHERE owner=? AND id=?', (json.dumps(body, ensure_ascii=False), owner(request), identifier))
    return {'read': True}


@router.delete('/{kind}/{identifier}')
def delete(kind: str, identifier: str, request: Request):
    if request.headers.get('X-Zhimai-Personal') != '1':
        raise HTTPException(403)
    with db() as c:
        c.execute('DELETE FROM entries WHERE owner=? AND kind=? AND id=?', (owner(request), kind, identifier))
    return {'deleted': True}


def tick():
    current = now().isoformat()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("INSERT OR REPLACE INTO scheduler_meta VALUES('heartbeat',?)", (current,))
        rows = c.execute("SELECT * FROM entries WHERE kind='tasks' AND next!='' AND next<=?", (current,)).fetchall()
        for r in rows:
            item = json.loads(r['body'])
            c.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?)', (r['owner'], r['id']+'_'+r['next'], r['id'], r['body'], r['next'], ''))
            following = next_time(item['time']) if item.get('recurrence', 'daily') == 'daily' else ''
            c.execute('UPDATE entries SET next=? WHERE owner=? AND id=?', (following, r['owner'], r['id']))
        jobs = c.execute("SELECT * FROM jobs WHERE lease='' OR lease<?", (current,)).fetchall()
        lease = (now()+timedelta(minutes=5)).isoformat()
        for job in jobs:
            c.execute('UPDATE jobs SET lease=? WHERE owner=? AND id=?', (lease, job['owner'], job['id']))
    for r in sorted(jobs, key=lambda r: json.loads(r['body']).get('task_type', 'weather') != 'reminder'):
        item = json.loads(r['body'])
        # Check cancellation before paying for weather, then again before publish.
        with db() as c:
            active = c.execute('SELECT body FROM entries WHERE owner=? AND id=?', (r['owner'], r['task_id'])).fetchone()
            if not active or active['body'] != r['body']:
                c.execute('DELETE FROM jobs WHERE owner=? AND id=?', (r['owner'], r['id']))
                continue
        result = None
        if item.get('task_type', 'weather') == 'weather':
            try:
                result = json.loads(weather.get_weather(item['location'], 'today'))
            except Exception:
                result = {'status': 'unavailable'}
            message = (f"{result.get('location', item['location'])}：{result.get('weather', '')} {result.get('temperature', '')}。" if result.get('status') == 'ok' else '天气查询失败，未取得可靠天气。')
            message += item['notes']+'。请观察异常范围、新叶和叶背并拍照对比；城市预报不能作为施药许可。'
        else:
            message = item['notes'] or item['name']
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            active = c.execute('SELECT body FROM entries WHERE owner=? AND id=?', (r['owner'], r['task_id'])).fetchone()
            if active and active['body'] == r['body']:
                payload = {'name': item['name'], 'message': message, 'weather': result, 'task_type': item.get('task_type', 'weather'),
                           'created_at': now().isoformat(), 'scheduled_for': r['scheduled'], 'read': False}
                c.execute('INSERT OR IGNORE INTO entries VALUES(?,?,?,?,?)', (r['owner'], r['id'], 'notifications', json.dumps(payload, ensure_ascii=False), ''))
                if item.get('recurrence') == 'once':
                    item.update(enabled=False, _completed_at=now().isoformat())
                    c.execute('UPDATE entries SET body=? WHERE owner=? AND id=?', (json.dumps(item, ensure_ascii=False), r['owner'], r['task_id']))
            c.execute('DELETE FROM jobs WHERE owner=? AND id=?', (r['owner'], r['id']))


def start():
    stop = threading.Event()
    def loop():
        while not stop.is_set():
            try:
                tick()
            except Exception:
                logging.getLogger('uvicorn.error').warning('personal_scheduler_failed; pending jobs retained')
            stop.wait(3)
    threading.Thread(target=loop, daemon=True).start()
    return stop
