"""逐批初审、全文回查、同类合并的诊断流程。"""
import datetime,copy,re,json,runpy,time,unicodedata
from pathlib import Path
SEARCH=runpy.run_path(str(Path(__file__).with_name('规范检索_v1.py')))
RETRIEVE=SEARCH['retrieve']

MATCH = runpy.run_path(str(Path(__file__).with_name('引文核对_v1.py')))
BUDGET_FILE = Path(__file__).resolve().parents[1]/'配置文件/规范检索预算_v1.json'
INTRO = re.compile(r'(?:下列|以下|如下|下述)(?:各项|各款)?(?:规定|要求|内容|条件)?[：:。.]?$')
REQUIREMENT = re.compile(r'应|必须|不得|严禁|限值|不宜|宜为|至少|不超过|[0-9０-９]')


def has_plan_quote(item):
    citations=item.get('citations')
    return isinstance(citations,list) and any(isinstance(c,dict) and c.get('source')=='plan' and c.get('quote') for c in citations)


def checked_basis(item, sent, inherited_refs=(), audit=None, phase=''):
    sent_by_ref = {r['ref']: r for r in sent}
    inherited = {r['ref']: r for r in inherited_refs}
    valid = []
    entries = item.get('basis', [])
    if not isinstance(entries, list):
        entries = [None]

    def note(ref, action, reason):
        if audit is not None:
            audit.append(dict(phase=phase, title=item.get('title',''), ref=ref, action=action, reason=reason))

    for entry in entries:
        if not isinstance(entry,dict):entry={}
        ref=entry.get('ref')
        row=sent_by_ref.get(ref) if isinstance(ref,str) else None
        prior=inherited.get(ref) if isinstance(ref,str) else None
        quote=entry.get('clause_quote')
        if not row and not prior:
            note(ref,'剔除','条号未提供')
            continue
        if not isinstance(quote,str) or not 0<len(''.join(quote.split()))<=80:
            note(ref,'剔除','缺少摘句或摘句超过80字')
            continue
        # 超预算的父条文仅允许复用随候选送出的已核验摘句。
        source=row['text'] if row else prior.get('clause_quote','')
        actual=MATCH['match_excerpt'](source,quote)
        if not actual and row and prior:
            # 父候选的已核验摘句也随回查/汇总请求送出。
            actual=MATCH['match_excerpt'](prior.get('clause_quote',''),quote)
        if not actual:
            note(ref,'剔除','摘句与送出的条文不符')
            continue
        relation=entry.get('relation')
        reason=''
        if relation not in ('参照','违反','未落实'):
            reason='关系无效'
        elif relation!='参照':
            if INTRO.search(quote.strip()) or not REQUIREMENT.search(quote):
                reason='摘句为总起句或缺少具体要求'
            elif relation=='违反' and (item.get('category') not in ('技术性错误','与本项目条件不符') or not has_plan_quote(item)):
                reason='违反关系缺少对应类别或方案引文'
            elif relation=='未落实' and item.get('category')!='内容缺项':
                reason='未落实关系与问题类别不符'
        if reason:
            note(ref,'降为参照',reason)
            relation='参照'
        elif prior and prior.get('relation') in ('违反','未落实') and relation=='参照':
            note(ref,'降为参照',str(entry.get('reason') or '模型回查调整关系'))
        valid.append(dict(row or prior,clause_quote=actual,relation=relation,reason=str(entry.get('reason',''))[:160]))
    item['_validatedBasis']=valid


def apply_basis_priority(item):
    priority=item.setdefault('modelPriority',item['priority'])
    if item.get('aiReview')!='待核':
        for basis in item.get('basis',[]):
            relation=basis.get('relation')
            if relation=='未落实' and basis.get('clause_quote') and item.get('category')=='内容缺项':
                priority=min(priority,'B')
            elif relation=='违反' and item.get('category') in ('技术性错误','与本项目条件不符') and basis.get('clause_quote') and has_plan_quote(item):
                priority=min(priority,'A' if basis.get('mandatory') else 'B')
    item['priority']=item.get('dedupPriority',priority)


def issue_text_key(issue):
    def normalized(value):
        return ''.join(c for c in value if not c.isspace() and not unicodedata.category(c).startswith('P'))
    return normalized(issue['title']), normalized(issue['description'])

def merge_identical(issues):
    """合并文字相同的最终问题，保留原编号、来源关联和可定位证据。"""
    groups = {}
    for issue in issues:
        key = issue_text_key(issue)
        groups.setdefault(key, []).append(issue)
    result, audit = [], []
    for members in groups.values():
        if len(members) == 1:
            result.append(members[0])
            continue
        best = min(members, key=lambda x: (x['priority'], not bool(x.get('candidateIds'))))
        kept = dict(best)
        ordered = [best] + [x for x in members if x is not best]
        kept['dedupPriority'] = best['priority']
        kept['mergedFrom'] = list(dict.fromkeys(i for x in ordered for i in [x['id'], *x.get('mergedFrom', [])]))
        kept['candidateIds'] = list(dict.fromkeys(i for x in ordered for i in x.get('candidateIds', [])))
        for field, keys in [('citations', ('source','paragraph','quote')), ('basis', ('ref','relation','clause_quote'))]:
            entries = {}
            for x in ordered:
                for entry in x.get(field, []):
                    entries.setdefault(tuple(entry.get(k) for k in keys), entry)
            kept[field] = list(entries.values())
        for x in ordered:
            if x.get('aiReview') == '待核':
                kept.update(aiReview='待核',checkReason=x.get('checkReason',''))
                break
        if any(x.get('reviewValidationError') for x in ordered):
            kept['reviewValidationError'] = True
        MATCH['annotate'](kept, parents=ordered)
        result.append(kept)
        audit.append(dict(method='文本规范化去重',title=kept['title'],issueIds=[x['id'] for x in ordered],
                          keptId=kept['id'],reason='标题和问题描述去空白、标点后相同'))
    return result, audit


def inherit_basis(item,parents):
    if 'basis' not in item:
        item['basis']=list({b['ref']:b for parent in parents for b in parent.get('basis',[]) if b.get('clause_quote')}.values())
    # 已核验的本轮 basis（包括空数组）是模型明确作出的决定。
    # 回查引文不合格时，调用方已完整保留初审候选。
    apply_basis_priority(item)


WIRE=runpy.run_path(str(Path(__file__).with_name('紧凑审查资料_v1.py')))

Pool=runpy.run_path(str(Path(__file__).with_name('并行审查调度_v1.py')))['ReviewPool']

class BatchTooLarge(Exception):
    pass

def split_task(task):
    source,doc,rows=task
    parts=WIRE['split_rows'](rows)
    return [(source,doc,part) for part in parts]

def restore_splits(tasks,job):
    for index in job.get('initialSplits',[]):
        if type(index)!=int or not 0<=index<len(tasks):raise ValueError('保存的分批位置无效。')
        tasks[index:index+1]=split_task(tasks[index])
    return tasks

def run_diagnosis(f,job,doc,design,cfg,focus,call,on_checkpoint=None):
    refs=f['source_index'](doc,design)
    options=f['batch_options'](job,resume=bool(job.get('resumeRequested')))
    mode=options['reviewFormat']
    cfg=dict(cfg,reviewFormat=mode)
    tasks=restore_splits(initial_tasks(f,doc,design,options),job)
    cp=prepare_resume(f,job,doc,design,tasks) if job.get('resumeRequested') else {'initialDone':0,'designFacts':[],'reviewDone':0,'reviewed':[]}
    job.update(wireVersion='compact2',**options)
    if not job.get('resumeRequested'):
        job['citationFailures']=0
        job.update(total=len(tasks)+1,completed=0,requests=[],failedBatch=None,candidates=[],reviewAudit=[],mergeAudit=[],reviewStats={})
    else:
        job.setdefault('citationFailures',0)
        job['attemptHistory']=job.get('attemptHistory',[])+[{'error':job.get('error',''),'failedBatch':job.get('failedBatch')}]
        job.update(error='',failedBatch=None,cancel=False,status='running')
    for key,value in (('requests',[]),('candidates',[]),('reviewAudit',[]),('mergeAudit',[]),('reviewStats',{})):
        job.setdefault(key,value)
    for item in job['issues']:item.setdefault('aiReview','待全篇回查')
    job['checkpoint']=cp
    design_facts=cp['designFacts'];current={};current_payload={}
    if not job.get('resumeRequested'):job['basisAudit']=[]
    basis_audit=job.setdefault('basisAudit',[])
    if not job.get('resumeRequested'):
        job['citationAudit']=[]
        job['citationStats']=dict(dropped=0,partialRemoved=0,corrected=0)
    job.setdefault('citationAudit',[])
    job.setdefault('citationStats',dict(dropped=job.get('rejected',0),partialRemoved=0,corrected=0))
    def commit_citations(events):
        request=current_record
        job['citationAudit'].extend(dict(e,batch=request['batch'],phase=request['phase']) for e in events)
        for key,count in f['QUOTE']['counts'](events).items():
            job['citationStats'][key]+=count
    runtime = f['RUNTIME']['settings']()
    check_lanes = f['RUNTIME'].get('parallel_limit')
    # 已打开的旧客户端续审时只会重新加载本流程，其引擎与配置模块仍是旧版。
    limit = check_lanes(cfg.get('parallelism',runtime.get('并发请求数',5))) if check_lanes else 1
    pool = Pool(limit, check_lanes(runtime.get('图片并发上限',2)) if check_lanes else 1, job)
    current_record = None
    active_work = None
    phase_seconds=job.setdefault('phaseSeconds',{})
    clock_phase=None
    tick=time.monotonic()

    def phase_clock(name):
        nonlocal clock_phase,tick
        now=time.monotonic()
        if clock_phase:
            phase_seconds[clock_phase]=round(phase_seconds.get(clock_phase,0)+now-tick,4)
        clock_phase=name
        tick=now

    def finish_log(work, error=None):
        if not work or not work.get('log'):
            return
        log = work.pop('log')
        if error:
            log['error'] = error
        try:
            f['RUNTIME']['save_log'](log, 'error' in log)
        except OSError as exc:
            job['logError'] = str(exc)

    def batch_section(rows):
        sections = {row.get('section','').split(' → ')[0] for row in rows}
        return sections.pop() if len(sections) == 1 else ''

    def prepare(payload, context, parents=(), previous_batch=None):
        payload['方案类别']=job.get('schemeType','通用')
        phase=payload.get('任务类型')
        standards=job.get('standardSelection') or {}
        items=[];omitted=[];inherited=[]
        for parent in sorted(parents,key=lambda x:x.get('priority','D')):
            inherited.extend(parent.get('basis',[]))
        if standards.get('standards') and phase!='设计提取':
            payload['选用规范']=[x['code'] for x in standards['standards']]
            payload['规范使用要求']='核对方案所引条号与提供的原文是否相符；未提供原文只能列为待核。ref 逐字复制，relation 选违反、未落实或参照。'
            if phase=='初审':
                query='\n'.join(row.get('text','') for row in payload['本次资料'])
            else:
                query='\n'.join(' '.join([x.get('title',''),x.get('description','')]+[c.get('quote','') for c in x.get('citations',[])]) for x in parents)
            budget=budgets[phase]
            section=''
            demote=[]
            if phase=='初审' and payload['本次资料']:
                section = batch_section(payload['本次资料'])
                if section and previous_batch and section == previous_batch[0]:
                    demote = previous_batch[1]
            summary = phase == '最终汇总'
            found = f.get('retrieve_standard_clauses', RETRIEVE)(
                query, book_ids=standards.get('book_ids', []), with_source=True, only_mandatory=summary,
                char_budget=budget, demote_refs=demote, reserve_per_book=not summary)
            # 回查继承旧依据时，也为本次检索命中的各本规范保留原文。
            combined = {}
            for row in inherited + found:
                if row.get('text') and row['ref'] not in combined:
                    combined[row['ref']] = row
            protected = []
            if inherited and found and not summary:
                reserved = SEARCH['book_reservations'](found, lambda r: r['ref'].split('#')[0])
                for row in reserved:
                    combined[row['ref']] = row
                    protected.append(row['ref'])
            singles = [row['ref'] for row in combined.values()
                       if row.get('mandatory') and row.get('whole_mandatory') is not None and not row['whole_mandatory']]
            items = SEARCH['fit_excerpts'](list(combined.values()), budget, protected, singles)
            sent_lengths = {row['ref']: len(row['text']) for row in items}
            omitted = [ref for ref, row in combined.items() if sent_lengths.get(ref, 0) < len(row['text'])]
            payload['规范条文']=[{k:r[k] for k in ('ref','mandatory','chapter_path','text')} for r in items]
        system=f[{'全篇回查':'REVIEW_SYSTEM','最终汇总':'FINAL_SYSTEM'}.get(phase,'SYSTEM')]
        system=f['FORMATS']['system_text'](system,f['WIRE']['GUIDE'],mode)
        payload=f['FORMATS']['render'](payload,context.get('source','plan'),refs,mode,f['WIRE'])
        if cfg.get('imageReviewScope') is not None:payload['图片审查范围']=cfg['imageReviewScope']
        chars=len(system)+len(f['FORMATS']['message'](payload,mode))
        if 'image_prompt_chars' in f:chars+=f['image_prompt_chars'](payload)
        if options['batchMethod']=='serialized' and phase in ('初审','设计提取') and chars>job['batchCharLimit']:
            raise BatchTooLarge
        context=dict(context,standardChars=sum(len(r['text']) for r in items),
                     inputChars=chars,standardRefs=[r['ref'] for r in items],truncatedStandardRefs=omitted)
        effort='high' if phase in ('全篇回查','最终汇总') else 'low'
        record=context|{'maxTokens':f['MAX_OUTPUT_TOKENS'],'thinking':bool(cfg.get('thinking',True)),'reasoningEffort':effort if cfg.get('thinking',True) else 'none','usage':{},'retries':[]}
        visual = phase != '最终汇总' and bool(f.get('review_image_ids', lambda data: [])(payload))
        return dict(payload=payload,record=record,visual=visual,parents=parents,items=items,section=section if phase=='初审' and standards.get('standards') else '',adjustments=[])

    def send(work, rate):
        record, payload = work['record'], work['payload']
        return call(dict(cfg,_cancelled=lambda:bool(job.get('cancel')),_retries=record['retries'],
                         _batchLog=lambda log:work.update(log=log),_rateEvent=rate),payload)

    def register(work):
        record = work['record']
        if work['adjustments']:
            record['parallelAdjustments'] = work['adjustments']
        if 'error' in work:
            exc = work['error']
            data = dict(getattr(exc,'diagnostics',{}))
            work['partialReply'] = data.pop('partialReply',None)
            record.update(data,status='cancelled' if isinstance(exc,f['RequestStopped']) else 'failed',error=str(exc))
        else:
            record.update(getattr(work['result'],'diagnostics',{}))
            record['status'] = 'received'
        requests = job['requests']
        requests.append(record)
        if len(requests)>1 and requests[-2].get('batch',0)>record['batch']:
            requests.sort(key=lambda r:r.get('batch',0))

    def discard(work):
        register(work)
        if 'error' not in work:
            work['record']['status']='discarded'
        finish_log(work, str(work['error']) if 'error' in work else None)

    def accept(work):
        nonlocal current,current_payload,current_record,active_work
        active_work=work
        current=current_record=work['record']
        current_payload=payload=work['payload']
        register(work)
        if 'error' in work:
            raise work['error']
        result,parents,items=work['result'],work['parents'],work['items']
        phase=payload.get('任务类型')
        f['WIRE']['expand_quotes'](result,payload)
        for item in result.get('issues',[]):
            if isinstance(item,dict):checked_basis(item,items,audit=basis_audit,phase=phase)
        for field,ids,key in [('reviews','candidateIds','candidateId'),('mergeGroups','issueIds','id')]:
            for entry in result.get(field,[]):
                if isinstance(entry,dict) and isinstance(entry.get('issue'),dict):
                    members=entry.get(ids)
                    if not isinstance(members,list):continue
                    allowed=[b for p in parents if p.get(key) in members for b in p.get('basis',[])]
                    issue=entry['issue']
                    checked_basis(issue,items,allowed,basis_audit,phase)
                    returned={b.get('ref') for b in issue.get('basis',[]) if isinstance(b,dict) and isinstance(b.get('ref'),str)} if isinstance(issue.get('basis'),list) else set()
                    for ref in {b['ref'] for b in allowed}-returned:
                        basis_audit.append(dict(phase=phase,title=issue.get('title',''),ref=ref,action='剔除',reason=entry.get('reason') or '模型未保留该依据'))
        return result
    def complete():
        finish_log(active_work)
        current_record['status']='completed';job['completed']+=1;ids();stats()
        phase_clock(clock_phase)
        if on_checkpoint:on_checkpoint()
    def cancelled():
        if job.get('cancel'):
            job['status']='cancelled';job['stage']='已停止，已完成条目保留';return True
        return False
    def ids():
        used={x.get('id') for x in job['issues'] if x.get('id')}
        next_id=max([int(x[1:]) for x in used|{x.get('id','') for x in job.get('candidates',[])} if re.fullmatch(r'Q\d+',x)]+[job.get('nextIssueId',1)-1])+1
        for item in job['issues']:
            if not item.get('id'):
                item['id']=f'Q{next_id:03d}';next_id+=1
            apply_basis_priority(item)
            item['bucket']=f['issue_bucket'](item)
        job['nextIssueId']=next_id
    def overview():
        selected=[]
        for row in doc['rows']:
            if len(row['text'])<50 or row.get('table'):continue
            if '工程概况' in row.get('chapter','') or any(t in row['text'] for t in ('本工程位于','本工程为','车站位于')):
                selected.append(row)
            if sum(len(r['text']) for r in selected)>2200:break
        return selected
    def stats():
        job['reviewStats']={'candidates':len(job['candidates']) or len(job['issues']),
            'excluded':sum(len(x['candidateIds']) for x in job['reviewAudit'] if x['decision']=='排除'),
            'merged':sum(len(x['candidateIds'])-1 for x in job['reviewAudit'] if x['decision']!='排除')+sum(len(x['issueIds'])-1 for x in job['mergeAudit'] if not x.get('skipped')),
            'pending':sum(x.get('aiReview')=='待核' for x in job['issues']),
            'unreviewed':sum(x.get('aiReview')=='待全篇回查' for x in job['issues'])}
    def initial_work(index, previous_batch):
        source,source_doc,rows=tasks[index]
        phase='整理设计依据' if source!='plan' else '正文初审'
        payload={'任务类型':'设计提取' if source!='plan' else '初审','资料名称':doc['name'],
                 '工程概况摘录':f['wire'](project_rows,'plan'),'已提取设计要求':list(design_facts),'重点关注':focus,
                 '本次资料':f['wire'](rows,source),'本批表格结构':f['STRUCTURE']['table_context'](source_doc,rows,source)}
        allowed={(source,r['id']) for r in rows}|{('plan',r['id']) for r in project_rows}
        for p in design_facts:
            for c in p['citations']:allowed.add((c['source'],c['paragraph']))
        # 表头也实际发送给模型，因此允许引用。
        for table in payload['本批表格结构']:
            for cell in table['cells']:
                for pid in cell['paragraphs']:allowed.add((source,pid))
        context={'batch':index+1,'phase':phase,'source':source,'documentName':source_doc['name'],
                 'paragraphStart':min(r['id'] for r in rows),'paragraphEnd':max(r['id'] for r in rows),'textChars':sum(len(r['text']) for r in rows)}
        work=prepare(payload,context,previous_batch=previous_batch)
        work.update(allowed=allowed,index=index)
        return work

    def commit_initial(work):
        source=work['record']['source']
        result=f['validate_result'](accept(work),refs,work['allowed'])
        if source=='plan':
            for item in result['issues']:
                item=f['mark_visual'](item,refs);item.setdefault('aiReview','待全篇回查');item['bucket']=f['issue_bucket'](item)
                f['append_unique'](job['issues'],[item],'issues')
        f['append_unique'](job['parameters'],result['parameters'],'parameters')
        job['citationFailures']+=sum('引用' in e for e in result['rejected'])
        job['rejected']+=len(result['rejected'])
        commit_citations(result['citationAudit'])
        if source!='plan':f['append_unique'](design_facts,result['parameters'],'parameters')
        cp['initialDone']=work['index']+1
        complete();ids()
    def review_work(index, group):
        selected={};searches=[]
        for item in group:
            found,terms=f['recall_context'](item,refs);selected.update(found)
            searches.append({'candidateId':item['candidateId'],'检索词':terms,'匹配段数':len(found)})
        context_rows=[];tables=[]
        for si,source_doc in enumerate([doc]+design):
            source='plan' if si==0 else 'design'+str(si)
            rows=[r for (s,_),r in selected.items() if s==source];rows.sort(key=lambda r:r['id'])
            context_rows+=f['wire'](rows,source)
            tables+=f['STRUCTURE']['table_context'](source_doc,rows,source)
        allowed=set(selected)
        for table in tables:
            for cell in table['cells']:
                for pid in cell['paragraphs']:allowed.add((table['source'],pid))
        payload={'任务类型':'全篇回查','候选问题':[f['compact_issue'](x) for x in group],
                 '方案章节目录':f['outline'](doc),'全篇检索记录':searches,'回查原文':context_rows,'表格结构':tables,'重点关注':focus}
        allowed.update(('plan',x['段号']) for x in payload['方案章节目录'])
        work=prepare(payload,{'batch':len(tasks)+index+1,'phase':'全篇回查','source':'review','documentName':doc['name'],
                              'candidateIds':[x['candidateId'] for x in group]},group)
        work.update(allowed=allowed,index=index)
        return work

    def commit_review(work):
        result=accept(work)
        changes=[];ignored=[]
        group=work['parents']
        try:
            if check_lanes:
                kept,audit=f['validate_review'](result,group,refs,work['allowed'],changes,ignored)
            else:
                kept,audit=f['validate_review'](result,group,refs,work['allowed'],changes)
        finally:
            if ignored:
                work['record']['ignoredCandidateIds']=ignored
                job.setdefault('reviewIdAudit',[]).append(dict(batch=work['record']['batch'],
                    ignoredCandidateIds=list(ignored),reason='模型返回了本组以外的候选编号'))
        commit_citations(changes)
        for item in kept:
            inherit_basis(item,[x for x in group if x['candidateId'] in item['candidateIds']])
            item['id']=next(x['id'] for x in group if x['candidateId'] in item['candidateIds'])
        reviewed.extend(kept);job['reviewAudit']+=audit;handled.update(x['candidateId'] for x in group)
        cp['reviewDone']=work['index']+1
        job['issues']=reviewed+[x for x in job['candidates'] if x['candidateId'] not in handled]
        complete();ids();stats()

    def run_window(items, commit, phase, offset, total):
        first=job['completed']
        def progress(finished, lanes):
            job['progressCompleted']=first+finished
            job['stage']=f'{phase} · 已完成 {offset+finished}/{total} · 并行 {lanes} 路'
        progress(0, min(pool.limit,len(items)))
        pool.execute(items,send,commit,discard,lambda n,k:progress(n,min(len(items),k)))

    def preparation_failed(exc, batch, phase):
        nonlocal current, current_record, current_payload, active_work
        current=dict(batch=batch,phase=phase)
        current_record=active_work=None
        current_payload={}
        job['failedBatch']=dict(current,error=str(exc))
        raise exc

    try:
        budgets=json.loads(BUDGET_FILE.read_text('utf-8-sig'))
        if any(type(budgets.get(k)) is not int or budgets[k]<0 for k in ('初审','全篇回查','最终汇总')):
            raise ValueError('请将规范检索预算设为非负整数')
        project_rows=overview()
        initial_waves = 0
        while cp['initialDone']<len(tasks):
            if cancelled():return
            first = index = cp['initialDone']
            is_plan = tasks[index][0] == 'plan'
            phase_clock('正文初审' if is_plan else '整理设计依据')
            job['stage'] = '准备正文初审批次' if is_plan else '准备设计资料提取'
            previous_batch = None
            if is_plan and index and tasks[index-1][0] == 'plan':
                # 旧断点的 unusedRefs 只包含未引用条文。取最后一批成功请求里实际送出的完整清单。
                last = next((r for r in reversed(job['requests']) if r.get('batch') == index
                             and r.get('source') == 'plan' and r.get('status') == 'completed'), {})
                prior_rows = f['wire'](tasks[index-1][2], 'plan')
                previous_batch = (batch_section(prior_rows), last.get('standardRefs', []))
            items = []
            while index < len(tasks) and not job.get('cancel'):
                try:
                    work = initial_work(index, previous_batch)
                except BatchTooLarge:
                    tasks[index:index+1]=split_task(tasks[index])
                    job.setdefault('initialSplits',[]).append(index)
                    job['total']=len(tasks)+1
                    continue
                except Exception as exc:
                    preparation_failed(exc,index+1,'准备初审')
                items.append(work)
                previous_batch = (work['section'], work['record']['standardRefs'])
                index += 1
                if not is_plan:
                    break  # 设计资料逐批提取，正文预组包要用到完整的设计要求。
            if cancelled():return
            design_count = sum(source != 'plan' for source,_,_ in tasks)
            if is_plan and not job.get('resumeRequested') and 'initial_waves' in f['RUNTIME']:
                initial_waves = f['RUNTIME']['initial_waves'](
                    [w['visual'] for w in items], design_count, limit, pool.visual_limit)
            run_window(items,commit_initial,items[0]['record']['phase'],
                       first-design_count if is_plan else first,len(tasks)-design_count if is_plan else design_count)
            del items
        if cancelled():return
        if not job['candidates']:
            for i,item in enumerate(job['issues'],1):item['candidateId']=f'C{i:03d}'
            job['candidates']=copy.deepcopy(job['issues'])
        groups=f['candidate_groups'](job['candidates']);job['total']=len(tasks)+len(groups)+1
        reviewed=cp['reviewed'];handled={cid for x in job['reviewAudit'] for cid in x['candidateIds']}
        while cp['reviewDone']<len(groups):
            if cancelled():return
            first=cp['reviewDone']
            phase_clock('全篇回查')
            items=[];prep_error=None
            for i in range(first,min(first+limit,len(groups))):
                if job.get('cancel'):break
                try:
                    items.append(review_work(i,groups[i]))
                except Exception as exc:
                    prep_error=exc
                    break
            if items:
                run_window(items,commit_review,'全篇回查',first,len(groups))
            if prep_error is not None:
                preparation_failed(prep_error,len(tasks)+i+1,'准备回查')
        if cancelled():return
        job['stage']='合并同类问题与最终汇总'
        phase_clock('最终汇总')
        ids()
        compact={'任务类型':'最终汇总','方案章节目录':f['outline'](doc),
                 '设计要求':design_facts,'已提取参数':job['parameters'],'已有问题':[f['compact_issue'](x) for x in job['issues']],'重点关注':focus}
        allowed={(c['source'],c['paragraph']) for p in job['parameters']+job['issues'] for c in p['citations']}
        allowed.update(('plan',x['段号']) for x in compact['方案章节目录'])
        if job.get('focusSources'):
            compact['关注项回写说明']='带编号的关注项在 focus 字段回写开头的方括号及编号。发现问题时在 summary 列出本次已有问题编号 Qxxx 和方案证据。未发现或资料不足应如实说明。'
        work=prepare(compact,{'batch':job['completed']+1,'phase':'最终汇总','source':'summary','documentName':doc['name']},job['issues'])
        results=[]
        pool.execute([work],send,lambda w:results.append(accept(w)),discard,lambda n,k:None)
        if not results and cancelled():return
        result=results[0]
        changes=[]
        consolidated,merges=f['validate_merges'](result,job['issues'],refs,allowed,changes)
        extra=f['validate_result'](result,refs,allowed,focus,True)
        text_keys={issue_text_key(x) for x in consolidated}
        for item in extra['issues']:
            item=f['mark_visual'](item,refs);item.setdefault('aiReview','已全篇回查');item['bucket']=f['issue_bucket'](item)
            key=issue_text_key(item)
            if key in text_keys:
                consolidated.append(item)
            else:
                before=len(consolidated)
                f['append_unique'](consolidated,[item],'issues')
                if len(consolidated)>before:text_keys.add(key)
        for item in consolidated:
            inherit_basis(item,[x for x in job['issues'] if x['id'] in item.get('mergedFrom',[])])
            if item.get('mergedFrom'):item['id']=item['mergedFrom'][0]
        job['issues']=consolidated
        ids()
        job['issues'], exact_merges = merge_identical(job['issues'])
        job['mergeAudit']=merges + exact_merges
        f['append_unique'](job['parameters'],extra['parameters'],'parameters')
        job['citationFailures']=job.get('citationFailures',0)+sum('引用' in e for e in extra['rejected'])+sum(bool(a.get('errors')) and any('引用' in e or '引文' in e or 'evidence' in e for e in a['errors']) for a in job['reviewAudit'])
        job['citationFailures']+=sum(any('引用' in error for error in row.get('validationErrors',[])) for row in merges)
        job['rejected']+=len(extra['rejected']);job['focusResults']=extra['focusResults']
        commit_citations(changes+extra['citationAudit'])
        job['issues'].sort(key=lambda x:(x.get('bucket')=='pending',x['priority'],f['CATEGORIES'].index(x['category'])));ids();stats()
        if f.get('finalize_focus'):f['finalize_focus'](job)
        if initial_waves:
            elapsed_initial = sum(phase_seconds.get(name,0) for name in ('整理设计依据','正文初审'))
            job['initialAverageSeconds'] = round(elapsed_initial / initial_waves, 3)
        job['status']='done';job['stage']='诊断完成';cp['finished']=True
        complete()
    except f['RequestStopped']:
        finish_log(active_work,'诊断已停止。')
        job.update(status='cancelled',stage='已停止，已完成条目保留',error='')
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else '处理失败，请检查接口或资料格式。'
        finish_log(active_work,message)
        if current_record is not None and current_record.get('status')!='completed':
            current_record.update(status='failed',error=message)
            job['failedBatch']=current_record|{'input':current_payload}
            if active_work.get('partialReply') is not None:job['failedBatch']['partialReply']=active_work['partialReply']
        elif job['failedBatch'] is None:
            job['failedBatch']={'batch':job['completed']+1,'phase':job['stage'],'error':message}
            current=job['failedBatch']
        location=f"第{current.get('batch',job['completed']+1)}/{job['total']}批 · {current.get('phase','准备诊断')}"
        if 'paragraphStart' in current:location+=f" · 段{current['paragraphStart']}—{current['paragraphEnd']}"
        usage=job['failedBatch'].get('usage',{});used=f" 本次生成{usage['completion_tokens']} tokens。" if isinstance(usage.get('completion_tokens'),int) else ''
        job.update(status='failed',error=location+'：'+message+used,stage='诊断暂停，已完成条目保留')
    finally:
        pool.close();phase_clock(None);job.pop('progressCompleted',None)
        ids();stats();job['finishedAt']=datetime.datetime.now().isoformat(timespec='seconds')

def initial_tasks(f,doc,design,options):
    tasks=[]
    for i,d in enumerate(design):
        for rows in f['chunks'](dict(d,**options)):tasks.append((f'design{i+1}',d,rows))
    for rows in f['chunks'](dict(doc,**options)):tasks.append(('plan',doc,rows))
    return tasks


def prepare_resume(f,job,doc,design,tasks=None):
    """恢复旧记录或新断点；只检查本地数据，不调用模型。"""
    if job.get('status')=='done':raise ValueError('本次诊断已经完成。')
    options=f['batch_options'](job,resume=True)
    if tasks is None:tasks=restore_splits(initial_tasks(f,doc,design,options),job)
    cp=copy.deepcopy(job.get('checkpoint'))
    if cp is None:
        done=[r for r in job.get('requests',[]) if r.get('status')=='completed' and r.get('source') in ['plan']+[f'design{i+1}' for i in range(len(design))]]
        if not done and job.get('completed',0):raise ValueError('该旧记录缺少批次信息，无法确定续审位置。')
        if len(done)>len(tasks):raise ValueError('原文批次数与记录不一致。')
        for request,(source,_,rows) in zip(done,tasks):
            if request.get('source')!=source or request.get('paragraphStart')!=min(r['id'] for r in rows) or request.get('paragraphEnd')!=max(r['id'] for r in rows):raise ValueError('原文段号或分批与记录不一致，无法续审。')
        audit=job.get('reviewAudit',[]);handled={cid for x in audit for cid in x['candidateIds']}
        groups=f['candidate_groups'](job.get('candidates',[]));review_done=0
        for group in groups:
            ids={x['candidateId'] for x in group}
            if ids<=handled:review_done+=1
            elif ids&handled:raise ValueError('旧记录中的回查组不完整，无法恢复该断点。')
            else:break
        cp={'initialDone':len(done),'designFacts':[p for p in job.get('parameters',[]) if any(c['source']!='plan' for c in p['citations'])],
            'reviewDone':review_done,'reviewed':[copy.deepcopy(x) for x in job['issues'] if x.get('candidateIds')]}
    if not isinstance(cp,dict) or not isinstance(cp.get('initialDone'),int) or not 0<=cp['initialDone']<=len(tasks) or not isinstance(cp.get('reviewDone'),int) or cp['reviewDone']<0 or not isinstance(cp.get('reviewed'),list) or not isinstance(cp.get('designFacts'),list):raise ValueError('断点信息不完整，无法续审。')
    if cp.get('finished'):raise ValueError('本次诊断已经完成。')
    if cp['reviewDone']>len(f['candidate_groups'](job.get('candidates',[]))):raise ValueError('回查断点超过候选组数。')
    return cp
