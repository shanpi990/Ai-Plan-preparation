"""恢复诊断记录和原文；不调用模型。"""
import copy, re, runpy, secrets, hashlib, json
from pathlib import Path
LOC=runpy.run_path(str(Path(__file__).with_name("Word章节定位_v10.py")))


def source_slot(source,job):
    if source=='plan':return 0
    if isinstance(source,str) and re.fullmatch(r'design[1-9]\d*',source):
        index=int(source[6:])
        if index<=len(job['design']):return index
    raise ValueError('原文来源编号不正确。')


def source_status(job,docs):
    return [{'source':'plan' if i==0 else f'design{i}','name':d['name'],'linked':docs[i] is not None}
            for i,d in enumerate([job['document']]+job['design'])]


def matching_citations(job,index,doc):
    source='plan' if index==0 else f'design{index}'
    rows={r['id']:r['text'] for r in doc['rows']}
    normal=lambda s:re.sub(r'\s+','',s)
    for item in job['issues']+job['parameters']:
        for cite in item['citations']:
            if cite['source']==source and normal(cite['quote']) not in normal(rows.get(cite['paragraph'],'')):
                raise ValueError('原文段号与记录引用不一致，请选择诊断时使用的原文件。')
    return doc


def bind_source(job,index,name,raw,root,engine):
    expected=([job['document']]+job['design'])[index]
    if hashlib.sha256(raw).hexdigest()!=expected.get('sha256'):
        raise ValueError('文件与该记录的原文件不一致，请选择诊断时使用的文件。')
    # 旧记录使用当时的解析器恢复段号，避免新版表格/图片解析改变定位。
    parser=engine if expected.get('parserVersion')=='v6' else runpy.run_path(str(root/'AI诊断引擎_v5.py'))
    doc=parser['parse_document'](expected['name'],raw)
    if Path(expected['name']).suffix.lower()=='.docx' and doc.get('locationVersion')!='v10':doc=LOC['enrich_docx'](doc,raw)
    return matching_citations(job,index,doc)


def import_record(record,available,raw_docs,root):
    if not isinstance(record,dict) or not isinstance(record.get('diagnosis'),dict):
        raise ValueError('请选择“保存复核记录”生成的JSON文件。')
    job=copy.deepcopy(record['diagnosis']);reviews=copy.deepcopy(record.get('reviews',{}))
    if not isinstance(job.get('document'),dict) or not isinstance(job['document'].get('name'),str):
        raise ValueError('记录缺少方案信息。')
    defaults={'design':[],'issues':[],'parameters':[],'focus':[],'focusResults':[],'requests':[],'error':'','model':'未记录','completed':0,'total':0,'rejected':0,'stage':'已导入结果'}
    for key,value in defaults.items():job.setdefault(key,value)
    for key in ('design','issues','parameters','focus','focusResults','requests'):
        if not isinstance(job[key],list):raise ValueError('记录中的'+key+'格式错误。')
    if any(not isinstance(d,dict) or not isinstance(d.get('name'),str) for d in job['design']):raise ValueError('设计资料信息不完整。')
    if any(not isinstance(x,str) for x in job['focus']):raise ValueError('关注项格式错误。')
    ids=set()
    for issue in job['issues']:
        if not isinstance(issue,dict) or issue.get('category') not in ('内容缺项','技术性错误','前后矛盾','与本项目条件不符','错别字与表述问题') or issue.get('priority') not in ('A','B','C','D'):
            raise ValueError('问题分类或优先级格式错误。')
        if not isinstance(issue.get('id'),str) or not re.fullmatch(r'Q[0-9]+',issue['id']) or issue['id'] in ids:raise ValueError('问题编号缺失或重复。')
        ids.add(issue['id'])
        for key in ('title','description','suggestion','priorityReason'):
            if not isinstance(issue.get(key),str):raise ValueError('问题文字信息不完整。')
    for parameter in job['parameters']:
        if not isinstance(parameter,dict) or any(not isinstance(parameter.get(k),str) for k in ('name','value','scope')):raise ValueError('参数信息不完整。')
    for item in job['issues']+job['parameters']:
        if not isinstance(item.get('citations'),list) or not item['citations']:raise ValueError('记录条目缺少原文引用。')
        for c in item['citations']:
            if not isinstance(c,dict) or not isinstance(c.get('paragraph'),int) or c['paragraph']<1 or not isinstance(c.get('quote'),str) or not c['quote'].strip():raise ValueError('原文引用格式错误。')
            source_slot(c.get('source'),job)
            c.setdefault('section','');c.setdefault('page',None)
    if not isinstance(reviews,dict):raise ValueError('人工复核记录格式错误。')
    for key,value in reviews.items():
        if key not in ids or not isinstance(value,dict) or value.get('status') not in ('待复核','确认修改','退回补查','不采纳','已修改') or not isinstance(value.get('note',''),str):raise ValueError('人工复核意见格式错误。')
    for key in ('completed','total','rejected'):
        if not isinstance(job[key],int) or job[key]<0:raise ValueError('诊断进度格式错误。')
    if any(not isinstance(x,dict) or any(not isinstance(x.get(k),str) for k in ('focus','status','summary')) for x in job['focusResults']):raise ValueError('关注项结果格式错误。')
    job.setdefault('status','done')
    previous=job['status']
    if previous=='running':job.update(status='cancelled',stage='已导入未完成记录，已完成条目保留')
    elif previous not in ('done','failed','cancelled'):raise ValueError('诊断状态格式错误。')
    # 旧版只保存本地起止时间。已核实的历史用时按运行记录匹配，避开同方案的其他审查。
    if previous == 'done' and 'activeReviewSeconds' not in job:
        times_path = root.parent / '运行数据' / '历史审查用时_v1.json'
        try:
            times = json.loads(times_path.read_text('utf-8-sig'))
        except (OSError, ValueError):
            times = {}
        entry = times.get(str(job.get('checkpointKey') or job.get('id'))) if isinstance(times, dict) else None
        if isinstance(entry, dict) and (entry.get('documentSha256'), entry.get('finishedAt'), entry.get('requests')) == (
            job['document'].get('sha256'), job.get('finishedAt'), len(job['requests'])
        ) and type(entry.get('activeReviewSeconds')) in (int, float) and entry['activeReviewSeconds'] >= 0:
            job['activeReviewSeconds'] = entry['activeReviewSeconds']
    job['id']=secrets.token_hex(8);job['cancel']=False;job['imported']=True
    for key in ('saveError','savedPath'):job.pop(key,None)
    snapshots=record.get('sourceDocuments',[])
    if not isinstance(snapshots,list):raise ValueError('原文快照格式错误。')
    docs=[];engine=None
    for index,expected in enumerate([job['document']]+job['design']):
        sha=expected.get('sha256')
        if sha not in raw_docs:
            reference=(root.parent/'参考文件'/Path(expected['name']).name).resolve()
            if reference.is_file() and reference.is_relative_to((root.parent/'参考文件').resolve()):
                raw=reference.read_bytes()
                if hashlib.sha256(raw).hexdigest()==sha:raw_docs[sha]=raw
        snapshot=snapshots[index] if index<len(snapshots) else None
        if sha in raw_docs and (snapshot is None or snapshot.get('locationVersion')!='v10' or (snapshot.get('imagesBySource') and snapshot.get('visuals'))):
            if engine is None:engine=runpy.run_path(str(root/'AI诊断引擎_v10.py'))
            snapshot=bind_source(job,index,expected['name'],raw_docs[sha],root,engine)
        if snapshot is not None:
            if not isinstance(snapshot,dict) or snapshot.get('sha256')!=expected.get('sha256') or not isinstance(snapshot.get('rows'),list):raise ValueError('原文快照与记录不一致。')
            if any(not isinstance(r,dict) or not isinstance(r.get('id'),int) or not isinstance(r.get('text'),str) for r in snapshot['rows']):raise ValueError('原文快照段落格式错误。')
            docs.append(matching_citations(job,index,snapshot));continue
        sha=expected.get('sha256');doc=available.get(sha)
        if doc is not None:
            try:
                if expected.get('parserVersion')=='v6':doc=matching_citations(job,index,doc)
                elif sha in raw_docs:
                    if engine is None:engine=runpy.run_path(str(root/'AI诊断引擎_v10.py'))
                    doc=bind_source(job,index,expected['name'],raw_docs[sha],root,engine)
                else:doc=None
            except ValueError:doc=None
        docs.append(doc)
    LOC['refresh_job'](job,docs)
    return job,reviews,docs
