"""深基坑AI初审本地服务。"""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import json,runpy,secrets,hashlib,base64,threading,webbrowser,sys,datetime
ROOT=Path(__file__).parent
E=runpy.run_path(str(ROOT/'1120_AI诊断引擎_v11.py'))
I=runpy.run_path(str(ROOT/'1120_结果导入_v11.py'))
TOKEN=secrets.token_urlsafe(32);DOCS={};JOBS={};JOB_DOCS={};REVIEWS={};RAW_DOCS={}
TYPES=runpy.run_path(str(ROOT/'1109_方案类别_v9.py'))
ACTIVE_ID=None

def meta(doc):return {k:v for k,v in doc.items() if k!='rows'}|{'count':len(doc['rows'])}

def job_list():
    return [{'id':j['id'],'name':j['document']['name'],'status':j['status'],'createdAt':j.get('createdAt',''),'schemeType':j.get('schemeType','通用')} for j in JOBS.values()]

def linked_document(job):
    docs=JOB_DOCS.get(job['id'],[])
    return meta(docs[0]) if docs and docs[0] is not None else None

FLOW=runpy.run_path(str(ROOT/'1120_全篇复核流程_v10.py'))

def active_reviews(job,reviews):
    result={}
    for item in job['issues']:
        origins=[item['id']]+item.get('mergedFrom',[])
        candidates=set(item.get('candidateIds',[]))
        origins += [x['id'] for x in job.get('candidates',[]) if x.get('candidateId') in candidates]
        chosen=[reviews[k] for k in dict.fromkeys(origins) if k in reviews]
        if chosen:result[item['id']]=chosen[0]
    return result

def save_checkpoint(job):
    job.setdefault('checkpointKey',job['id'])
    path=E['RUNTIME']['checkpoint_path'](E['RECORD_ROOT'],job)
    job['checkpointPath']=str(path)
    E['RUNTIME']['atomic_json'](path,E['RUNTIME']['snapshot'](job,active_reviews(job,REVIEWS.get(job['id'],{})),JOB_DOCS[job['id']]))

def worker(job,doc,design,cfg,focus):
    try:E['run_diagnosis'](job,doc,design,cfg,focus,on_checkpoint=lambda:save_checkpoint(job))
    except Exception as exc:job.update(status='failed',stage='诊断暂停，已完成条目保留',error=str(exc))
    REVIEWS[job['id']]=active_reviews(job,REVIEWS.get(job['id'],{}))
    try:
        if job['status']!='done':
            save_checkpoint(job)
            job['savedPath']=job['checkpointPath']
        else:
            job['savedPath']=E['report'](job,REVIEWS[job['id']],JOB_DOCS.get(job['id']),finish_checkpoint=True)
    except Exception:job['saveError']='自动保存失败，请使用“保存复核记录”重试。'

def resume_state(job):
    if job['status']=='running':raise ValueError('当前诊断正在运行。')
    docs=JOB_DOCS[job['id']]
    if any(d is None for d in docs):raise ValueError('请先点击“关联原文”，补齐方案和设计资料后续审。')
    cp=FLOW['prepare_resume'](E,job,docs[0],docs[1:])
    return docs,cp

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,obj,status=200,ctype='application/json; charset=utf-8'):
        raw=obj if isinstance(obj,bytes) else json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/':return self.reply((ROOT/'1109_施工方案AI审查_v11.html').read_bytes(),ctype='text/html; charset=utf-8')
        if self.path=='/api/bootstrap':
            try:config=E['public_config'](E['load_config']());error=''
            except ValueError as e:config=E['public_config'](E['DEFAULT']);error=str(e)
            return self.reply(dict(token=TOKEN,schemeLibrary=TYPES['load_library'](E['CONFIG_ROOT'],config.get('focus',[])),jobs=job_list(),config=config,configError=error,categories=E['CATEGORIES'],priorities=E['PRIORITIES'],job=JOBS.get(ACTIVE_ID),reviews=REVIEWS.get(ACTIVE_ID,{}) ))
        self.reply({'error':'未找到页面'},404)
    def do_POST(self):
        global ACTIVE_ID
        try:
            if self.headers.get('X-Prototype-Token')!=TOKEN:return self.reply({'error':'请刷新页面后重试。'},403)
            n=int(self.headers.get('Content-Length',0))
            if n<=0 or n>85_000_000:raise ValueError('文件过大或请求为空。')
            data=json.loads(self.rfile.read(n));path=self.path
            if path=='/api/config':return self.reply({'config':E['save_config'](data.get('config',{})),'message':'配置已保存，下次启动自动读取。'})
            if path=='/api/focus':return self.reply({'config':E['save_config']({},data.get('focus',[])),'message':'关注项已保存。'})
            if path=='/api/scheme-library':
                return self.reply({'schemeLibrary':TYPES['save_library'](E['CONFIG_ROOT'],data.get('library')),'message':'类别和关注项已保存。'})
            if path=='/api/reviews':
                job=JOBS[data['id']]
                REVIEWS[job['id']]=active_reviews(job,data.get('reviews',{}))
                return self.reply({'message':'复核意见已暂存。'})
            if path=='/api/select-job':
                job=JOBS[data['id']];ACTIVE_ID=job['id']
                return self.reply({'job':job,'reviews':REVIEWS.get(job['id'],{}),'doc':linked_document(job),'jobs':job_list()})
            if path=='/api/models':
                cfg=E['resolve_config'](data.get('config',{}));res=E['request_api'](cfg,'/models')
                return self.reply({'models':[x['id'] for x in res.get('data',[]) if isinstance(x,dict) and isinstance(x.get('id'),str)]})
            if path=='/api/document':return self.reply({'doc':meta(DOCS[data['sha256']])})
            if path=='/api/import':
                raw=base64.b64decode(data['raw'],validate=True);doc=E['parse_document'](data['name'],raw);DOCS[doc['sha256']]=doc;RAW_DOCS[doc['sha256']]=raw
                return self.reply({'doc':meta(doc)})
            if path=='/api/import-result':
                if any(j['status']=='running' for j in JOBS.values()):raise ValueError('请等当前诊断完成或停止后导入结果。')
                job,reviews,docs=I['import_record'](data.get('record'),DOCS,RAW_DOCS,ROOT)
                JOBS[job['id']]=job;JOB_DOCS[job['id']]=docs;REVIEWS[job['id']]=reviews;ACTIVE_ID=job['id']
                for linked in docs:
                    if linked is not None:DOCS[linked['sha256']]=linked
                return self.reply({'job':job,'reviews':reviews,'sources':I['source_status'](job,docs),'doc':linked_document(job),'jobs':job_list()})
            if path=='/api/result-sources':
                job=JOBS[data['id']];return self.reply({'sources':I['source_status'](job,JOB_DOCS[job['id']]),'doc':linked_document(job),'job':job})
            if path=='/api/bind-result-source':
                job=JOBS[data['id']];raw=base64.b64decode(data['raw'],validate=True)
                index=I['source_slot'](data.get('source'),job)
                doc=I['bind_source'](job,index,data['name'],raw,ROOT,E)
                JOB_DOCS[job['id']][index]=doc;DOCS[doc['sha256']]=doc;E['LOC']['refresh_job'](job,JOB_DOCS[job['id']])
                return self.reply({'sources':I['source_status'](job,JOB_DOCS[job['id']]),'doc':linked_document(job),'job':job})
            if path=='/api/text':
                text=str(data.get('text','')).strip()
                if not text:raise ValueError('请填写设计说明。')
                doc=E['parse_document']('粘贴的设计说明.txt',text.encode());DOCS[doc['sha256']]=doc
                return self.reply({'doc':meta(doc)})
            if path=='/api/estimate':
                doc=DOCS[data['sha256']];design=[DOCS[h] for h in data.get('design',[])]
                return self.reply({'calls':E['estimate'](doc,design),'paragraphs':len(doc['rows']),'designCount':len(design),'initialCalls':E['estimate'](doc,design)-1,'reviewDynamic':True})
            if path=='/api/start':
                if data.get('consent') is not True:raise ValueError('请先确认资料发送与API调用。')
                if any(j['status']=='running' for j in JOBS.values()):raise ValueError('已有诊断正在运行，请先完成或停止。')
                cfg=E['resolve_config'](data.get('config',{}));E['validate_base'](cfg)
                E['validate_key'](cfg.get('key',''))
                doc=DOCS[data['sha256']];design=[DOCS[h] for h in data.get('design',[])];focus=E['clean_focus'](data.get('focus',[]))
                scheme_type=data.get('schemeType','通用')
                if not isinstance(scheme_type,str) or not scheme_type.strip() or len(scheme_type)>60:raise ValueError('请选择方案类别。')
                jid=secrets.token_hex(8)
                job=dict(id=jid,status='running',stage='准备诊断',completed=0,total=E['estimate'](doc,design),document=meta(doc),design=[meta(d) for d in design],
                         model=cfg['model'],schemeType=scheme_type,focus=focus,focusResults=[],issues=[],parameters=[],rejected=0,error='',cancel=False,createdAt=datetime.datetime.now().isoformat(timespec='seconds'))
                JOBS[jid]=job;JOB_DOCS[jid]=[doc]+design;ACTIVE_ID=jid
                threading.Thread(target=worker,args=(job,doc,design,cfg,focus),daemon=True).start()
                return self.reply({'job':job,'jobs':job_list()})
            if path=='/api/resume-plan':
                job=JOBS[data['id']];docs,cp=resume_state(job)
                return self.reply({'completed':job['completed'],'initialRemaining':len(FLOW['restore_splits'](FLOW['initial_tasks'](E,docs[0],docs[1:],E['batch_options'](job,resume=True)),job))-cp['initialDone'],'reviewCompleted':cp['reviewDone'],'document':job['document']})
            if path=='/api/resume':
                if data.get('consent') is not True:raise ValueError('请先确认续审的API调用。')
                if any(j['status']=='running' for j in JOBS.values()):raise ValueError('已有诊断正在运行。')
                job=JOBS[data['id']];docs,cp=resume_state(job)
                cfg=E['resolve_config'](data.get('config',{}));E['validate_base'](cfg);E['validate_key'](cfg.get('key',''))
                REVIEWS[job['id']]=active_reviews(job,data.get('reviews',{}))
                if REVIEWS[job['id']]:job.setdefault('reviewHistory',[]).append({'at':datetime.datetime.now().isoformat(timespec='seconds'),'reviews':REVIEWS[job['id']]})
                job.update(checkpoint=cp,resumeRequested=True,status='running',stage='准备从断点继续',cancel=False,model=cfg['model'])
                threading.Thread(target=worker,args=(job,docs[0],docs[1:],cfg,job['focus']),daemon=True).start()
                return self.reply({'job':job,'jobs':job_list()})
            if path=='/api/job':return self.reply({'job':JOBS[data['id']],'reviews':REVIEWS.get(data['id'],{})})
            if path=='/api/cancel':
                job=JOBS[data['id']];job['cancel']=True
                return self.reply({'message':'已申请停止，当前请求结束后停止后续批次。'})
            if path=='/api/context':
                if data.get('jobId'):
                    docs=JOB_DOCS[data['jobId']];source=data['source'];doc=docs[0] if source=='plan' else docs[int(source.replace('design',''))]
                else:doc=DOCS[data['sha256']]
                if doc is None:raise ValueError('原文尚未关联，请点击“关联原文”选择诊断时使用的文件。')
                pid=int(data['paragraph']);rows=[r for r in doc['rows'] if pid-2<=r['id']<=pid+2]
                return self.reply({'name':doc['name'],'rows':rows})
            if path=='/api/search':
                doc=DOCS[data['sha256']];q=str(data.get('query','')).strip()
                rows=[r for r in doc['rows'] if q and q in r['text']]
                return self.reply({'rows':rows[:80],'total':len(rows)})
            if path=='/api/export':
                job=JOBS[data['id']]
                if job['status']=='running':raise ValueError('请等本次诊断完成或停止后保存。')
                reviews=active_reviews(job,data.get('reviews',{}));path=E['report'](job,reviews,JOB_DOCS.get(job['id']));REVIEWS[job['id']]=reviews;job['savedPath']=path
                return self.reply({'path':path})
            if path=='/api/stop':
                if any(j['status']=='running' for j in JOBS.values()):raise ValueError('请先停止当前诊断，等当前请求结束后关闭服务。')
                self.reply({'message':'服务已关闭。'});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            self.reply({'error':'未找到接口'},404)
        except Exception as e:
            self.reply({'error':str(e) if isinstance(e,ValueError) else '处理失败，请检查资料格式或接口配置。'},400)

if __name__=='__main__':
    ThreadingHTTPServer.allow_reuse_address=False
    server=None
    for port in range(8876,8896):
        try:server=ThreadingHTTPServer(('127.0.0.1',port),Handler);break
        except OSError:continue
    if server is None:sys.exit('8876～8895端口均已占用。')
    server.daemon_threads=True;url=f'http://127.0.0.1:{port}';print(url,flush=True)
    if '--no-open' not in sys.argv:webbrowser.open(url)
    try:server.serve_forever()
    finally:server.server_close()
