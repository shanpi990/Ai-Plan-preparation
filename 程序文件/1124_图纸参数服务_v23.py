"""R4 审查入口。图纸参数只通过 v22 已确认参数通道进入审查。"""
import copy
import json
import runpy
import sys
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
v22=runpy.run_path(str(ROOT/'1124_编审联动服务_v22.py'),init_globals={'_test_transport':globals().get('_test_transport')})
D=runpy.run_path(str(ROOT/'1124_图纸参数工作区_v1.py'))
E,X,ctx=v22['E'],v22['X'],v22['ctx']
origin=D['ORIGIN']
draw=D['Workspace'](ROOT,ROOT.parent/'运行数据/图纸识别',E)
native_selection=v22['native_selection']
packs=v22['packs']
real={}
base_dispatch=X['dispatch']
base_focus=ctx['prepare_focus']
base_import=ctx['I']['import_record']
g=v22['g']
base_expand=g['WIRE']['expand_quotes']
base_finalize=g['finalize_focus']
base_report=E['report']
zone_rules=D['ZONE']

def render(payload,source,refs,mode,wire):
    pack=v22['current'].get()
    if not drawing(pack):
        return v22['render'](payload,source,refs,mode,wire)
    rendered=v22['original_render'](payload,source,refs,mode,wire)
    if payload.get('任务类型')=='设计提取':return rendered
    lines=zone_rules['select'](pack['parameters'],payload)
    if not lines:return rendered
    rendered['参数核对要求']=v22['PARAM_GUIDE']+'\n'+zone_rules['COMPARISON']
    phase=payload.get('任务类型')
    system=g[{'全篇回查':'REVIEW_SYSTEM','最终汇总':'FINAL_SYSTEM'}.get(phase,'SYSTEM')]
    preamble=g['FORMATS']['system_text'](system,wire['GUIDE'],mode)
    # 为模型输出留出原有空间。紧凑输入仍由审查引擎依实际序列化字符数拆分。
    cfg=(v22['active'].get() or {}).get('cfg',{})
    context=int(cfg.get('contextTokens') or 131072)
    input_budget=max(0,context-g['MAX_OUTPUT_TOKENS'])
    base=zone_rules['estimate'](preamble+g['FORMATS']['message'](rendered,mode))
    while lines and base+zone_rules['estimate'](json.dumps({'已确认参数表':lines},ensure_ascii=False))+16>input_budget:
        lines.pop()
    if lines:rendered['已确认参数表']=lines
    else:rendered.pop('参数核对要求')
    return rendered

def desktop_state():
    state=v22['desktop_state']()
    with draw.lock:
        return dict(state,busy=state['busy'] or any(draw.busy(k) for k in draw.operations))

def drawing(pack):
    return isinstance(pack,dict) and pack.get('origin')==origin

def register(sha,s):
    pack=D['parameter_pack'](s)
    packs[sha,pack['packSha256']]=pack
    return pack

def restored(s):
    if not isinstance(s,dict) or not all(isinstance(s.get(k),list) for k in ('documents','candidates','parameters','aiLog')):
        raise ValueError('记录缺少图纸参数明细')
    return copy.deepcopy(s)

def import_record(*args,**kw):
    record=args[0] if args else kw.get('record',{})
    stored=record.get('diagnosis',{}) if isinstance(record,dict) else {}
    pack=stored.get('bianshen') or {}
    recovered=None
    if drawing(pack) and stored.get('drawingParams'):
        recovered=D['restore_pack'](restored(stored['drawingParams']),pack)
    job,reviews,docs=base_import(*args,**kw)
    if recovered:
        job['bianshen']=recovered
        packs[job['document']['sha256'],recovered['packSha256']]=recovered
        D['restore_merged_links'](job)
        job.pop('bianshenSummary',None)
    return job,reviews,docs

def dispatch(context,path,data):
    action=path.rsplit('/',1)[-1]
    if action=='bianshen-match':
        r=base_dispatch(context,path,data)
        if r.get('bianshen'):real[data['sha256']]=r['bianshen']['packSha256']
        return r
    if action.startswith('drawing-'):
        action=action[8:]
        if action=='source':return draw.crop(data['source'])
        sha=data['sha256']
        if sha not in context['DOCS']:raise ValueError('请先导入待审方案')
        if sha in real:return dict(suppressed=True)
        if action=='status':return draw.status(sha)
        if action=='upload':return draw.upload(sha,data)
        if action=='type':
            with draw.lock:
                s=draw.check_edit(sha,data)
                kind=data.get('type')
                if kind not in D['TYPES']:raise ValueError('请选择有效的资料类型')
                doc=next((d for d in s['documents'] if d['sha256']==data.get('docId')),None)
                if not doc:raise ValueError('请重新选择图纸')
                if doc['type']!=kind:
                    doc['type']=kind;draw.clear_results(s,doc['sha256']);draw.save(sha)
                return draw.status(sha)
        if action=='remove':return draw.remove(sha,data)
        if action=='start':
            cfg=E['resolve_config'](data.get('config',{}));E['validate_base'](cfg);E['validate_key'](cfg.get('key',''))
            return draw.start(sha,data,cfg)
        if action=='cancel':return draw.cancel(sha)
        if action=='reuse':
            prior=context['JOBS'].get(data.get('recordId'),{})
            if not drawing(prior.get('bianshen')):raise ValueError('所选记录没有已确认图纸参数')
            snapshot=restored(prior['drawingParams'])
            D['ZONE']['normalize'](snapshot)
            if not snapshot['parameters']:raise ValueError('记录没有已确认图纸参数')
            with draw.lock:
                current=draw.check_edit(sha,data)
                snapshot['revision']=current['revision']
                draw.state[sha]=snapshot
                draw.save(sha)
                return dict(**draw.status(sha),pack=register(sha,snapshot))
        if action=='invalidate':
            with draw.lock:
                s=draw.check_edit(sha,data)
                draw.invalidate(s);draw.save(sha)
                return draw.status(sha)
        if action=='confirm':
            with draw.lock:
                s=draw.confirm(sha,data)
                return dict(**draw.status(sha),pack=register(sha,s))
        raise ValueError('未知图纸操作')
    if action=='review-start' and data.get('bianshenPackSha'):
        sha=data['sha256'];key=data['bianshenPackSha']
        if sha in real and key!=real[sha]:raise ValueError('当前方案已配有编制助手送审包，请使用送审包开始审查')
        with draw.lock:
            draft=draw.get(sha)
            if key==D['parameter_pack'](draft)['packSha256'] and draft['parameters']:register(sha,draft)
            pack=packs.get((sha,key))
            if drawing(pack):
                if not draft['parameters'] or key!=D['parameter_pack'](draft)['packSha256'] or draft['kind']!=data.get('schemeType'):
                    raise ValueError('图纸参数或方案类别已变更，请重新确认')
                return base_dispatch(context,path,data)
    return base_dispatch(context,path,data)

def focus(kind,items):
    bundle=base_focus(kind,items)
    pack=bundle.get('bianshen')
    if drawing(pack):
        sha=next(k[0] for k,v in packs.items() if v is pack)
        bundle['drawingParams']=copy.deepcopy(draw.get(sha))
    return bundle

def expand(obj,payload):
    base_expand(obj,payload)
    pack=v22['current'].get()
    if not drawing(pack):return
    params={p['id']:p for p in pack['parameters']}
    rows=list(obj.get('issues') or [])
    for name in ('reviews','mergeGroups'):
        rows.extend(x.get('issue') for x in obj.get(name,[]) if isinstance(x,dict))
    for row in rows:
        if not isinstance(row,dict):continue
        for b in row.get('_packEvidence',[]):
            p=params[b['ref']]
            b.update(origin=origin,drawingSource=copy.deepcopy(p['source']),zone='，'.join(filter(None,[p.get('zone'),p.get('drawingScope')])))

def finalize(job):
    if drawing(job.get('bianshen')):
        D['restore_merged_links'](job)
        return v22['original_finalize'](job)
    return base_finalize(job)

def line(b):
    zone='（'+b['zone']+'）' if b.get('zone') else ''
    return f"图纸参数 {b['ref']} {b['label']}{zone}= {b['value']} {b.get('unit','')}，{b['source']}（{origin}）"

def comment(issue):
    if not any(b.get('origin')==origin for b in issue.get('parameterBasis',[])):return v22['comment'](issue)
    legacy=[b for b in issue['parameterBasis'] if b.get('origin')!=origin]
    return '\n'.join([v22['comment'](dict(issue,parameterBasis=legacy))]+[line(b) for b in issue['parameterBasis'] if b.get('origin')==origin])

def report(job,*args,**kw):
    path=base_report(job,*args,**kw)
    if drawing(job.get('bianshen')):
        with Path(path).open('a',encoding='utf8') as out:
            out.write('\n## 审查端图纸识别\n\n')
            for issue in job['issues']:
                for b in issue.get('parameterBasis',[]):
                    if b.get('origin')==origin:out.write(f"- {issue['id']} {line(b)}\n")
    return path

g['FORMATS']['render']=render
X['dispatch']=dispatch
ctx['prepare_focus']=focus
ctx['I']['import_record']=import_record
g['WIRE']['expand_quotes']=expand
g['finalize_focus']=finalize
v22['word']['add_comments'].__globals__['comment_text']=comment
E['report']=report

class Handler(v22['Handler']):
    def do_GET(self):
        if self.path=='/submission.js':
            content=(ROOT/'1124_编审联动界面_v1.js').read_bytes()+b'\n'+(ROOT/'1124_图纸参数界面_v2.js').read_bytes()
            return self.reply(content,ctype='application/javascript; charset=utf-8')
        return super().do_GET()

def create_server():
    for port in range(8876,8896):
        try:
            server=v22['v21']['v20']['LocalServer'](('127.0.0.1',port),Handler)
            server.daemon_threads=True
            return server
        except OSError:continue
    raise ValueError('本地服务端口已占用。')

if __name__=='__main__':
    with create_server() as server:
        if '--no-open' not in sys.argv:webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        server.serve_forever()
