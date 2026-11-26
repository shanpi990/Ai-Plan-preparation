"""逐批初审、全文回查、同类合并的诊断流程。"""
import datetime,copy,re

def run_diagnosis(f,job,doc,design,cfg,focus,call,on_checkpoint=None):
    refs=f['source_index'](doc,design)
    tasks=initial_tasks(f,doc,design)
    cp=prepare_resume(f,job,doc,design) if job.get('resumeRequested') else {'initialDone':0,'designFacts':[],'reviewDone':0,'reviewed':[]}
    if not job.get('resumeRequested'):
        job.update(total=f['estimate'](doc,design),completed=0,requests=[],failedBatch=None,candidates=[],reviewAudit=[],mergeAudit=[],reviewStats={})
    else:
        job['attemptHistory']=job.get('attemptHistory',[])+[{'error':job.get('error',''),'failedBatch':job.get('failedBatch')}]
        job.update(error='',failedBatch=None,cancel=False,status='running')
    for key,value in (('requests',[]),('candidates',[]),('reviewAudit',[]),('mergeAudit',[]),('reviewStats',{})):
        job.setdefault(key,value)
    for item in job['issues']:item.setdefault('aiReview','待全篇回查')
    job['checkpoint']=cp
    design_facts=cp['designFacts'];current={};current_payload={}
    def invoke(payload,context):
        nonlocal current,current_payload
        payload['方案类别']=job.get('schemeType','通用')
        standards = job.get('standardSelection')
        if isinstance(standards, dict) and standards.get('standards'):
            payload['选用规范'] = standards
            payload['规范使用要求'] = '按选用规范和提供的条文摘要核对方案。涉及未提供的条文原文或项目规定时列为待核，并说明要补查的依据。'
        current=context;current_payload=payload
        effort='high' if payload.get('任务类型') in ('全篇回查','最终汇总') else 'low'
        record=context|{'maxTokens':f['MAX_OUTPUT_TOKENS'],'thinking':bool(cfg.get('thinking',True)),'reasoningEffort':effort if cfg.get('thinking',True) else 'none','usage':{}}
        try:result=call(cfg,payload)
        except Exception as exc:
            stats=dict(getattr(exc,'diagnostics',{}));partial=stats.pop('partialReply',None)
            record.update(stats);record.update(status='failed',error=str(exc));job['requests'].append(record)
            job['failedBatch']=record|{'input':payload}
            if partial is not None:job['failedBatch']['partialReply']=partial
            raise
        record.update(getattr(result,'diagnostics',{}));record['status']='received';job['requests'].append(record)
        return result
    def complete():
        job['requests'][-1]['status']='completed';job['completed']+=1;ids();stats()
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
            'merged':sum(len(x['candidateIds'])-1 for x in job['reviewAudit'] if x['decision']!='排除')+sum(len(x['issueIds'])-1 for x in job['mergeAudit']),
            'pending':sum(x.get('aiReview')=='待核' for x in job['issues']),
            'unreviewed':sum(x.get('aiReview')=='待全篇回查' for x in job['issues'])}
    try:
        project_rows=overview()
        for task_index,(source,source_doc,rows) in enumerate(tasks):
            if task_index<cp['initialDone']:continue
            if cancelled():return
            phase='整理设计依据' if source!='plan' else '正文初审'
            job['stage']=phase+f" · {job['completed']+1}/{len(tasks)}"
            payload={'任务类型':'设计提取' if source!='plan' else '初审','资料名称':doc['name'],
                     '工程概况摘录':f['wire'](project_rows,'plan'),'已提取设计要求':design_facts,'重点关注':focus,
                     '本次资料':f['wire'](rows,source),'本批表格结构':f['STRUCTURE']['table_context'](source_doc,rows,source)}
            allowed={(source,r['id']) for r in rows}|{('plan',r['id']) for r in project_rows}
            for p in design_facts:
                for c in p['citations']:allowed.add((c['source'],c['paragraph']))
            # 表头也实际发送给模型，因此允许引用。
            for table in payload['本批表格结构']:
                for cell in table['cells']:
                    for pid in cell['paragraphs']:allowed.add((source,pid))
            context={'batch':job['completed']+1,'phase':phase,'source':source,'documentName':source_doc['name'],
                     'paragraphStart':min(r['id'] for r in rows),'paragraphEnd':max(r['id'] for r in rows),'textChars':sum(len(r['text']) for r in rows)}
            result=f['validate_result'](invoke(payload,context),refs,allowed)
            if source=='plan':
                for item in result['issues']:
                    item=f['mark_visual'](item,refs);item.setdefault('aiReview','待全篇回查');item['bucket']=f['issue_bucket'](item)
                    f['append_unique'](job['issues'],[item],'issues')
            f['append_unique'](job['parameters'],result['parameters'],'parameters')
            job['rejected']+=len(result['rejected'])
            if source!='plan':f['append_unique'](design_facts,result['parameters'],'parameters')
            cp['initialDone']=task_index+1
            complete();ids()
        if cancelled():return
        if not job['candidates']:
            for i,item in enumerate(job['issues'],1):item['candidateId']=f'C{i:03d}'
            job['candidates']=copy.deepcopy(job['issues'])
        groups=f['candidate_groups'](job['candidates']);job['total']=len(tasks)+len(groups)+1
        reviewed=cp['reviewed'];handled={cid for x in job['reviewAudit'] for cid in x['candidateIds']}
        for gi,group in enumerate(groups,1):
            if gi<=cp['reviewDone']:continue
            if cancelled():return
            job['stage']=f'全篇回查 · 第{gi}/{len(groups)}组'
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
            kept,audit=f['validate_review'](invoke(payload,{'batch':job['completed']+1,'phase':'全篇回查','source':'review','documentName':doc['name'],'candidateIds':[x['candidateId'] for x in group]}),group,refs,allowed)
            for item in kept:
                item['id']=next(x['id'] for x in group if x['candidateId'] in item['candidateIds'])
            reviewed+=kept;job['reviewAudit']+=audit;handled.update(x['candidateId'] for x in group)
            cp['reviewDone']=gi
            job['issues']=reviewed+[x for x in job['candidates'] if x['candidateId'] not in handled]
            complete();ids();stats()
        if cancelled():return
        job['stage']='合并同类问题与最终汇总'
        ids()
        compact={'任务类型':'最终汇总','方案章节目录':f['outline'](doc),
                 '设计要求':design_facts,'已提取参数':job['parameters'],'已有问题':[f['compact_issue'](x) for x in job['issues']],'重点关注':focus}
        allowed={(c['source'],c['paragraph']) for p in job['parameters']+job['issues'] for c in p['citations']}
        allowed.update(('plan',x['段号']) for x in compact['方案章节目录'])
        result=invoke(compact,{'batch':job['completed']+1,'phase':'最终汇总','source':'summary','documentName':doc['name']})
        consolidated,merges=f['validate_merges'](result,job['issues'],refs,allowed)
        extra=f['validate_result'](result,refs,allowed,focus,True)
        for item in extra['issues']:
            item=f['mark_visual'](item,refs);item.setdefault('aiReview','已全篇回查');item['bucket']=f['issue_bucket'](item)
            f['append_unique'](consolidated,[item],'issues')
        for item in consolidated:
            if item.get('mergedFrom'):item['id']=item['mergedFrom'][0]
        job['issues']=consolidated;job['mergeAudit']=merges
        f['append_unique'](job['parameters'],extra['parameters'],'parameters')
        job['rejected']+=len(extra['rejected']);job['focusResults']=extra['focusResults']
        job['issues'].sort(key=lambda x:(x.get('bucket')=='pending',x['priority'],f['CATEGORIES'].index(x['category'])));ids();stats()
        job['status']='done';job['stage']='诊断完成';cp['finished']=True
        complete()
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else '处理失败，请检查接口或资料格式。'
        if job['failedBatch'] is None:
            if job['requests']:
                job['requests'][-1].update(status='failed',error=message);job['failedBatch']=job['requests'][-1]|{'input':current_payload}
            else:job['failedBatch']=current|{'input':current_payload,'error':message}
        location=f"第{current.get('batch',job['completed']+1)}/{job['total']}批 · {current.get('phase','准备诊断')}"
        if 'paragraphStart' in current:location+=f" · 段{current['paragraphStart']}—{current['paragraphEnd']}"
        usage=job['failedBatch'].get('usage',{});used=f" 本次生成{usage['completion_tokens']} tokens。" if isinstance(usage.get('completion_tokens'),int) else ''
        job.update(status='failed',error=location+'：'+message+used,stage='诊断暂停，已完成条目保留')
    finally:
        ids();stats();job['finishedAt']=datetime.datetime.now().isoformat(timespec='seconds')

def initial_tasks(f,doc,design):
    tasks=[]
    for i,d in enumerate(design):
        for rows in f['chunks'](d):tasks.append((f'design{i+1}',d,rows))
    for rows in f['chunks'](doc):tasks.append(('plan',doc,rows))
    return tasks


def prepare_resume(f,job,doc,design):
    """恢复旧记录或新断点；只检查本地数据，不调用模型。"""
    if job.get('status')=='done':raise ValueError('本次诊断已经完成。')
    tasks=initial_tasks(f,doc,design)
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
