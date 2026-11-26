"""客户端 v21。复用 v20 的初审、回查、汇总、导出和断点。"""
import base64
from collections import OrderedDict
import json
from pathlib import Path
import runpy
import sys
import webbrowser
from uuid import uuid4

ROOT=Path(__file__).resolve().parent
v20=runpy.run_path(str(ROOT/'server_v20.py'),init_globals={'_test_transport':globals().get('_test_transport')})
ctx=v20['ctx']
X=v20['X']
E=ctx['E']
desktop_state=v20['desktop_state']
F=runpy.run_path(str(ROOT/'重点关注扩展_v1.py'))
lib=F['Library'](E['CONFIG_ROOT'])
ctx['prepare_focus']=lib.compose
E['validate_result'].__globals__['finalize_focus']=F['finalize']
drafts=OrderedDict()


# 同一原始记录的导入副本读取本机已有星标，同时保留随记录带来的收藏信息。
original_import=ctx['I']['import_record']
def import_with_stars(*args,**kwargs):
    job,reviews,docs=original_import(*args,**kwargs)
    index={tuple(row['sourceKey']):row['id'] for row in lib.read('favorites')['items']}
    for issue in job['issues']:
        fid=index.get(tuple(lib.source_key(job,issue)))
        if fid:issue['favoriteId']=fid
    return job,reviews,docs
ctx['I']['import_record']=import_with_stars


def state():
    with F['LOCK']:
        return dict(owners=lib.read('owners')['items'],favorites=lib.read('favorites')['items'])


def remember(draft):
    with F['LOCK']:
        key=uuid4().hex
        drafts[key]=draft
        if len(drafts)>20:drafts.popitem(last=False)
        return dict(draft=draft,key=key)


def persist(job):
    name='问题收藏记录_'+job['id']+'_v1.json'
    path=E['RECORD_ROOT']/name
    rt=E['RUNTIME']
    rt['atomic_json'](path,rt['snapshot'](job,ctx['REVIEWS'].get(job['id'],{}),ctx['JOB_DOCS'].get(job['id'],[])))
    job['favoriteRecordPath']=str(path)
    return path


def dispatch(action,data):
    if action=='state':return state()
    if action=='preview':
        return lib.compose(data['schemeType'],E['clean_focus'](data.get('focus',[])))
    if action=='import':
        raw=base64.b64decode(data['raw'],validate=True)
        src=F['read_source'](data['name'],raw)
        existing=next((b for b in lib.read('owners')['items'] if b['sha256']==src['sha256']),None)
        if existing and not data.get('overwrite'):return dict(duplicate=True,sha256=src['sha256'])
        cfg=E['resolve_config']({})
        types=ctx['TYPES']['load_library'](E['CONFIG_ROOT'],[])['categories']
        return remember(F['model_extract'](E,cfg,src,[t['name'] for t in types]))
    if action=='edit-book':
        book=next((b for b in lib.read('owners')['items'] if b['sha256']==data['sha256']),None)
        if not book:raise ValueError('文件记录已变化，请刷新。')
        return remember(book)
    if action=='save-book':
        with F['LOCK']:
            draft=drafts.get(data['key'])
            if not draft:raise ValueError('校对已过期，请重新打开文件。')
            book=lib.save_book(draft,data['items'],data['docNo'],data.get('overwrite') is True)
            drafts.pop(data['key'])
            return dict(book=book)
    with F['LOCK']:
        if action=='collect':
            job=ctx['JOBS'][data['id']]
            if job.get('status')=='running':raise ValueError('请等待审查结束。')
            issue=next((i for i in job['issues'] if i['id']==data['issueId']),None)
            if not issue:raise ValueError('请选择当前记录的问题。')
            if data['enabled']:
                row=lib.collect(job,issue,str(data.get('note','')))
                issue['favoriteId']=row['id']
            else:
                fid=issue.pop('favoriteId',None)
                local=next((r for r in lib.read('favorites')['items'] if r['id']==fid and
                            r['sourceKey']==lib.source_key(job,issue)),None)
                if local:lib.edit_favorite(fid,{},True)
            return dict(favoriteId=issue.get('favoriteId'),saved=str(persist(job)))
        if action=='favorite':
            fid=data['favoriteId']
            remove=data.get('remove') is True
            row=next((r for r in lib.read('favorites')['items'] if r['id']==fid),None)
            lib.edit_favorite(fid,data,remove)
            if remove:
                for job in ctx['JOBS'].values():
                    if job.get('status')=='running':continue
                    changed=False
                    for issue in job['issues']:
                        if row and issue.get('favoriteId')==fid and row['sourceKey']==lib.source_key(job,issue):
                            issue.pop('favoriteId')
                            changed=True
                    if changed:persist(job)
            return state()
    raise ValueError('未知操作。')


class Handler(v20['Handler']):
    def reply(self,obj,status=200,ctype='application/json; charset=utf-8'):
        if isinstance(obj,dict) and isinstance(obj.get('error'),str):
            # 返回相对于项目的位置，保留报错文件及具体错误原因。
            message=obj['error']
            for prefix in (str(ROOT.parent)+'\\',ROOT.parent.as_posix()+'/'):
                message=message.replace(prefix,'').replace(prefix.replace('\\','\\\\'),'')
            obj=dict(obj,error=message)
        return super().reply(obj,status,ctype)

    def do_GET(self):
        if self.path=='/':
            html=v20['page_bytes']().replace(b'</body>',b'<script src="/focus-extension.js"></script></body>')
            return self.reply(html,ctype='text/html; charset=utf-8')
        if self.path=='/focus-extension.js':
            return self.reply((ROOT/'重点关注界面_v1.js').read_bytes(),ctype='application/javascript; charset=utf-8')
        return super().do_GET()

    def do_POST(self):
        if not self.path.startswith('/api/focus-ext/'):return super().do_POST()
        if self.headers.get('X-Prototype-Token')!=ctx['TOKEN']:return self.reply({'error':'请刷新窗口。'},403)
        try:
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<=85_000_000:raise ValueError('请求为空或文件过大。')
            return self.reply(dispatch(self.path.rsplit('/',1)[1],json.loads(self.rfile.read(size))))
        except Exception as exc:return self.reply({'error':str(exc)},400)


def create_server():
    for port in range(8876,8896):
        try:
            server=v20['LocalServer'](('127.0.0.1',port),Handler)
            server.daemon_threads=True
            return server
        except OSError:continue
    raise ValueError('本地服务端口已占用。')


if __name__=='__main__':
    with create_server() as server:
        if '--no-open' not in sys.argv:webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        server.serve_forever()

