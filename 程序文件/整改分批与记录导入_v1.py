"""分批生成整改建议，并恢复与原方案匹配的修改记录。"""
import secrets


def install(ctx, extension):
    namespace = extension['_dispatch_v13'].__globals__
    original = namespace['generation']

    def generate(ctx, job, selected, cfg, task):
        doc = ctx['JOB_DOCS'][job['id']][0]
        rows = {row['id']: row for row in doc['rows']}
        reviews = ctx['REVIEWS'].get(job['id'], {})
        issues = []
        for issue in job['issues']:
            if issue['id'] in selected:
                issues.append({**issue, '人工修改意见': reviews.get(issue['id'], {}).get('note', '')})
        batches = []
        current = []
        size = 0
        for issue in issues:
            cost = len(str(issue)) + sum(len(rows.get(c['paragraph'], {}).get('text', '')) for c in issue['citations'] if c['source']=='plan')
            if current and (len(current)>=4 or size+cost>7500):
                batches.append(current)
                current, size = [], 0
            current.append(issue)
            size += cost
        if current:
            batches.append(current)
        local = {**ctx, 'E': {**ctx['E'], 'report': lambda *args: None}}
        edits, pending, conflicts = {}, [], set()
        try:
            for number, batch in enumerate(batches, 1):
                task.update(phase=f'正在生成第 {number}/{len(batches)} 批')
                shadow = {**job, 'issues': batch}
                part = {}
                if task.get('cancel'):
                    raise ValueError('已停止生成，原对照表保留。')
                original(local, shadow, [i['id'] for i in batch], cfg, part)
                if part.get('status')!='done':
                    reason = part.get('error') or '生成失败'
                    if number==1:
                        raise ValueError(reason)
                    pending.extend({'issueId':i['id'],'reason':f'第{number}批未生成：{reason}'} for i in batch)
                    # 接口故障后停止后续收费调用。
                    pending.extend({'issueId':i['id'],'reason':'前一批生成失败，本项尚未请求。'} for remaining in batches[number:] for i in remaining)
                    break
                draft = shadow['amendments']
                pending.extend(draft['unresolved'])
                for edit in draft['edits']:
                    pid = edit['paragraph']
                    prior = edits.get(pid)
                    if prior and prior['after']==edit['after']:
                        prior['issueIds']=list(dict.fromkeys(prior['issueIds']+edit['issueIds']))
                    elif prior or pid in conflicts:
                        conflicts.add(pid)
                        affected = edit['issueIds'] + (edits.pop(pid)['issueIds'] if prior else [])
                        pending.extend({'issueId':id,'reason':f'第{pid}段有多条不同的替换建议，请核对后合并修改。'} for id in set(affected))
                    else:
                        edits[pid]=edit
            final={'documentSha256':doc['sha256'],'edits':list(edits.values()),'unresolved':pending,'selectedIssueIds':selected}
            ctx['E']['report']({**job,'amendments':final}, reviews, ctx['JOB_DOCS'][job['id']])
            job['amendments']=final
            task.update(status='done', amendments=final)
        except Exception as error:
            task.update(status='failed',error=str(error))
    namespace['generation']=generate
    previous=extension['dispatch']
    def dispatch(ctx,path,data):
        if path.endswith('/import-amend-log'):
            job=ctx['JOBS'][data['id']]
            doc=ctx['JOB_DOCS'][job['id']][0]
            log=data['record']
            if not doc or log.get('originalSha256')!=doc['sha256']:
                raise ValueError('请先打开对应的审查记录并关联同一份原方案。')
            if job.get('status')=='running' or any(t.get('jobId')==job['id'] and t.get('status')=='running' for t in extension['OPERATIONS'].values()):
                raise ValueError('请等当前任务结束后导入。')
            rows={r['id']:r for r in doc['rows']}
            known={i['id']:i for i in job['issues']}
            edits=[]; seen=set()
            for x in log.get('edits',[]):
                pid=x['paragraph']; row=rows.get(pid)
                if not row or pid in seen or x['before']!=row['text'] or not row.get('editAnchor') or not isinstance(x.get('after'),str) or not x['after'].strip() or '\n' in x['after'] or '\r' in x['after']:
                    raise ValueError('修改记录的段落、原文或替换文本不匹配。')
                ids=x.get('issueIds',[])
                if not ids or any(id not in known or not any(c['source']=='plan' and c['paragraph']==pid for c in known[id]['citations']) for id in ids):
                    raise ValueError('问题编号或引用位置不匹配，请选择生成这份修改记录的审查结果。')
                seen.add(pid)
                edits.append({**x,'editId':secrets.token_hex(6),'selected':True,'location':row.get('location') or row.get('section','')})
            if not edits:raise ValueError('文件没有可恢复的替换内容。')
            draft={'documentSha256':doc['sha256'],'edits':edits,'unresolved':[],'selectedIssueIds':list(dict.fromkeys(id for x in edits for id in x['issueIds']))}
            ctx['E']['report']({**job,'amendments':draft},ctx['REVIEWS'].get(job['id'],{}),ctx['JOB_DOCS'][job['id']])
            job['amendments']=draft
            return draft
        return previous(ctx,path,data)
    extension['dispatch']=dispatch

