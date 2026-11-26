"""图纸工作区。图纸和识别页按内容缓存，方案按指纹分别保存候选和确认快照。"""
import base64
import copy
import hashlib
import io
import json
import math
import os
import re
import runpy
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ZONE=runpy.run_path(str(Path(__file__).with_name('图纸分区选参_v1.py')))
ORIGIN = '审查端图纸识别'
TYPES = ('设计总说明','岩土工程勘察报告')
FLAGS = getattr(subprocess,'CREATE_NO_WINDOW',0)
def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid4().hex+'.partial')
    temp.write_bytes(data)
    temp.replace(path)

def stamp():
    return datetime.now().isoformat(timespec='seconds')

def verified(kind):
    return '深基坑' in kind or 'SMW' in kind.upper()

def ocr_workers(configured):
    if configured in (None,'自动'):
        return max(1,min(6,(os.cpu_count() or 1)-2))
    if type(configured) is not int or not 1<=configured<=61:
        raise ValueError('读图并行数请设为“自动”或 1～61 的整数')
    return configured

def candidate_source(c,docs):
    boxes=[line['bbox'] for line in c['evidence'] if line.get('bbox')]
    return dict(doc=docs[c['docId']]['name'],sha256=c['docId'],page=c['page'],
                bbox=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)] if boxes else None)

def group_key(c):
    return (c.get('zone',''),c['name'],c.get('drawingScope',c.get('phase','')))

def conflicts_for(candidates,extractor):
    # OCR 摘句常带字段名和单位。仅在同分区、同字段、同工况内对比单一数值或范围。
    import unicodedata
    groups={}
    aliases={'开挖深度':('基坑开挖深度','基坑深度','开挖深度'),
             '基坑安全等级':('基坑安全等级','安全等级'),'支撑道数':('设置','设')}
    for row in candidates:
        zone,name,phase=key=group_key(row)
        value=unicodedata.normalize('NFKC',row['value']).strip()
        for prefix in (zone,phase):
            if prefix and value.startswith(prefix):value=value[len(prefix):].lstrip(' :：')
        for prefix in aliases.get(name,(name,)):
            if value.startswith(prefix):value=value[len(prefix):].lstrip(' :：');break
        value=re.sub(r'^(?:约为|为|约|共|取)\s*','',value).strip()
        value=value.rstrip('。；;').replace('～','~')
        unit=row.get('unit','').strip()
        suffix=re.fullmatch(r'(.*?)(mm|cm|m|%|道|级)',value,re.I)
        if suffix:
            value,unit=suffix.group(1).strip(),suffix.group(2).lower()
        if name in ('支撑道数','基坑安全等级','环境保护等级'):
            value={'一':'1','二':'2','三':'3','四':'4','五':'5','六':'6'}.get(value,value)
        groups.setdefault(key,[]).append(dict(row,value=value,unit=unit))
    return [key for key,rows in groups.items() if extractor['numeric_conflicts'](rows)]

def coordinate_rows(rows,cast):
    result=copy.deepcopy(rows)
    for p in result:
        source=p.get('source') or {}
        if isinstance(source.get('bbox'),list):
            source['bbox']=[cast(v) for v in source['bbox']]
    return result

def integer_coordinate(v):
    return int(v) if isinstance(v,float) and v.is_integer() else v

def parameter_pack(snapshot):
    rows=[p for p in snapshot['parameters'] if p.get('confirmed') is True]
    return dict(matched=True,origin=ORIGIN,pending=[],parameters=copy.deepcopy(rows),packSha256=digest(encoded(coordinate_rows(rows,integer_coordinate))))


def restore_pack(snapshot,stored):
    p=parameter_pack(snapshot)
    if p['parameters']!=stored.get('parameters'):raise ValueError('审查依据与已确认图纸参数不一致')
    rows=p['parameters']
    # 旧指纹以 OCR 输出的浮点坐标序列化。浏览器会将 10.0 回传为 10。
    valid={p['packSha256'],digest(encoded(rows)),digest(encoded(coordinate_rows(rows,float)))}
    if stored.get('packSha256') not in valid:raise ValueError('记录中的图纸参数指纹不符')
    return p

def restore_merged_links(job):
    from collections import defaultdict
    ancestors=defaultdict(set)
    for event in job.get('mergeAudit',[]):
        ids=event.get('issueIds') or []
        if not event.get('skipped') and len(ids)>1:
            ancestors[event.get('keptId') or ids[0]].update(ids)
    reviewed={i['id']:i for i in (job.get('checkpoint') or {}).get('reviewed',[]) if i.get('id')}
    params={p['id']:p for p in job['bianshen']['parameters']}
    for issue in job.get('issues',[]):
        keep=issue.get('id')
        if keep not in ancestors:continue
        mentioned=set(re.findall(r'(?<![A-Za-z0-9])CS-[0-9]+', ' '.join(str(issue.get(k,'')) for k in ('title','description','suggestion'))))
        existing={b['ref'] for b in issue.get('parameterBasis',[])}
        pending=[keep];seen=set()
        while pending:
            member=pending.pop()
            if member in seen:continue
            seen.add(member);pending.extend(sorted(ancestors.get(member,())))
            for b in reviewed.get(member,{}).get('parameterBasis',[]):
                ref=b['ref'];p=params.get(ref)
                if ref in mentioned-existing and p and b.get('origin')==ORIGIN and b.get('drawingSource')==p.get('source') and b.get('value')==p['value']:
                    issue.setdefault('parameterBasis',[]).append(copy.deepcopy(b));existing.add(ref)

class Workspace:
    def __init__(self,root,cache,E):
        self.engine=Path(root)/'读图引擎'
        self.cache=Path(cache)
        self.E=E
        self.pool=runpy.run_path(str(Path(root)/'并行审查调度_v1.py'))['ReviewPool']
        self.state={}
        self.operations={}
        self.lock=threading.RLock()
        self.health=dict(ready=False,message='正在自检读图引擎')
        self.extractor={}
        self._probe=threading.Thread(target=self.probe,daemon=True)
        self._probe.start()

    def command(self,*args):
        return [str(self.engine/'运行库/python.exe'),'-B','-X','utf8',str(self.engine/'读图引擎.py'),*map(str,args)]

    def probe(self):
        try:
            self.extractor=runpy.run_path(str(self.engine/'图纸参数提取.py'))
            result=subprocess.run(self.command('selftest'),capture_output=True,encoding='utf8',timeout=90,creationflags=FLAGS)
            if result.returncode:raise ValueError(result.stdout[-400:] or result.stderr[-400:])
            self.health=dict(ready=True,message='读图引擎就绪')
        except Exception as exc:self.health=dict(ready=False,message='读图引擎不可用：'+str(exc))

    def folder(self,sha):
        if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('文件指纹无效')
        return self.cache/sha[:12]

    def draft_path(self,sha):
        self.folder(sha)
        return self.cache/'方案'/sha/'图纸参数.json'

    def get(self,sha):
        with self.lock:
            if sha not in self.state:
                path=self.draft_path(sha)
                self.state[sha]=json.loads(path.read_bytes()) if path.is_file() else dict(documents=[],candidates=[],parameters=[],aiLog=[],revision=0,kind='',readSeconds=0,extractSeconds=0)
                ZONE['normalize'](self.state[sha])
            return self.state[sha]

    def save(self,sha):
        s=self.get(sha);s['revision']+=1
        write(self.draft_path(sha),encoded(s))

    def invalidate(self,s):
        s.update(parameters=[],reviewer='',confirmedAt='')

    def busy(self,sha):
        return self.operations.get(sha,{}).get('status')=='running'

    def check_edit(self,sha,data):
        if self.busy(sha):raise ValueError('读图或提取正在运行')
        s=self.get(sha)
        if data.get('revision')!=s['revision']:raise ValueError('候选表已更新，请刷新后确认')
        return s

    def status(self,sha):
        with self.lock:
            s=copy.deepcopy(self.get(sha))
            op={k:v for k,v in self.operations.get(sha,{}).items() if k not in ('process','thread','started','cancel')}
            if op and self.busy(sha):op['elapsed']=int(time.monotonic()-self.operations[sha]['started'])
            elif op:op['elapsed']=round(s['readSeconds']+s['extractSeconds'])
            conflicts=conflicts_for(s['candidates'],self.extractor) if self.extractor else []
            return dict(draft=s,progress=op,engine=self.health,conflicts=sorted(conflicts),packSha=parameter_pack(s)["packSha256"] if s["parameters"] else "")

    def upload(self,sha,data):
        from pypdf import PdfReader
        name=Path(data['name']).name
        kind=data.get('type')
        if Path(name).suffix.lower()!='.pdf' or kind not in TYPES:raise ValueError('请选择 PDF 和资料类型')
        raw=base64.b64decode(data['raw'],validate=True)
        if not 0<len(raw)<=60_000_000:raise ValueError('PDF 需在 60 MB 以内')
        pdf=PdfReader(io.BytesIO(raw));count=len(pdf.pages)
        if pdf.is_encrypted or not count:raise ValueError('请选择可读取的未加密 PDF')
        key=digest(raw)
        with self.lock:
            s=self.check_edit(sha,data)
            path=self.folder(key)/'原图.pdf'
            if not path.exists():write(path,raw)
            elif digest(path.read_bytes())!=key:raise ValueError('缓存中的图纸指纹不符')
            doc=next((d for d in s['documents'] if d['sha256']==key),None)
            if doc and doc['type']==kind:return self.status(sha)
            if doc:doc['type']=kind
            else:s['documents'].append(dict(name=name,sha256=key,pages=count,type=kind))
            self.clear_results(s,key)
            self.save(sha);return self.status(sha)

    def clear_results(self,s,key=None):
        s['extractionComplete']=False
        for field in ('candidates','aiLog'):
            s[field]=[r for r in s[field] if key and r['docId']!=key]
        self.invalidate(s)

    def remove(self,sha,data):
        with self.lock:
            s=self.check_edit(sha,data)
            s['documents']=[d for d in s['documents'] if d['sha256']!=data['docId']]
            self.clear_results(s,data['docId']);self.save(sha)
            return self.status(sha)

    def start(self,sha,data,cfg):
        with self.lock:
            s=self.check_edit(sha,data)
            if not self.health['ready']:raise ValueError(self.health['message'])
            if not s['documents']:raise ValueError('请先选择图纸')
            kind=str(data['kind'])
            if s['kind']!=kind:self.clear_results(s)
            s.update(kind=kind,fieldsVerified=verified(kind),extractionComplete=False)
            self.invalidate(s);self.save(sha)
            op=dict(status='running',phase='读图',cancel=False,started=time.monotonic(),done=0,total=sum(d['pages'] for d in s['documents']))
            self.operations[sha]=op
            threading.Thread(target=self.work,args=(sha,s,op,cfg),daemon=True).start()
            return self.status(sha)

    def cancel(self,sha):
        with self.lock:
            op=self.operations.get(sha,{})
            if self.busy(sha):
                op['cancel']=True
                child=op.get('process')
                if child and child.poll() is None:
                    subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],creationflags=FLAGS,capture_output=True)
            return self.status(sha)

    def work(self,sha,s,op,cfg):
        start=time.monotonic()
        try:
            work=[];done=0
            documents=s['documents']
            missing=[]
            for doc in documents:
                folder=self.folder(doc['sha256'])
                pages=[n for n in range(1,doc['pages']+1) if not (folder/f'page_{n}.json').is_file()]
                if pages:missing.append((folder,pages))
            if missing:
                settings=self.engine.parent.parent/'配置文件/审查运行配置_v1.json'
                options=json.loads(settings.read_bytes()) if settings.is_file() else {}
                workers=ocr_workers(cfg.get('ocrParallelism',options.get('读图并行数')))
                args=self.command('ocr','--parallel',workers)
                for folder,pages in missing:
                    args.extend(['--pdf',str(folder/'原图.pdf'),'--out',str(folder),'--document-pages',','.join(map(str,pages))])
                with self.lock:
                    if op['cancel']:raise ValueError('已取消')
                    proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',errors='replace',creationflags=FLAGS)
                    op.update(process=proc,ocrWorkers=workers,ocrDocuments=len(missing))
                done=sum(d['pages'] for d in documents)-sum(len(pages) for _,pages in missing)
                error=''
                with proc:
                    for line in proc.stdout:
                        try:ev=json.loads(line)
                        except ValueError:continue
                        with self.lock:
                            if ev.get('event')=='progress':
                                op.update(tile=ev['tile'],tileCount=ev['tileCount'],page=done+1)
                            elif ev.get('event')=='page':
                                done+=1;op['done']=done
                            elif ev.get('event')=='error':error=ev.get('message','')
                    if proc.wait():raise ValueError(error or '本次读图已中断')
            done=0
            for doc in documents:
                if op['cancel']:raise ValueError('已取消')
                folder=self.folder(doc['sha256'])
                for n in range(1,doc['pages']+1):
                    pg=json.loads((folder/f'page_{n}.json').read_bytes())
                    lines=pg['lines']
                    for a,b in self.extractor['batches'](lines):
                        work.append(dict(doc=doc,page=n,lines=lines,a=a,b=b,visual=False,record=dict(batch=len(work)+1),adjustments=[]))
                    done+=1
                with self.lock:op.update(done=done,page=done)
            with self.lock:
                s['readSeconds']+=round(time.monotonic()-start,2)
                op.update(phase='提取',done=0,total=len(work),rejected=sum(x['rejected'] for x in s['aiLog']))
                self.save(sha)
            start=time.monotonic()
            self.extract(sha,s,op,work,cfg)
            with self.lock:
                if not op['cancel'] and not work:raise ValueError('没有读到可提取的文字行')
                op['status']='cancelled' if op['cancel'] else 'done'
                s['extractionComplete']=not op['cancel']
                ZONE['normalize'](s)
        except Exception as exc:
            with self.lock:op.update(status='cancelled' if op['cancel'] else 'failed',error=str(exc))
        finally:
            with self.lock:
                if op['phase']=='提取':s['extractSeconds']+=round(time.monotonic()-start,2)
                op.pop('process',None);self.save(sha)

    def extract(self,sha,s,op,items,cfg):
        seen={l['key'] for l in s['aiLog']}
        pending=[]
        for w in items:
            d=w['doc'];fields=self.extractor['FIELDS_BY_TYPE'][d['type']] if s['fieldsVerified'] else self.extractor['GENERIC_FIELDS']
            prompt=self.extractor['build_prompt'](d['name'],d['type'],w['lines'],w['a'],w['b'],fields)
            w.update(key=digest(encoded([d['sha256'],w['page'],cfg['model'],prompt])),fields=fields,prompt=prompt)
            if w['key'] not in seen:pending.append(w)
        op['done']=len(items)-len(pending)
        def query(w,rate):
            body=dict(model=cfg['model'],messages=[dict(role='system',content='按字段表提取，返回 JSON 对象。'),dict(role='user',content=w['prompt'])],response_format=dict(type='json_object'),max_tokens=65536)
            if cfg['model'].startswith('deepseek'):
                body['thinking']=dict(type='enabled' if cfg.get('thinking',True) else 'disabled')
                if cfg.get('thinking',True):body['reasoning_effort']='low'
            raw=self.E['request_api'](dict(cfg,_reviewPayload={'任务类型':'图纸参数提取'},_rateEvent=rate,_cancelled=lambda:op['cancel']),'/chat/completions',body)
            w['usage']=self.E['token_usage'](raw)
            w['finishReason']=(raw.get('choices') or [{}])[0].get('finish_reason','')
            obj=self.E['parse_model_reply'](raw,{})
            if not isinstance(obj.get('items'),list):raise ValueError('模型没有返回候选表')
            d=w['doc']
            rows,bad=self.extractor['validate_items'](obj['items'],w['lines'],w['a'],w['b'],w['fields'],d['sha256'],d['name'],w['page'])
            log=dict(docId=d['sha256'],page=w['page'],key=w['key'],lines=[w['a'],w['b']-1],accepted=len(rows),rejected=len(bad),usage=w['usage'],finishReason=w['finishReason'])
            return rows,log
        errors=[]
        def commit(w):
            if 'error' in w:
                with self.lock:
                    s.setdefault('aiFailures',[]).append(dict(key=w['key'],docId=w['doc']['sha256'],page=w['page'],error=str(w['error']),finishReason=w.get('finishReason',''),usage=w.get('usage',{})))
                    self.save(sha)
                errors.append(w['error']);return
            rows,log=w['result'];log['seconds']=w['record']['requestSeconds'];d=w['doc']
            with self.lock:
                existing={c['id'] for c in s['candidates']}
                for row in rows:
                    key=digest(encoded([row['docId'],row['page'],row['zone'],row.get('phase'),row['name'],row['value'],row['unit']]))
                    if key not in existing:
                        s['candidates'].append(dict(row,id=key));existing.add(key)
                s['aiLog'].append(log);op['rejected']+=log['rejected'];self.save(sha)
        pool=self.pool(max(1,min(10,int(cfg.get('parallelism',4)))),1,op)
        cached=len(items)-len(pending)
        def progress(completed,limit):
            with self.lock:op['done']=cached+completed
        try:pool.execute(pending,query,commit,commit,progress)
        finally:pool.close()
        if errors:raise errors[0]

    def confirm(self,sha,data):
        with self.lock:
            s=self.check_edit(sha,data)
            if not s.get('extractionComplete') or self.operations.get(sha,{}).get('status') in ('failed','cancelled'):raise ValueError('请先续跑完成提取')
            person=str(data.get('reviewer','')).strip()
            if not person:raise ValueError('请填写确认人')
            selected=data.get('selected',[]);edits=data.get('edits',{});scopes=data.get('scopes',{})
            if not isinstance(scopes,dict) or any(not isinstance(v,str) or len(v.strip())>80 for v in scopes.values()):raise ValueError('请填写简短的适用工况')
            rows={r['id']:r for r in s['candidates']}
            if not isinstance(selected,list) or not selected or any(i not in rows for i in selected):raise ValueError('请勾选有效候选')
            conflicts=set(map(tuple,conflicts_for(s['candidates'],self.extractor)))
            for key in conflicts:
                ids=[i for i in set(selected) if group_key(rows[i])==key]
                if len(ids)>1:
                    import unicodedata
                    named={''.join(unicodedata.normalize('NFKC',scopes.get(i,'')).casefold().split()) for i in ids}
                    if '' in named or len(named)!=len(ids):raise ValueError('同一工况只能选一个值；若均适用，请为每一条填写不同的工况')
                if data.get('all') is True and not ids:raise ValueError('请为冲突字段人工选定一个值')
                if not data.get('all') and not data.get('partial') and ids:raise ValueError('本次只确认无冲突项')
            params=[];docs={d['sha256']:d for d in s['documents']};ids=set(selected)
            for n,(key,c) in enumerate(rows.items(),1):
                if key not in ids:continue
                value=str(edits.get(key,c['value'])).strip()
                if not value:raise ValueError('确认值不能为空')
                scope=scopes.get(key,c.get('phase','')).strip()
                params.append(dict(id=f'CS-{n:03d}',candidateId=key,label=c['name'],zone=c['zone'],drawingScope=scope,value=value,unit=c['unit'],source=candidate_source(c,docs),origin='人工修改' if value!=c['value'] or scope!=c.get('phase','') else ORIGIN,confirmed=True))
            s.update(parameters=params,reviewer=person,confirmedAt=stamp())
            ZONE['normalize'](s)
            self.save(sha)
            return copy.deepcopy(s)

    def crop(self,source):
        sha=source['sha256'];folder=self.folder(sha);pdf=folder/'原图.pdf'
        if not pdf.is_file():raise ValueError('本机缺少对应原图，请重新上传同一份 PDF')
        box=source.get('bbox');page=source.get('page')
        if not isinstance(box,list) or len(box)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in box) or type(page)!=int:raise ValueError('该来源缺少可定位的页码或坐标')
        target=folder/('crop_'+digest(encoded([page,box]))[:20]+'.png')
        if not target.is_file():
            p=subprocess.run(self.command('crop','--pdf',pdf,'--page',page,'--bbox',','.join(map(str,box)),'--out',target),capture_output=True,encoding='utf8',creationflags=FLAGS,timeout=60)
            if p.returncode:raise ValueError('原图裁切失败：'+p.stdout[-300:])
        return dict(image='data:image/png;base64,'+base64.b64encode(target.read_bytes()).decode())

