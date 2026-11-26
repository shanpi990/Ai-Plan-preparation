"""v5 服务入口。在已完成的本轮审查记录上进行离线对照。"""
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import runpy
import threading
from datetime import datetime

ROOT = Path(__file__).resolve().parent
base = runpy.run_path(str(ROOT/'图纸参数服务_v23.py'), init_globals={'_test_transport':globals().get('_test_transport')})
core = runpy.run_path(str(ROOT/'复审对照_v2.py'))
param_export = runpy.run_path(str(ROOT/'项目参数导出_v1.py'))
ctx, E, X = base['ctx'], base['E'], base['X']
desktop_state, native_selection = base['desktop_state'], base['native_selection']
dispatch_previous, report_previous = X['dispatch'], E['report']
lock = threading.RLock()


def family(name):
    stem = re.sub(r'^(?:\d{4}_)+','',Path(name).stem)
    suffix = r'[_\s-]+(?:v\d+(?:\.\d+)*|整改直接替换版|整改修订版|整改版|修订版|批注版|复审稿|修改稿)$'
    while re.search(suffix,stem,flags=re.I):
        stem = re.sub(suffix,'',stem,flags=re.I)
    return stem.casefold()


def same_run(a,b):
    keys = lambda j: {str(j[k]) for k in ('id','checkpointKey','comparisonSourceId') if j.get(k)}
    if keys(a) & keys(b):
        return True
    return bool(a.get('createdAt') and a.get('finishedAt') and
                (a['document'].get('sha256'),a['createdAt'],a['finishedAt']) ==
                (b['document'].get('sha256'),b.get('createdAt'),b.get('finishedAt')))


def overview(record):
    old = record.get('diagnosis') if isinstance(record, dict) else None
    if not isinstance(old,dict) or not isinstance(old.get('issues'),list) or not isinstance(old.get('document',{}).get('name'),str):
        raise ValueError('请选择包含审查结果的 JSON 记录。')
    if old.get('status','done') != 'done':
        raise ValueError('上一轮审查尚未完成。')
    rv = record.get('reviews',{})
    if not isinstance(rv,dict):
        raise ValueError('上一轮复核状态格式错误。')
    ids=set()
    for i in old['issues']:
        if (not isinstance(i,dict) or not isinstance(i.get('id'),str) or i['id'] in ids or
            not all(isinstance(i.get(k),str) for k in ('title','description','priority')) or not isinstance(i.get('citations'),list)):
            raise ValueError('上一轮问题清单不完整。')
        ids.add(i['id'])
    if any(not isinstance(v,dict) or not isinstance(v.get('note',''),str) for v in rv.values()):
        raise ValueError('上一轮人工复核内容格式错误。')
    return old, sum(core['is_processed'](rv.get(k,{})) for k in ids)


def list_records(job):
    rows=[]
    for path in E['RECORD_ROOT'].glob('*.json'):
        try:
            rec=json.loads(path.read_bytes())
            old,n=overview(rec)
            if same_run(old,job) or family(old['document']['name'])!=family(job['document']['name']):
                continue
            dt=datetime.fromtimestamp(path.stat().st_mtime)
            rows.append(dict(name=path.name,date=dt.isoformat(timespec='seconds'),mtime=path.stat().st_mtime_ns,
                             processed=n,total=len(old['issues'])))
        except (AttributeError,KeyError,TypeError,ValueError,OSError):
            continue
    return sorted(rows,key=lambda r:(r['mtime'],r['name']),reverse=True)


def plan_document(job, snapshot):
    expected=job['document']
    sha=expected.get('sha256')
    refs=[c['paragraph'] for i in job['issues'] for c in core['plan_refs'](i)]
    def complete(doc):
        if not isinstance(doc,dict) or doc.get('sha256')!=sha:
            return False
        rows=doc.get('rows') or []
        if not rows or (expected.get('count') and len(rows)!=expected['count']):
            return False
        if any(not isinstance(r,dict) or r.get('id')!=i or not isinstance(r.get('text'),str) for i,r in enumerate(rows,1)):
            return False
        return all(isinstance(p,int) and 1<=p<=len(rows) for p in refs)
    for doc in (snapshot,ctx['DOCS'].get(sha)):
        if complete(doc):
            return doc
    name=Path(expected['name']).name
    refroot=(ROOT.parent/'参考文件').resolve()
    raw=ctx['RAW_DOCS'].get(sha)
    if not raw and refroot.is_dir():
        for path in refroot.rglob('*'):
            if path.name.casefold()==name.casefold() and path.is_file() and path.resolve().is_relative_to(refroot):
                data=path.read_bytes()
                if hashlib.sha256(data).hexdigest()==sha:
                    raw=data
                    break
    if raw and hashlib.sha256(raw).hexdigest()==sha:
        source=ctx['I']['bind_source'](job,0,name,raw,ROOT,E)
        if complete(source):
            return source
    raise ValueError('方案「'+name+'」的段落快照不完整，请把同一份原文件放入参考文件目录后重试。')


def plan_rows(job,snapshot):
    return plan_document(job,snapshot)['rows']


def export_parameters(context, jid):
    job = context['JOBS'].get(jid)
    if not job or not job.get('parameters'):
        raise ValueError('当前审查记录没有可导出的项目参数。')
    docs = context['JOB_DOCS'].get(jid) or []
    document = plan_document(job, docs[0] if docs else None)
    return param_export['build'](job, document)


def save_parameters_as(window, jid):
    from webview import FileDialog
    result = export_parameters(ctx, jid)
    if not result['exported']:
        return dict(exported=0, skipped=result['skipped'])
    folder = E['RESULT_ROOT']
    folder.mkdir(parents=True, exist_ok=True)
    selection = window.create_file_dialog(FileDialog.SAVE, directory=str(folder),
                                          save_filename=result['filename'], file_types=('项目参数 (*.json)',))
    if not selection:
        return None
    return param_export['save'](result, Path(selection[0]), E['RUNTIME']['atomic_json'])


def local_path(name):
    folder=E['RECORD_ROOT'].resolve()
    path=(folder/name).resolve()
    if path.parent!=folder or path.suffix.lower()!='.json' or not path.is_file():
        raise ValueError('未找到所选审查记录。')
    return path


def dispatch(context,path,data):
    action=path.rsplit('/',1)[-1]
    if action in ('parameters-export', 'parameters-save'):
        result = export_parameters(context, data.get('id'))
        if action == 'parameters-export':
            return result
        return param_export['save'](result, E['RESULT_ROOT']/result['filename'], E['RUNTIME']['atomic_json'])
    if not action.startswith('round-'):
        return dispatch_previous(context,path,data)
    job=context['JOBS'].get(data.get('id'))
    if not job or job.get('status')!='done':
        raise ValueError('请先打开已完成的本轮审查记录。')
    if action=='round-list':
        return dict(records=list_records(job))
    with lock:
        state=job.get('roundComparison')
        if data.get('revision',0)!=(state or {}).get('revision',0):
            raise ValueError('对照结果已更新，请重新打开当前审查记录。')
        reviews=context['active_reviews'](job,data.get('reviews',context['REVIEWS'].get(job['id'],{})))
        if action=='round-compare':
            name=Path(data['name']).name
            raw=base64.b64decode(data['raw'],validate=True) if 'raw' in data else local_path(name).read_bytes()
            previous=json.loads(raw)
            old,processed=overview(previous)
            if same_run(old,job):
                raise ValueError('这份文件就是本轮记录，请选择上一轮审查。')
            digest=hashlib.sha256(raw).hexdigest()
            if state and state['sha256']==digest and not state.get('weakNeedsSource'):
                return dict(state=state,reviews=reviews)
            if not processed and not data.get('allowUnreviewed'):
                return dict(warning=core['UNREVIEWED'],sha256=digest)
            if data.get('expectedSha') and data['expectedSha']!=digest:
                raise ValueError('上一轮文件已经改变，请重新选择。')
            olddocs=previous.get('sourceDocuments') or []
            oldrows=plan_rows(old,olddocs[0] if olddocs else None)
            docs=context['JOB_DOCS'].get(job['id']) or []
            newrows=plan_rows(job,docs[0] if docs else None)
            candidate=core['build'](previous,job,oldrows,newrows,name,digest)
            candidate['revision']=(state or {}).get('revision',0)
            if state and state['sha256']==digest:
                for key in ('manual','inherited','decisions','overrides'):
                    if key in state:
                        candidate[key]=copy.deepcopy(state[key])
            else:
                reviews=core['remove_inherited'](state,reviews)
        elif action=='round-decide' and state:
            candidate=copy.deepcopy(state)
            core['decide'](candidate,data.get('previous'),data.get('current'),data.get('outcome'))
        elif action=='round-adjust' and state:
            candidate=copy.deepcopy(state)
            core['adjust'](candidate,data.get('previous'),data.get('current'),job['issues'])
        else:
            raise ValueError('请先选定上轮审查记录。')
        reviews=core['evaluate'](candidate,job['issues'],reviews)
        dest=E['RECORD_ROOT']/('复审对照记录_'+job['id']+'_v1.json')
        rt=E['RUNTIME']
        rt['atomic_json'](dest,rt['snapshot'](dict(job,roundComparison=candidate),reviews,context['JOB_DOCS'][job['id']]))
        job['roundComparison']=candidate
        context['REVIEWS'][job['id']]=reviews
        return dict(state=candidate,reviews=reviews,saved=dest.name)


def report(job,*args,**kwargs):
    path=report_previous(job,*args,**kwargs)
    if job.get('roundComparison'):
        with Path(path).open('a',encoding='utf8') as f:
            f.write(core['markdown'](job['roundComparison'],job['issues']))
    return path


original_import=ctx['I']['import_record']
def import_record(record,*args,**kwargs):
    # 旧导入器会先核对引文。段落不全的快照须在这一步前补齐。
    rawjob=record.get('diagnosis',{}) if isinstance(record,dict) else {}
    snapshots=record.get('sourceDocuments') if isinstance(record,dict) else None
    first=snapshots[0] if isinstance(snapshots,list) and snapshots else None
    if isinstance(first,dict) and isinstance(rawjob.get('document'),dict):
        rows=first.get('rows')
        expected_count=rawjob['document'].get('count')
        if isinstance(rows,list) and expected_count and len(rows)!=expected_count:
            source=plan_document(rawjob,first)
            record=dict(record,sourceDocuments=[source,*snapshots[1:]])
    job,reviews,docs=original_import(record,*args,**kwargs)
    job['comparisonSourceId']=record['diagnosis'].get('comparisonSourceId') or record['diagnosis'].get('id')
    s=job.get('roundComparison')
    if s is not None:
        if (not isinstance(s,dict) or s.get('version') not in (1,2) or not isinstance(s.get('previous'),list)
                or set(s.get('newMarks',{}))!={i['id'] for i in job['issues']}):
            raise ValueError('复审对照记录与本轮问题清单不一致。')
        if s['version']==1:
            try:
                rows=plan_rows(job,docs[0] if docs else None)
            except ValueError:
                rows=[]
                s['weakNeedsSource']=True
            core['upgrade'](s,job['issues'],rows)
            reviews=core['evaluate'](s,job['issues'],reviews)
    return job,reviews,docs


ctx['I']['import_record']=import_record
X['dispatch']=dispatch
E['report']=report


class Handler(base['Handler']):
    def do_GET(self):
        if self.path=='/submission.js':
            scripts=['编审联动界面_v1.js','图纸参数界面_v2.js','复审对照界面_v2.js','参数导出界面_v1.js']
            return self.reply(b'\n'.join((ROOT/name).read_bytes() for name in scripts),ctype='application/javascript; charset=utf-8')
        if self.path=='/round-compare.css':
            return self.reply((ROOT/'复审对照样式_v2.css').read_bytes(),ctype='text/css; charset=utf-8')
        return super().do_GET()


def create_server():
    server_type=base['v22']['v21']['v20']['LocalServer']
    for port in range(8876,8896):
        try:
            server=server_type(('127.0.0.1',port),Handler)
            server.daemon_threads=True
            return server
        except OSError:
            continue
    raise ValueError('本地服务端口已占用。')


if __name__=='__main__':
    with create_server() as server:
        server.serve_forever()
