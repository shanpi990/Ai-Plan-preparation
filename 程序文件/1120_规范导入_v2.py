import sqlite3,json,base64,runpy,threading,uuid,datetime
from contextlib import contextmanager
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DB=ROOT.parent/'配置文件/1120_规范原文库_v1.sqlite3'
P=runpy.run_path(str(ROOT/'1120_条文解析_v1.py'))
parse=P['parse']
TASKS={};LOCK=threading.Lock()
@contextmanager
def connection():
    c=sqlite3.connect(DB,timeout=25);c.row_factory=sqlite3.Row
    try:
        c.execute('PRAGMA foreign_keys=ON')
        with c:yield c
    finally:c.close()

def initialize():
    with connection() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS book(id TEXT PRIMARY KEY,code TEXT NOT NULL,title TEXT NOT NULL,effective_date TEXT,status TEXT NOT NULL,categories TEXT NOT NULL,whole_mandatory INTEGER,source_name TEXT,imported_at TEXT,parse_report TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS current_code ON book(code) WHERE status='现行';
CREATE TABLE IF NOT EXISTS clause(id INTEGER PRIMARY KEY,book_id TEXT REFERENCES book(id) ON DELETE CASCADE,number TEXT NOT NULL,chapter_path TEXT,body TEXT NOT NULL,explanation TEXT,mandatory INTEGER,location TEXT,ord INTEGER,enabled INTEGER,edited INTEGER,UNIQUE(book_id,number));
INSERT OR IGNORE INTO meta VALUES('schema_version','1');
""")
        if any('ENABLE_FTS5' in r[0] for r in c.execute('pragma compile_options')):
            try:
                c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS clause_fts USING fts5(body,chapter_path,number,tokenize='trigram')")
                for event,sql in [('insert','INSERT INTO clause_fts(rowid,body,chapter_path,number) VALUES(new.id,new.body,new.chapter_path,new.number);'),('delete','DELETE FROM clause_fts WHERE rowid=old.id;'),('update','UPDATE clause_fts SET body=new.body,chapter_path=new.chapter_path,number=new.number WHERE rowid=old.id;')]:
                    c.execute(f'CREATE TRIGGER IF NOT EXISTS sync_{event} AFTER {event} ON clause BEGIN {sql} END')
            except sqlite3.OperationalError:pass
        legacy=DB.with_name('导入规范.sqlite3')
        if legacy.exists() and not c.execute("select 1 from meta where key='legacy'").fetchone():
            with sqlite3.connect(legacy) as old:
                if old.execute("select 1 from sqlite_master where name='books'").fetchone():
                    for key,name in old.execute('select id,name from books'):
                        c.execute("insert or ignore into book values(?,?,?,'','停用','[]',0,?,CURRENT_TIMESTAMP,'[]')",(key,'待核-'+key[:8],name,name))
                        for i,(n,loc,b) in enumerate(old.execute('select num,loc,body from clauses where book=?',(key,))):
                            c.execute("insert or ignore into clause(book_id,number,location,body,ord,mandatory,enabled,edited) values(?,?,?,?,?,0,1,0)",(key,n,loc,b,i))
            c.execute("insert into meta values('legacy','1')")

def books(c):
    return [dict(r)|{'categories':json.loads(r['categories'])} for r in c.execute("""select b.*,count(c.id) as clause_count,coalesce(sum(c.mandatory),0) as mandatory_count from book b left join clause c on c.book_id=b.id and c.enabled=1 group by b.id order by imported_at desc""")]

def save(c,data):
    m=data['meta_guess'];key=m['id'];code=P['code'](m['code'].strip());title=m['title'].strip()
    if not code or not title or not data['clauses']:raise ValueError('编号、名称和条文不能为空')
    if c.execute('select 1 from book where id=?',(key,)).fetchone():raise ValueError('相同文件已入库')
    old=c.execute("select id from book where code=? and status='现行'",(code,)).fetchone()
    if old and not data.get('replace'):return {'conflict':True}
    if old:c.execute("update book set status='被替代' where id=?",tuple(old))
    whole=bool(m.get('whole_mandatory') or __import__('re').match(r'GB 55\d{3}-',code))
    c.execute('insert into book values(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?)',(key,code,title,m.get('effective_date',''),'现行',json.dumps(m.get('categories',[])),whole,m.get('source_name',''),json.dumps(data.get('warnings',[]),ensure_ascii=False)))
    seen=set()
    for i,x in enumerate(data['clauses']):
        number=x['number'].strip()
        if number in seen:raise ValueError(f'条号 {number} 重复，请在校对页修改或删除重复条文')
        seen.add(number)
        if not x['number'].strip() or not x['body'].strip():raise ValueError('请补齐条号及正文')
        c.execute('insert into clause(book_id,number,chapter_path,body,explanation,mandatory,location,ord,enabled,edited) values(?,?,?,?,?,?,?,?,?,?)',(key,x['number'].strip(),x.get('chapter_path',''),x['body'],x.get('explanation',''),whole or bool(x.get('mandatory')),x.get('location',''),i,bool(x.get('enabled',True)),bool(x.get('edited'))))
    return {'id':key}

def expire_preview(key):
    with LOCK:TASKS.pop(key,None)

def dispatch(action,data):
    if action=='preview':
        key=uuid.uuid4().hex
        def worker():
            try:res={'preview':parse(data['name'],base64.b64decode(data['raw'],validate=True))}
            except Exception as e:res={'error':str(e)}
            with LOCK:TASKS[key]=res
            timer=threading.Timer(600,expire_preview,args=(key,))
            timer.daemon=True
            timer.start()
        with LOCK:TASKS[key]={'running':True}
        threading.Thread(target=worker,daemon=True).start()
        return {'task':key}
    if action=='progress':
        with LOCK:
            r=TASKS.get(data.get('task'))
            if r is None:return {'error':'任务已结束或已过期，请重新选择文件'}
            if not r.get('running'):TASKS.pop(data['task'])
            return r
    with connection() as c:
        if action=='list':return {'books':books(c)}
        if action=='commit':
            c.execute('begin immediate');return save(c,data)
        key=data['id']
        if action in ('read','export'):
            b=next(b for b in books(c) if b['id']==key)
            return {'book':b,'rows':[dict(x) for x in c.execute('select * from clause where book_id=? order by ord',(key,))]}
        if action=='delete_book':c.execute('delete from book where id=?',(key,))
        elif action=='update_book':
            if 'status' in data:
                if data['status'] not in ('现行','停用','被替代'):raise ValueError('状态无效')
                try:c.execute('update book set status=? where id=?',(data['status'],key))
                except sqlite3.IntegrityError as exc:raise ValueError('同编号已有现行规范，请先停用另一本，再启用本版') from exc
            if 'title' in data:
                title=data['title'].strip()
                if not title:raise ValueError('请输入规范名称')
                c.execute('update book set title=?,effective_date=?,categories=? where id=?',(title,data.get('effective_date',''),json.dumps(data.get('categories',[])),key))
        elif action=='update_clause':
            if not data['body'].strip():raise ValueError('正文为空')
            c.execute('update clause set body=?,mandatory=max(?,(select whole_mandatory from book where id=book_id)),enabled=?,edited=1 where id=?',(data['body'],bool(data['mandatory']),bool(data['enabled']),key))
        else:raise ValueError('未知操作')
        return {'ok':True}

