"""送审包待补覆盖判定，以及带编制处理证据的复审对比。"""
import re
import unicodedata
from collections import Counter, defaultdict

NUMBER = re.compile(r'[图表]\d+(?:\.\d+)*(?:[-－—–]\d+)+')
EXCLUDE = re.compile(r'文字错误|错别字|编号与题注|占位未替换|前后矛盾|做法错误|技术性错误|表述不规范|规范依据不符|与本项目条件不符')
EDITORIAL = re.compile(r'误写|错别字|编号错位|编号跳号|引用无着落|依据不符|规范.*引用错误|站名未替换')
OBJECT = re.compile(r'建构筑物|构筑物|管线|机械设备|施工机械|联系方式|承压水|地下水位|支撑轴力|预加轴力|预加力|井点|稳压|吊机|轴线|围檩|层顶标高|层底标高|荷载|预警值|报警值|焊缝|止水帷幕|围护桩|支撑标高|支撑道数|劳动力|流程图|应急组织')
PENDING_GUIDE = ('在最终 JSON 顶层返回 pendingDecisions 数组，每条含 issueId、pendingId、coverage、reason。'
    '只在所列候选中选择一项。综合意见标题、说明列出的每个独立缺项和交付内容。登记项目能交付意见所需的全部内容才为 full。'
    'reason 必须具体说明将交付什么、覆盖了意见的哪些要求。尚有要求未覆盖则为 partial 并指出缺口；'
    '无实质关联则省略。逐项区分意见指出的实际缺项，以及「无法判断/核验/指导」等后果。后果本身不另算交付物；'
    '恢复该处查验所需资料已足够时，不额外要求分析报告。若意见明确要求改表题、工序或另作验算，则分别判断。'
    '只据列出的登记内容作答，不推定一项概括性勘察资料必然含有某一土层、试验或实测数值。')
GROUPS = (('fixed','已整改'),('still','仍存在'),('rejectedAgain','不采纳后再次报出'),
          ('unreported','本次未报出（未整改）'),('new','新出现'))

def norm(s):
    return ''.join(unicodedata.normalize('NFKC',str(s or '')).lower().split()).replace('－','-').replace('—','-').replace('–','-')

def positions(i):
    return {c['paragraph'] for c in i.get('citations',[]) if c.get('source')=='plan' and type(c.get('paragraph')) is int}

def kinds(t):
    result=set()
    if re.search(r'表|汇总|清单|设备明细|联系方式',t):result.add('资料表')
    if re.search(r'图|绘制',t):result.add('图')
    if re.search(r'勘察|实测|资料|参数|指标|水位|地质|数据',t):result.add('文字资料')
    if re.search(r'选型|选用|决策|方案比选',t):result.add('决策')
    return result

def numbers(t):
    return set(NUMBER.findall(norm(t)))

def candidates(i,pending):
    if EXCLUDE.search(i.get('category','')) or EDITORIAL.search(i.get('title','')):return []
    title=norm(i.get('title'))
    content=title+' '+norm(i.get('description'))
    kinds_issue=kinds(content)
    para=positions(i)
    ranked=[]
    for p in pending:
        name=norm(p['title'])
        deliver=norm(p.get('deliverable') or name)
        names=[name,*(norm(x) for x in p.get('objects',[]) if isinstance(x,str))]
        shared_num=numbers(content)&numbers(deliver+' '+' '.join(names))
        shared_obj=set(OBJECT.findall(content))&set(OBJECT.findall(deliver+' '+name))
        named=any(len(x)>=3 and not NUMBER.fullmatch(x) and x in content for x in names)
        overlap=bool(para.intersection((p.get('paragraphs') or [])+[p.get('paragraph')]))
        typed={p['kind']} if p.get('kind') else {'图' if p.get('type')=='图' else '决策'} if p.get('type') in ('图','决策') else kinds(name) or {'文字资料'}
        if not (named or shared_num or shared_obj or overlap and typed&kinds_issue):continue
        score=(bool(shared_num),named,len(shared_obj),overlap and bool(typed&kinds_issue),overlap)
        ranked.append((score,p))
    ranked.sort(key=lambda x:x[0],reverse=True)
    return [p for _,p in ranked[:3]]

def proposal(issues, pending):
    rows=[]
    for i in issues:
        options=candidates(i,pending)
        if options:
            rows.append(dict(issueId=i['id'],title=i['title'],description=i.get('description',''),
                candidates=[dict(pendingId=p['id'],title=p['title'],deliverable=p.get('deliverable') or p['title'],
                                 kind=p.get('kind') or p.get('type','')) for p in options]))
    return rows

def concrete(a,b):
    return any(s[n:n+3] in norm(b) for s in re.findall(r'[\w]+',norm(a)) for n in range(len(s)-2))

def resolve(rows,decisions):
    by_id={r['issueId']:r for r in rows}
    result={}
    if not isinstance(decisions,list):return result
    counts=Counter(d['issueId'] for d in decisions if isinstance(d,dict) and isinstance(d.get('issueId'),str))
    for d in decisions:
        if not isinstance(d,dict) or not isinstance(d.get('issueId'),str):continue
        i=by_id.get(d['issueId'])
        if not i or counts[d['issueId']]!=1:continue
        p=next((p for p in i['candidates'] if p['pendingId']==d.get('pendingId')),None)
        coverage=d.get('coverage')
        if not p or coverage not in ('partial','full'):continue
        reason=d.get('reason') if isinstance(d.get('reason'),str) else ''
        if coverage=='full' and (not concrete(reason,p['deliverable']+p['title']) or
                not concrete(reason,i['title']+i['description']) or len(norm(reason))<12):
            coverage='partial'
            reason='覆盖说明未具体交代登记交付物和意见要求。'
        result[d['issueId']]=dict(id=p['pendingId'],coverage=coverage,reason=reason or '仅覆盖部分要求。')
    return result

def apply_links(job,rows,decisions):
    links=resolve(rows,decisions)
    sent={r['issueId']:r for r in rows}
    for i in job['issues']:
        r=sent.get(i['id'])
        reason='没有符合类别与对象条件的登记项。' if not r else '候选登记项未获得有效覆盖结论。'
        i['bianshenPending']=dict(id=None,coverage='none',reason=reason)
        # 合并或改写的意见必须以最终文本判断，旧结论仅限原样保留的意见。
        if r and i['id'] in links and r['title']==i['title'] and r['description']==i.get('description',''):
            i['bianshenPending']=links[i['id']]
    job['bianshenCoverageVersion']=2
    summarize(job)

def summarize(job):
    full=[i for i in job['issues'] if (i.get('bianshenPending') or {}).get('coverage')=='full']
    counts=Counter(i['priority'] for i in job['issues'] if i not in full)
    job['bianshenSummary']=dict(version=2,registered=len({i['bianshenPending']['id'] for i in full}),
        linkedIssues=len(full),partial=sum((i.get('bianshenPending') or {}).get('coverage')=='partial' for i in job['issues']),
        newPriorities={k:counts[k] for k in 'ABCD'})

def evidence(doc,pack):
    rows={x['id']:x for x in doc.get('rows',[])}
    anchors={x['paragraph']:x.get('blockId','') for x in pack.get('paragraphMap',[]) if isinstance(x,dict) and type(x.get('paragraph')) is int}
    return rows,anchors

def signatures(issue,context):
    rows,anchors=context
    pos=positions(issue)
    blocks={anchors[n] for n in pos if anchors.get(n)}
    table=[]
    for n in pos:
        row=rows.get(n,{})
        if row.get('table') and row.get('tableCaption'):
            table.append((norm(row['tableCaption']),n, anchors.get(n)))
    return blocks,table

def pair_local(old,new,old_ctx,new_ctx):
    matches=[]
    for a in old:
        ab,at=signatures(a,old_ctx)
        for b in new:
            bb,bt=signatures(b,new_ctx)
            common=len(ab&bb)
            close=any(t==u and abs(n-m)<=2 for t,n,_ in at for u,m,_ in bt)
            ta,tb=norm(a['title']),norm(b['title'])
            same=ta==tb
            ids=numbers(ta)&numbers(tb)
            objects=set(OBJECT.findall(ta))&set(OBJECT.findall(tb))
            quotes=lambda x:{norm(c['quote']) for c in x.get('citations',[]) if c.get('source')=='plan' and c.get('quote')}
            q=len(quotes(a)&quotes(b))
            if not (common or close or same and q):continue
            cat=a.get('category')==b.get('category')
            if not (cat or same or ids or objects):continue
            grams=lambda s:{s[i:i+2] for i in range(len(s)-1)}
            affinity=len(grams(ta)&grams(tb))/max(1,len(grams(ta)|grams(tb)))
            matches.append(((same,bool(ids),len(objects),cat,common,q,affinity),a['id'],b['id']))
    used_a,used_b=set(),set()
    pairs=[]
    for score,a,b in sorted(matches,reverse=True):
        if a in used_a or b in used_b:continue
        if any(s==score and (x==a or y==b) and (x,y)!=(a,b) for s,x,y in matches):continue
        pairs.append((a,b,'段落定位及类别或对象匹配'));used_a.add(a);used_b.add(b)
    return pairs

def brief(i):
    return dict(id=i['id'],title=i['title'],description=i.get('description','')[:80],paragraphs=sorted(positions(i)))

def actual_edit(issue,decision,old_ctx,new_ctx):
    if decision.get('status')!='已采纳':return None
    before,after=decision.get('before'),decision.get('after')
    if not before or not after or before.strip()==after.strip():return None
    block,n=decision.get('blockId'),decision.get('paragraph')
    old_rows,old_map=old_ctx
    new_rows,new_map=new_ctx
    if not block or not n or old_rows.get(n,{}).get('text')!=before:return None
    if old_map.get(n) and old_map[n]!=block:return None
    if n not in positions(issue) and not any(old_map.get(k)==block for k in positions(issue)):return None
    matched=[k for k,v in new_map.items() if v==block and new_rows.get(k,{}).get('text')==after]
    if len(matched)==1:return dict(blockId=block,previousParagraph=n,paragraph=matched[0],before=before,after=after)

def compare(previous,issues,handled,old_ctx,new_ctx,ask=None):
    decisions={x.get('issueId'):x for x in handled if isinstance(x,dict)}
    pairs=pair_local(previous,issues,old_ctx,new_ctx)
    old_ids={x for x,_,_ in pairs};new_ids={y for _,y,_ in pairs}
    left={i['id']:i for i in previous if i['id'] not in old_ids}
    right={i['id']:i for i in issues if i['id'] not in new_ids}
    if left and right and ask:
        reply=ask(dict(previous=[brief(i) for i in left.values()],current=[brief(i) for i in right.values()]))
        entries=reply.get('pairs',[])
        valid=[d for d in entries if isinstance(d,dict) and d.get('same') is True and isinstance(d.get('reason'),str) and d['reason'].strip()
               and isinstance(d.get('old'),str) and d['old'] in left and isinstance(d.get('new'),str) and d['new'] in right] if isinstance(entries,list) else []
        count_a=Counter(d['old'] for d in valid);count_b=Counter(d['new'] for d in valid)
        for d in valid:
            if count_a[d['old']]==count_b[d['new']]==1:pairs.append((d['old'],d['new'],d['reason']))
    old={i['id']:i for i in previous};new={i['id']:i for i in issues}
    result={k:[] for k,_ in GROUPS}
    for b in new.values():b.pop('previousRejection',None)
    for a,b,why in pairs:
        decision=decisions.get(a,{})
        row=dict(previousId=a,id=b,title=new[b]['title'],matchReason=why)
        if decision.get('status')=='不采纳':
            row['reason']=decision.get('note') or decision.get('reason') or '原因未登记'
            new[b]['previousRejection']=row['reason']
            group='rejectedAgain'
        else:
            row['acceptedAgain']=decision.get('status')=='已采纳'
            group='still'
        result[group].append(row)
    paired={a for a,_,_ in pairs}
    for k,i in old.items():
        if k in paired:continue
        proof=actual_edit(i,decisions.get(k,{}),old_ctx,new_ctx)
        result['fixed' if proof else 'unreported'].append(dict(id=k,title=i['title'],**(proof or {})))
    paired={b for _,b,_ in pairs}
    result['new']=[dict(id=k,title=i['title']) for k,i in new.items() if k not in paired]
    return dict(version=2,**result)

