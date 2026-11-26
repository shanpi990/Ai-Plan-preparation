"""A2 瓦片进程池；图幅灰度与完成瓦片按文件摘要、页码及阈值复用。"""
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
from pathlib import Path
from collections import deque
import hashlib,json,os,time,unicodedata,runpy
engine=None
def init_worker():
    global engine
    import cv2
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from rapidocr_onnxruntime import RapidOCR
    from rapidocr_onnxruntime.utils.infer_engine import OrtInferSession
    cv2.setNumThreads(1)
    default_options=OrtInferSession._init_sess_opts
    def model_options(config):
        opts=default_options(config)
        if 'rec' in Path(config['model_path']).stem.lower():
            opts.enable_cpu_mem_arena=True
        return opts
    # 每个独立工作进程仅初始化一套模型；识别行沿用同一分配器。
    OrtInferSession._init_sess_opts=staticmethod(model_options)
    try:
        engine=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1,Det_limit_side_len=2000)
    finally:
        OrtInferSession._init_sess_opts=staticmethod(default_options)
def worker(task):
    import numpy as np,cv2
    kind,path,items=task;gray=np.load(path,mmap_mode='r');height,width=gray.shape
    if kind=='tile':
        x,y=items;result,_=engine(gray[y:y+2000,x:x+2000],use_cls=False,use_rec=False,box_thresh=.42);out=[]
        for pts in result if result is not None else []:
            a=np.asarray(pts).reshape(-1,2);xx,yy=a.min(axis=0);rr,bb=a.max(axis=0)
            if rr-xx>4 and bb-yy>6:out.append([max(0,int(xx+x)),max(0,int(yy+y)),min(width,int(rr+x+1)),min(height,int(bb+y+1))])
        return out
    rows=[]
    for i,(x,y,r,b) in items:
        roi=gray[max(0,y-2):min(height,b+2),max(0,x-2):min(width,r+2)]
        if not roi.size:continue
        rec,_=engine.text_rec([cv2.cvtColor(cv2.resize(roi,None,fx=1.35,fy=1),cv2.COLOR_GRAY2BGR)])
        if rec:
            value,score=rec[0][:2];v=unicodedata.normalize('NFKC',value).strip()
            if v:rows.append((i,v,round(float(score),4),[round(z/(300/72),2) for z in (x,y,r,b)]))
    return rows
def process(pages,n,job,cancelled,onpage):
    import pymupdf as fitz
    import numpy as np
    lib=runpy.run_path(str(Path(__file__).with_name('图纸分块OCR.py')))
    start=time.monotonic();states=[];total=0;done=0
    for spec in pages:
        path,number,threshold,cache=spec['file'],spec['page'],spec.get('threshold',165),Path(spec['cache'])
        cache.mkdir(parents=True,exist_ok=True);grayfile=cache/'灰度.npy';step=300/72
        with fitz.open(path) as pdf:
            pg=pdf[number-1];size=[pg.rect.width,pg.rect.height];native=pg.get_text(sort=True).strip()
            if not grayfile.exists():
                pix=pg.get_pixmap(matrix=fitz.Matrix(step,step),colorspace=fitz.csGRAY,alpha=False);gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
                tmp=cache/'写入灰度.npy';np.save(tmp,np.where(gray>threshold,255,gray).astype(np.uint8));os.replace(tmp,grayfile)
        height,width=np.load(grayfile,mmap_mode='r').shape;tiles=[(x,y) for y in lib['starts'](height) for x in lib['starts'](width)]
        checkpoint=cache/'瓦片.json';boxes=json.loads(checkpoint.read_text('utf8')) if checkpoint.exists() else {}
        st=dict(spec=spec,gray=str(grayfile),tiles=tiles,checkpoint=checkpoint,boxes=boxes,size=size,width=width,native=native,lines=[],finished=False,recfile=cache/"识别行组.json",rec={})
        if st["recfile"].exists():st["rec"]=json.loads(st["recfile"].read_text("utf8"))
        states.append(st);total+=len(tiles);done+=len(boxes)
    job.update(document=pages[0].get('document'),page=pages[0]['page'],total=len(states),completed=0,parallel=n,tileCount=total,tile=done,cachedTiles=done,cachedRowGroups=0);pool=ProcessPoolExecutor(max_workers=n,initializer=init_worker)
    pending={};queue=deque();finished=0
    def submit_rows(i):
        st=states[i];boxes=lib['join_boxes']([box for k in range(len(st['tiles'])) for box in st['boxes'][str(k)]],st['width'])
        st['groups']=(len(boxes)+11)//12
        for k in range(0,len(boxes),12):
            if str(k) in st['rec']:
                st['lines'].extend(st['rec'][str(k)]);st['groups']-=1;job['cachedRowGroups']+=1
            else:queue.append(('rows',i,list(enumerate(boxes[k:k+12],k))))
        if not st['groups']:publish(i)
    def publish(i):
        nonlocal finished
        st=states[i];rows=[dict(text=v,confidence=sc,page=st['spec']['page'],bbox=box) for _,v,sc,box in sorted(st['lines'], key=lambda row: row[0])]
        raw='\n'.join(a['text'] for a in rows);item=dict(page=st['spec']['page'],text=(st['native']+'\n' if st['native'] and not st['spec'].get('force') else '')+raw,rawOCR=raw,lines=rows,confidence=sum(a['confidence'] for a in rows)/max(1,len(rows)),method='300 dpi 并行分块本地OCR',empty=not rows,pageSize=st['size'],threshold=st['spec'].get('threshold',165),tiles=len(st['tiles']),seconds=round(time.monotonic()-start,3))
        onpage(st['spec'],item);finished+=1;job['completed']=finished
    try:
        for k in range(max((len(st['tiles']) for st in states),default=0)):
            for i,st in enumerate(states):
                if k<len(st['tiles']) and str(k) not in st['boxes']:queue.append(('tile',i,k))
        for i,st in enumerate(states):
            if len(st['boxes'])==len(st['tiles']):submit_rows(i)
        job.update(document=pages[0].get('document'),page=pages[0]['page'])
        while queue or pending:
            cancelled(job)
            while queue and len(pending)<n*2:
                kind,i,k=queue.popleft();st=states[i];f=pool.submit(worker,(kind,st['gray'],st['tiles'][k] if kind=='tile' else k));pending[f]=(kind,i,k)
            ready,_=wait(pending,timeout=.4,return_when=FIRST_COMPLETED)
            for f in ready:
                kind,i,k=pending.pop(f);st=states[i];res=f.result()
                if kind=='tile':
                    st['boxes'][str(k)]=res;tmp=st['checkpoint'].with_suffix('.partial');tmp.write_text(json.dumps(st['boxes']),'utf8');os.replace(tmp,st['checkpoint']);done+=1
                    if len(st['boxes'])==len(st['tiles']):submit_rows(i)
                else:
                    st['rec'][str(k[0][0])]=res;tmp=st['recfile'].with_suffix('.partial');tmp.write_text(json.dumps(st['rec'],ensure_ascii=False),'utf8');os.replace(tmp,st['recfile'])
                    st['lines'].extend(res);st['groups']-=1
                    if st['groups']==0:publish(i)
                job.update(document=st['spec'].get('document'),page=st['spec']['page'],tile=done,phase=f"第 {i+1}/{len(states)} 张 · 瓦片 {done}/{total} · 并行 {n} 路 · 已用 {time.monotonic()-start:.0f} s")
    finally:pool.shutdown(wait=True,cancel_futures=True)
