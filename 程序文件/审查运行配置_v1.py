import json, os, re, uuid, datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
CONFIG=ROOT/'配置文件/审查运行配置_v1.json'

def parallel_limit(value):
    if type(value) is not int or not 1 <= value <= 10:
        raise ValueError('并发请求数应为 1～10 的整数。')
    return value

def initial_waves(plan_visual, design_batches, lanes, visual_limit):
    """每轮按入队顺序占用请求槽；设计批次逐个完成后才开始正文。"""
    waves = design_batches
    occupied = images = 0
    for visual in plan_visual:
        if occupied == lanes or (visual and images == visual_limit):
            waves += 1
            occupied = images = 0
        occupied += 1
        images += int(visual)
    return waves + int(occupied > 0)


def recent_initial_seconds():
    records = ROOT/'审查记录'
    paths = sorted((p for p in records.glob('*.json') if not p.name.startswith('审查断点_')),
                   key=lambda p:p.stat().st_mtime,reverse=True)
    for path in paths:
        try:
            job = json.loads(path.read_text('utf-8-sig'))['diagnosis']
            if job.get('status') != 'done':
                continue
            measured = job.get('initialAverageSeconds')
            if isinstance(measured, (int,float)) and measured > 0:
                return measured
            values = [r['requestSeconds'] for r in job.get('requests',[]) if r.get('phase')=='正文初审'
                      and r.get('status')=='completed' and isinstance(r.get('requestSeconds'),(int,float))]
            if values:
                return sum(values)/len(values)
            history = ROOT/'运行数据/历史审查用时_v1.json'
            if history.is_file():
                entry = json.loads(history.read_text('utf-8-sig')).get(job.get('checkpointKey'),{})
                if entry.get('documentSha256')==job.get('document',{}).get('sha256'):
                    return entry.get('initialBatchSeconds',90)
        except (OSError,ValueError,KeyError,TypeError):
            continue
    return 90

def settings():
    result=json.loads(CONFIG.read_text('utf-8-sig'))
    if result['模型请求日志'] not in ('关闭','仅失败请求','全部'):raise ValueError('请核对模型请求日志模式。')
    if type(result['日志保留天数'])!=int or result['日志保留天数']<0:raise ValueError('日志保留天数应为非负整数。')
    if type(result['初审批次字符上限'])!=int or result['初审批次字符上限']<=0:raise ValueError('初审批次字符上限应为正整数。')
    return result

def log_root():
    return Path(os.environ.get('SCHEME_REVIEW_LOG_DIR') or ROOT/'运行数据/模型请求日志')

def archive_expired():
    root=log_root()
    if not root.is_dir():return
    cutoff=datetime.date.today()-datetime.timedelta(days=settings()['日志保留天数'])
    for day in root.iterdir():
        if not day.is_dir() or day.is_symlink() or not re.fullmatch(r'\d{4}-\d\d-\d\d',day.name):continue
        try:log_day=datetime.date.fromisoformat(day.name)
        except ValueError:continue
        if log_day>cutoff:continue
        for item in day.glob('*_模型请求_*.json'):
            if item.is_symlink():continue
            dest=root/'到期归档'/day.name/item.name
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():item.rename(dest)

def save_log(record,failed):
    mode=settings()['模型请求日志']
    if mode=='关闭' or (not failed and mode!='全部'):return
    # 只在确需写日志时复制图像消息，图片字节保留在关联原件中。
    if 'request' in record:
        import copy
        record=dict(record,request=copy.deepcopy(record['request']))
        for message in record['request'].get('messages',[]):
            if isinstance(message.get('content'),list):
                for block in message['content']:
                    if block.get('type')=='image_url':block['image_url']['url']='[图片已省略]'
    now=datetime.datetime.now()
    folder=log_root()/now.date().isoformat()
    folder.mkdir(parents=True,exist_ok=True)
    name=now.strftime('%m%d_模型请求_%H%M%S%f_')+uuid.uuid4().hex[:10]+'.json'
    (folder/name).write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')

def snapshot(job,reviews,docs):
    # 原文行用于离线查看，图片字节由 sha256 已核对的原件恢复。
    def without_images(doc):
        if not doc or 'visuals' not in doc:return doc
        visuals=[]
        for v in doc['visuals']:
            digest=v.get('sha256')
            if not digest and v.get('dataUrl'):
                import base64,hashlib
                digest=hashlib.sha256(base64.b64decode(v['dataUrl'].partition(',')[2])).hexdigest()
            visuals.append({'id':v['id'],**({'sha256':digest} if digest else {})})
        return dict(doc,visuals=visuals,imagesBySource=True)
    saved=dict(job)
    saved.pop('progressCompleted',None)
    if 'document' in job:saved['document']=without_images(job['document'])
    if 'design' in job:saved['design']=[without_images(d) for d in job['design']]
    return {'diagnosis':saved,'reviews':reviews,'sourceDocuments':[without_images(d) for d in docs or ()]}

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,separators=(',',':'))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp,path)

def checkpoint_path(folder,job):
    key=job.get('checkpointKey') or job['id']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key):raise ValueError('断点任务编号无效。')
    return folder/('审查断点_'+key+'.json')
