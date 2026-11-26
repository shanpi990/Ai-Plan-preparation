"""飞书主题客户端服务；沿用 v15 的图文审查与整改功能。"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import runpy,json,threading,sys,webbrowser,sqlite3
ROOT=Path(__file__).parent
previous=runpy.run_path(str(ROOT/'图文服务_v16.py'),init_globals={'_test_transport':globals().get('_test_transport')})
ctx=previous['ctx'];X=previous['X'];LocalServer=previous['LocalServer']
runpy.run_path(str(ROOT/'整改分批与记录导入_v1.py'))['install'](ctx,X)
standard_catalog = runpy.run_path(str(ROOT/'规范条文查询_v2.py'))['lookup']

def standards_for_today():
    day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    return standard_catalog(as_of=day)

import hashlib
lib=runpy.run_path(str(ROOT/'规范导入_v2.py'))
lib['initialize']()
search=runpy.run_path(str(ROOT/'规范检索_v1.py'))['retrieve']
def catalog(category):
    builtin=standards_for_today()['standards']
    items={b['code']:dict(b,book_id=None,whole_mandatory=bool(b['whole_standard_mandatory']),default_selected=category=='excavation' and b.get('default_selected',False)) for b in builtin}
    for book in lib['dispatch']('list',{})['books']:
        if book['status']!='现行' or (book['categories'] and category not in book['categories']):continue
        items[book['code']]=dict(code=book['code'],title=book['title'],book_id=book['id'],clause_count=book['clause_count'],whole_mandatory=bool(book['whole_mandatory']),default_selected=items.get(book['code'],{}).get('default_selected',bool(book['categories'])))
    return list(items.values())
def prepare_standards(kind,data):
    library=ctx['TYPES']['load_library'](ctx['E']['CONFIG_ROOT'],[])
    category=next((c['id'] for c in library['categories'] if c['name']==kind),None)
    codes=data.get('standardCodes',[])
    selected=[b for b in catalog(category) if b['code'] in codes]
    if {b['code'] for b in selected}!=set(codes):raise ValueError('所选规范已变化，请重新选择')
    return dict(standards=selected,book_ids=[b['book_id'] for b in selected if b.get('book_id')],schema_version='1',library_sha256=hashlib.sha256(lib['DB'].read_bytes()).hexdigest())
ctx['prepare_standards'] = prepare_standards
ACTIVE_WORKERS=set();WORKER_LOCK=threading.Lock();original_worker=ctx['worker']
def tracked_worker(job,*args):
    with WORKER_LOCK:ACTIVE_WORKERS.add(job['id'])
    try:return original_worker(job,*args)
    finally:
        with WORKER_LOCK:ACTIVE_WORKERS.discard(job['id'])
ctx['worker']=tracked_worker

def desktop_state():
    running=[]
    for j in ctx['JOBS'].values():
        if j.get('status')=='running':running.append('方案审查：'+j['document']['name'])
    for t in X['OPERATIONS'].values():
        if t.get('status')=='running':running.append(t.get('phase') or '生成整改文本')
    for b in X['BATCHES'].values():
        if b.get('status')=='running':running.append('批量诊断')
    with WORKER_LOCK:
        if ACTIVE_WORKERS and not running:running.append('保存审查记录')
    return {'busy':bool(running),'running':running}

def library_request(action,data):
    if action=='catalog':return {'standards':catalog(data.get('category'))}
    if action=='search':return {'rows':search(data['text'],book_ids=[data['id']],reserve_per_book=False)}
    return lib['dispatch'](action,data)

class Handler(previous['Handler']):
    def do_GET(self):
        files={'/extended-ui.js':('界面扩展_v16.js','application/javascript'),'/amend-work.js':('整改工作区_v2.js','application/javascript'),'/':('施工方案AI审查_v17.html','text/html'),'/desktop-ui.js':('客户端界面_v1.js','application/javascript'),'/desktop.css':('客户端样式_v2.css','text/css'),'/feishu-theme.css':('飞书主题_v1.css','text/css'),'/standards-ui.js':('规范选择界面_v2.js','application/javascript')}
        if self.path in files:
            name,kind=files[self.path];return self.reply((ROOT/name).read_bytes(),ctype=kind+'; charset=utf-8')
        return super().do_GET()
    def do_POST(self):
        if self.path.startswith('/api/library/'):
            try:
                if self.headers.get('X-Prototype-Token') != ctx['TOKEN']:
                    return self.reply({'error':'请刷新窗口'},403)
                size = int(self.headers.get('Content-Length',0))
                if not 0 < size <= 85000000:
                    raise ValueError('文件过大或请求为空')
                return self.reply(library_request(self.path.split('/')[-1],json.loads(self.rfile.read(size))))
            except Exception as error:
                return self.reply({'error':str(error)},400)
        if self.path in ('/api/desktop/state','/api/desktop/cancel'):
            try:
                if self.headers.get('X-Prototype-Token')!=ctx['TOKEN']:raise ValueError('请重新打开窗口。')
                n=int(self.headers.get('Content-Length',0))
                if not 0<n<=10000:raise ValueError('请求大小不正确。')
                json.loads(self.rfile.read(n))
                if self.path.endswith('/cancel'):
                    for j in ctx['JOBS'].values():
                        if j.get('status')=='running':j['cancel']=True
                    for t in X['OPERATIONS'].values():
                        if t.get('status')=='running':t['cancel']=True
                    for b in X['BATCHES'].values():
                        if b.get('status')=='running':b['stop']=True
                return self.reply(desktop_state())
            except Exception as exc:return self.reply({'error':str(exc)},400)
        return super().do_POST()

def create_server():
    for port in range(8876,8896):
        try:
            server=LocalServer(('127.0.0.1',port),Handler);server.daemon_threads=True;return server
        except OSError:continue
    raise ValueError('本地服务端口已占用，请关闭不再使用的审查窗口。')

def main():
    server=create_server();url=f'http://127.0.0.1:{server.server_port}'
    if '--no-open' not in sys.argv:webbrowser.open(url)
    try:server.serve_forever()
    finally:server.server_close()
if __name__=='__main__':main()


