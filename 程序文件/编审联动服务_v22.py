"""审查端 v22。送审包按方案和包的双指纹绑定到一次审查。"""
import base64
import copy
import hashlib
import json
import runpy
import sys
import webbrowser
from collections import Counter
from contextvars import ContextVar
from pathlib import Path

PARAM_GUIDE='正文数值与同一部位、工况的已确认参数不一致时，按前后矛盾或技术性错误（数值错误）报告，在该问题的 parameterRefs 数组回写本批对应的 CS 编号，方案原文仍须逐字引用。'
ROOT=Path(__file__).resolve().parent
v21=runpy.run_path(str(ROOT/'server_v21.py'),init_globals={'_test_transport':globals().get('_test_transport')})
R=runpy.run_path(str(ROOT/'送审包规则_v1.py'))
C=runpy.run_path(str(ROOT/'编审覆盖与对比_v2.py'))
active=ContextVar('submission_work',default=None)
ctx,X,E=v21['ctx'],v21['X'],v21['E']
desktop_state=v21['desktop_state']
native_selection=R['native_selection']
packs={}
starting=ContextVar('starting_pack',default=None)
current=ContextVar('active_submission',default=None)
original_dispatch=X['dispatch']
original_focus=ctx['prepare_focus']
g=E['validate_result'].__globals__
original_run=E['run_diagnosis']
original_report=E['report']
original_render=g['FORMATS']['render']
original_expand=g['WIRE']['expand_quotes']
original_validate=g['validate_result']
original_finalize=g['finalize_focus']
original_compact=g['compact_issue']
word=original_dispatch.__globals__['WORD']
original_comment=word['add_comments'].__globals__['comment_text']
original_import=ctx['I']['import_record']


def import_record(*args,**kwargs):
    job,reviews,docs=original_import(*args,**kwargs)
    pack=job.get('bianshen')
    if isinstance(pack,dict) and pack.get('matched') is True:
        packs[job['document']['sha256'],pack['packSha256']]=pack
        if (job.get('bianshenSummary') or {}).get('version')!=2:
            for i in job['issues']:
                legacy=i.get('bianshenPending')
                if isinstance(legacy,str):
                    i['bianshenPending']=dict(id=legacy,coverage='partial',reason='历史关联，完整覆盖尚待核对。')
            C['summarize'](job)
        if job.get('bianshenComparison') and job['bianshenComparison'].get('version')!=2:
            job['bianshenComparison']=dict(unavailable=True,reason='请选取上次记录，按实际改文重新对比')
    return job,reviews,docs


def match(data):
    sha=data['sha256']
    doc=ctx['DOCS'].get(sha)
    if not doc or sha not in ctx['RAW_DOCS']:raise ValueError('请先导入方案。')
    raw=base64.b64decode(data['raw'],validate=True)
    pack=R['read_pack'](data['documentName'],data['name'],raw,sha)
    if pack:packs[sha,pack['packSha256']]=pack
    return dict(bianshen=pack)


def dispatch(context,path,data):
    if path.endswith('/bianshen-match'):return match(data)
    if path.endswith('/bianshen-previous'):
        job=context['JOBS'][data['id']]
        prev=job['bianshen']['previousReview']
        raw=base64.b64decode(data['raw'],validate=True)
        if hashlib.sha256(raw).hexdigest()!=prev.get('recordSha256'):
            raise ValueError('所选文件与送审包登记的上次审查记录不一致。')
        record=json.loads(raw.decode('utf-8-sig'))
        cfg=E['resolve_config'](data.get('config',{}))
        comparison=compare_record(job,record,context['JOB_DOCS'][job['id']][0],cfg)
        job['bianshenComparison']=comparison
        E['report'](job,context['REVIEWS'].get(job['id'],{}),context['JOB_DOCS'][job['id']])
        return dict(job=job)
    if path.endswith('/review-start') and data.get('bianshenPackSha'):
        key=data['sha256'],data['bianshenPackSha']
        pack=packs.get(key)
        if not pack:raise ValueError('送审包未与当前 Word 配对，请重新导入。')
        token=starting.set(pack)
        try:return original_dispatch(context,path,data)
        finally:starting.reset(token)
    return original_dispatch(context,path,data)


def focus(kind,items):
    bundle=original_focus(kind,items)
    return dict(bundle,bianshen=starting.get()) if starting.get() else bundle


def run(job,*args,**kwargs):
    pack=job.get('bianshen')
    if not pack or pack.get('matched') is not True:return original_run(job,*args,**kwargs)
    token=current.set(pack)
    doc=args[0] if args else kwargs['doc']
    cfg=args[2] if len(args)>2 else kwargs['cfg']
    state=active.set(dict(doc=doc,cfg=cfg,call=kwargs.get('call') or (args[4] if len(args)>4 else None)))
    try:return original_run(job,*args,**kwargs)
    finally:
        active.reset(state)
        current.reset(token)


def render(payload,*args):
    pack=current.get()
    if pack is None:return original_render(payload,*args)
    lines=R['select_params'](pack['parameters'],payload)
    rendered=original_render(payload,*args)
    if payload.get('任务类型')=='最终汇总':
        rows=C['proposal'](payload.get('已有问题',[]),pack['pending'])
        if rows:
            rendered['待补候选']=rows
            rendered['待补覆盖判读要求']=C['PENDING_GUIDE']
    if lines:
        rendered['已确认参数表']=lines
        rendered['参数核对要求']=PARAM_GUIDE
    return rendered


def annotate_raw(result,payload):
    original_expand(result,payload)
    pack=current.get()
    if pack is None:return
    if payload.get('任务类型')=='最终汇总' and active.get() is not None:
        active.get().update(rows=payload.get('待补候选',[]),decisions=result.get('pendingDecisions',[]))
    sent={s.split(']',1)[0][1:] for s in payload.get('已确认参数表',[])}
    valid={p['id']:p for p in pack['parameters'] if p['id'] in sent}
    items=list(result.get('issues') or [])
    for k in ('reviews','mergeGroups'):
        items.extend(x.get('issue') for x in result.get(k,[]) if isinstance(x,dict))
    for item in items:
        if not isinstance(item,dict):continue
        ids=item.get('parameterRefs',[])
        if not isinstance(ids,list):ids=[ids]
        ids=list(ids)
        if 'parameterRefs' not in item and isinstance(item.get('parameterBasis'),list):
            ids.extend(b.get('ref') if isinstance(b,dict) else b for b in item['parameterBasis'])
        basis=item.get('basis')
        if isinstance(basis,list):
            standard=[]
            for b in basis:
                if isinstance(b,dict) and (str(b.get('ref','')).startswith('CS-') or b.get('relation')=='不一致'):
                    ids.append(b.get('ref'))
                else:standard.append(b)
            item['basis']=standard
        refs=list(dict.fromkeys(i for i in ids if isinstance(i,str)))
        item['_packEvidence']=[
            dict(ref=i,label=valid[i]['label'],zone=valid[i].get('zone',''),value=valid[i]['value'],
                 unit=valid[i].get('unit',''),source=R['source_label'](valid[i]),relation='不一致') for i in refs if i in valid]
        item['_packInvalid']=any(not isinstance(i,str) or i not in valid for i in ids)


def validate(obj,refs,allowed=None,focus=(),final=False):
    if current.get() is None or not isinstance(obj,dict) or not isinstance(obj.get('issues'),list):
        return original_validate(obj,refs,allowed,focus,final)
    result=original_validate(dict(obj,issues=[]),refs,allowed,focus,final)
    for raw in obj['issues']:
        one=original_validate(dict(issues=[raw],parameters=[]),refs,allowed)
        for item in one['issues']:
            if raw.get('_packEvidence'):item['parameterBasis']=raw['_packEvidence']
            if raw.get('_packInvalid'):
                item['aiReview']='待核'
                item['checkReason']='；'.join(filter(None,[item.get('checkReason'),'参数编号未在本批送出，已移除该依据']))
        for field in ('issues','rejected','citationAudit'):result[field].extend(one[field])
    return result


def compact(issue):
    data=original_compact(issue)
    if current.get() is not None and 'parameterBasis' in data:
        data['parameterBasis']=[{'ref':b['ref']} for b in data['parameterBasis']]
    return data


def previous_record(digest):
    if not isinstance(digest,str) or len(digest)!=64:return None
    for path in E['RECORD_ROOT'].glob('*.json'):
        try:
            with path.open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=digest:continue
                f.seek(0)
                return json.load(f)
        except (OSError,ValueError,KeyError):continue


PAIR_GUIDE=('比较两次剩余的意见，仅在部位、具体缺陷和整改动作相同时配对，勿按编号、同章或同类强行配对。'
    '每个编号最多用一次。返回 JSON 对象，pairs 为数组，每项含 old、new、布尔值 same 和具体 reason。')

def model_json(cfg,instruction,data):
    body=dict(model=cfg['model'],messages=[dict(role='system',content=instruction),dict(role='user',content=json.dumps(data,ensure_ascii=False))],
              max_tokens=16384,response_format=dict(type='json_object'))
    if cfg['model'].startswith('deepseek'):
        body['thinking']=dict(type='enabled' if cfg.get('thinking',True) else 'disabled')
        if cfg.get('thinking',True):body['reasoning_effort']='high'
    options={k:v for k,v in cfg.items() if k!='imageReviewScope'}
    raw=E['request_api'](options,'/chat/completions',body)
    return E['parse_model_reply'](raw,{}),E['token_usage'](raw)


def compare_record(job,record,doc,cfg,call=None):
    prior=record['diagnosis']
    old_pack=prior.get('bianshen') or {}
    sha=prior.get('document',{}).get('sha256')
    if not old_pack.get('paragraphMap'):
        old_pack=packs.get((sha,old_pack.get('packSha256')),old_pack)
    pack=job['bianshen']
    old_ctx=C['evidence']((record.get('sourceDocuments') or [{}])[0],old_pack)
    new_ctx=C['evidence'](doc,pack)
    if not old_ctx[1]:
        texts=Counter(r['text'] for r in old_ctx[0].values())
        now=Counter(r['text'] for r in new_ctx[0].values())
        anchors={r['text']:new_ctx[1].get(n) for n,r in new_ctx[0].items() if now[r['text']]==1}
        old_ctx[1].update({n:anchors[r['text']] for n,r in old_ctx[0].items() if texts[r['text']]==1 and anchors.get(r['text'])})
        for h in pack['previousReview'].get('handled',[]):
            if h.get('blockId') and h.get('before') and old_ctx[0].get(h.get('paragraph'),{}).get('text')==h['before']:
                old_ctx[1][h['paragraph']]=h['blockId']
    def ask(data):
        if call:
            result=call(cfg,dict(任务类型='复审配对',要求=PAIR_GUIDE,**data))
            usage=getattr(result,'diagnostics',{}).get('usage',{})
        else:result,usage=model_json(cfg,PAIR_GUIDE,data)
        if not isinstance(result.get('pairs'),list):raise ValueError('模型没有返回复审配对清单')
        job.setdefault('requests',[]).append(dict(batch=len(job.get('requests',[]))+1,phase='复审配对',status='completed',usage=usage))
        return result
    return C['compare'](prior['issues'],job['issues'],pack['previousReview'].get('handled',[]),old_ctx,new_ctx,ask)


def finalize(job):
    original_finalize(job)
    pack=job.get('bianshen')
    if not pack:return
    state=active.get() or {}
    C['apply_links'](job,state.get('rows',[]),state.get('decisions',[]))
    previous=pack.get('previousReview')
    if previous:
        old=previous_record(previous.get('recordSha256'))
        if old is None:job['bianshenComparison']=dict(unavailable=True,reason='未找到指纹一致的上次审查记录')
        else:
            try:job['bianshenComparison']=compare_record(job,old,state['doc'],state['cfg'],state.get('call'))
            except (ValueError,OSError) as exc:
                job['bianshenComparison']=dict(unavailable=True,reason='复审配对未完成，可重新选择上次记录。'+str(exc))


def comment(issue):
    link=issue.get('bianshenPending')
    prefix=''
    if isinstance(link,dict) and link.get('coverage') in ('full','partial'):
        prefix='【编制已登记待补】' if link.get('coverage')=='full' else '【相关待补（部分覆盖）】'
    text=prefix+original_comment(issue)
    for b in issue.get('parameterBasis',[]):
        text+=f"\n参数表 [{b['ref']}] {b['label']} {b.get('zone','')} = {b['value']} {b.get('unit','')}，来源：{b['source']}（不一致）"
    return text


def report(job,*args,**kwargs):
    path=original_report(job,*args,**kwargs)
    summary=job.get('bianshenSummary')
    if summary:
        lines=['','## 编审联动','',
               '本次新增问题　'+'　'.join(f'{k} 级 {n} 条' for k,n in summary['newPriorities'].items()),
               f"编制阶段已登记待补 {summary['registered']} 项，本次仍未闭合。关联 {summary['linkedIssues']} 条审查意见。"]
        for i in job['issues']:
            link=i.get('bianshenPending')
            if isinstance(link,dict) and link.get('coverage') in ('full','partial'):
                label='编制已登记待补' if link['coverage']=='full' else '相关待补（部分覆盖）'
                name=next((p['title'] for p in job['bianshen']['pending'] if p['id']==link['id']),link['id'])
                lines.append(f"- {i['id']} {label} · {name} · {link['reason']}")
            for b in i.get('parameterBasis',[]):
                lines.append(f"- {i['id']} 参数表 [{b['ref']}] {b['label']} {b.get('zone','')} = {b['value']} {b.get('unit','')}，来源：{b['source']}（不一致）")
        comp=job.get('bianshenComparison') or {}
        if comp.get('version')==2:
            for key,label in C['GROUPS']:
                lines.extend(['',f"### {label}（{len(comp[key])} 条）"])
                for row in comp[key]:
                    prefix=row.get('previousId','')
                    lines.append('- '+(prefix+' → ' if prefix else '')+row['id']+' '+row['title'])
                    if row.get('acceptedAgain'):lines.append('  采纳后仍报出，请复核')
                    for field,title in [('reason','不采纳原因'),('before','改前'),('after','改后')]:
                        if row.get(field):lines.append('  '+title+'　'+row[field])
        elif comp.get('unavailable'):lines.append('复审对比　'+comp['reason'])
        with Path(path).open('a',encoding='utf8') as f:f.write('\n'.join(lines)+'\n')
    return path


original_prepare=E.get('prepare_review_request')

def prepare_request(cfg,body,phase):
    if original_prepare:original_prepare(cfg,body,phase)
    fmt=body.get('response_format') or {}
    if fmt.get('type')!='json_schema' or not (cfg.get('_reviewPayload') or {}).get('待补候选'):return
    fmt=body['response_format']=copy.deepcopy(fmt)
    schema=fmt['json_schema']['schema']
    props={key:{'type':'string'} for key in ('issueId','pendingId','coverage','reason')}
    props['coverage']['enum']=['full','partial']
    schema['properties']['pendingDecisions']=dict(type='array',items=dict(type='object',properties=props,
        required=list(props),additionalProperties=False))
    schema['required'].append('pendingDecisions')

E['prepare_review_request']=prepare_request
X['dispatch']=dispatch
ctx['I']['import_record']=import_record
ctx['prepare_focus']=focus
E['run_diagnosis']=run
E['report']=report
g['FORMATS']['render']=render
g['WIRE']['expand_quotes']=annotate_raw
g['validate_result']=E['validate_result']=validate
g['finalize_focus']=finalize
g['compact_issue']=compact
word['add_comments'].__globals__['comment_text']=comment


class Handler(v21['Handler']):
    def reply(self,obj,status=200,ctype='application/json; charset=utf-8'):
        if self.path=='/' and isinstance(obj,bytes) and b'/focus-extension.js' in obj:
            obj=obj.replace(b'</body>',b'<script src="/submission.js"></script></body>')
        return super().reply(obj,status,ctype)

    def do_GET(self):
        if self.path=='/submission.js':
            return self.reply((ROOT/'编审联动界面_v1.js').read_bytes(),ctype='application/javascript; charset=utf-8')
        return super().do_GET()


def create_server():
    for port in range(8876,8896):
        try:
            server=v21['v20']['LocalServer'](('127.0.0.1',port),Handler)
            server.daemon_threads=True
            return server
        except OSError:continue
    raise ValueError('本地服务端口已占用。')


if __name__=='__main__':
    with create_server() as server:
        if '--no-open' not in sys.argv:webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        server.serve_forever()
