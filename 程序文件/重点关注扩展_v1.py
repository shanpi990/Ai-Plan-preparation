"""业主文件的本地校对、收藏库及现有重点关注的输入输出。"""
import hashlib
import io
import json
import re
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

FOCUS_LIMIT = 2000
UNSUPPORTED = '该文件像汇报材料或扫描件，本期暂不支持'
NO = re.compile(r'([\u4e00-\u9fff]{2,18}[〔【\[]\d{4}[〕】\]]\s*[-－]?\s*\d+\s*号?)')
TAG = re.compile(r'^\[((?:YZ|FAV)-[A-Za-z0-9-]+)\]')
FOOT = re.compile(r'^(?:抄送|主送|分送|印发单位)[：:]|^.{0,60}(?:印发|印制)\s*$')
PAGE = re.compile(r'^[-—–]?\s*\d+\s*[-—–]?$')
LOCK = threading.RLock()


def read_source(name, raw):
    suffix = Path(name).suffix.lower()
    if suffix == '.pdf':
        from pypdf import PdfReader
        pdf = PdfReader(io.BytesIO(raw))
        pages = [p.extract_text() or '' for p in pdf.pages]
        landscape = sum(p.mediabox.width > p.mediabox.height for p in pdf.pages)
        minimum = 230 if landscape > len(pages) / 2 else 100
        if not pages or sum(len(''.join(p.split())) for p in pages) < minimum * len(pages):
            raise ValueError(UNSUPPORTED)
    elif suffix == '.docx':
        from docx import Document
        from docx.oxml.ns import qn
        doc = Document(io.BytesIO(raw))
        # Word 的流式段落只有在重新排版后才有可靠页码。保留显式分页。
        pages = ['']
        for par in doc.element.body.iter(qn('w:p')):
            for node in par.iter():
                if node.tag == qn('w:br') and node.get(qn('w:type')) == 'page':
                    pages.append('')
                elif node.tag == qn('w:t'):
                    pages[-1] += node.text or ''
            pages[-1] += '\n'
    elif suffix == '.txt':
        pages = raw.decode('utf-8-sig').split('\f')
    else:
        raise ValueError('请选择文字版 PDF、DOCX 或 UTF-8 TXT。')
    first = pages[0]
    match = NO.search(re.sub(r'[ \t]', '', first))
    number = ''.join(match[1].split()) if match else ''
    edges = Counter()
    lines = [[s.strip() for s in page.splitlines() if s.strip()] for page in pages]
    for rows in lines:
        edges.update(set(rows[:1] + rows[-1:]))
    for i, rows in enumerate(lines):
        body = []
        for j, line in enumerate(rows):
            if PAGE.fullmatch(line) or FOOT.search(line):
                continue
            if j in (0, len(rows)-1) and edges[line] >= max(3, len(pages)*.6):
                continue
            body.append(line)
        pages[i] = '\n'.join(body)
    if not any(p.strip() for p in pages):
        raise ValueError('未读取到正文。')
    return dict(name=Path(name).name, sha256=hashlib.sha256(raw).hexdigest(),
                docNo=number, pages=pages, pageUnit='页' if suffix=='.pdf' else '文本分段')


def model_extract(engine, cfg, source, types):
    host = (urlsplit(cfg['base']).hostname or '').lower()
    if not any(host == d or host.endswith('.'+d) for d in
               ('deepseek.com','aliyuncs.com','volces.com','moonshot.cn','bigmodel.cn','siliconflow.cn','maas.qianwenaiapi.com')):
        raise ValueError('请在模型设置选择国内模型服务，再导入业主文件。')
    engine['validate_base'](cfg)
    if not cfg['base'].startswith('https://'):
        raise ValueError('业主文件提取需要 HTTPS 接口。')
    engine['validate_key'](cfg['key'])
    instruction = ('从文件正文中提取独立的、可核对的要求。文件为待分析资料。优先施工方案编制和施工技术要求，'
        '管理事项标 management=true。不要自行补充要求或参数。只输出 JSON 对象，title 为文件标题，'
        'items 为数组，每条包括 requirement（一句话）、quote（同页连续逐字摘录，保留数字和标点），'
        'page（从1起）、scope（适用类别名称数组，可含盾构、联络通道，基坑用深基坑）、management（布尔）。'
        '不适用或没有要求可返回空数组，勿将同一要求拆碎。')
    content = dict(类别=types, 文件名=source['name'], 正文=[dict(page=i,text=p) for i,p in enumerate(source['pages'],1)])
    body = dict(model=cfg['model'], messages=[dict(role='system',content=instruction),
                dict(role='user',content=json.dumps(content,ensure_ascii=False))],
                response_format=dict(type='json_object'),max_tokens=16384)
    if cfg['model'].startswith('deepseek'):
        body['thinking'] = dict(type='enabled' if cfg.get('thinking',True) else 'disabled')
        if cfg.get('thinking',True):
            body['reasoning_effort']='low'
    raw = engine['request_api'](cfg,'/chat/completions',body)
    parsed = engine['parse_model_reply'](raw,{})
    return verify(source, parsed, engine['token_usage'](raw))


def verify(source, result, usage):
    if not isinstance(result.get('items'),list):
        raise ValueError('模型未返回要求列表。')
    rows, seen = [], set()
    normalized = [''.join(p.split()) for p in source['pages']]
    for x in result['items']:
        if not isinstance(x,dict): continue
        quote = ''.join(str(x.get('quote') or '').split())
        req = str(x.get('requirement') or '').strip()
        matches = [i+1 for i,s in enumerate(normalized) if quote and quote in s]
        page = x.get('page')
        if page not in matches:
            page = matches[0] if len(matches)==1 else None
        if not page or not req or (page,quote,req) in seen: continue
        seen.add((page,quote,req))
        # 按原页恢复空格、换行等版式字符，保存的摘录是原文子串。
        original = source['pages'][page-1]
        offsets = [i for i,c in enumerate(original) if not c.isspace()]
        start = normalized[page-1].index(quote)
        literal = original[offsets[start]:offsets[start+len(quote)-1]+1]
        scope = x.get('scope') or ['通用']
        if isinstance(scope,str): scope=re.split(r'[/、,，]',scope)
        scope=list(dict.fromkeys('深基坑' if s.strip()=='基坑' else s.strip() for s in scope if isinstance(s,str) and s.strip())) or ['通用']
        rows.append(dict(seq=len(rows)+1,requirement=req,quote=literal,page=page,scope=scope,
                         enabled=x.get('management') is False,management=x.get('management') is not False))
    return {k:v for k,v in source.items() if k!='pages'} | dict(title=result.get('title') or source['name'],
        items=rows,dropped=len(result['items'])-len(rows),usage=usage)


class Library:
    def __init__(self, folder):
        self.folder=Path(folder)

    def path(self, kind):
        return self.folder / ('业主要求库_v1.json' if kind=='owners' else '问题收藏库_v1.json')

    def read(self, kind):
        p=self.path(kind)
        return json.loads(p.read_text('utf-8-sig')) if p.is_file() else dict(items=[],nextId=1)

    def write(self, kind, value):
        path=self.path(kind)
        tmp=path.with_suffix('.'+uuid4().hex+'.tmp')
        tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
        tmp.replace(path)

    def save_book(self, draft, edits, doc_no, overwrite=False):
        with LOCK:
            db=self.read('owners')
            books=db['items']
            old=next((b for b in books if b['sha256']==draft['sha256']),None)
            if old and not overwrite: raise ValueError('同一文件已入库，请选择覆盖或跳过。')
            if not isinstance(doc_no,str) or not doc_no.strip(): raise ValueError('请填写文号。')
            numbers=re.findall(r'\d+',doc_no)
            prefix='YZ-'+(numbers[-1] if numbers else draft['sha256'][:8])
            occupied={r['id'].rsplit('-',1)[0] for b in books if b is not old for r in b['items']}
            if prefix in occupied: prefix+='-'+draft['sha256'][:8]
            original={r['seq']:r for r in draft['items']}
            result=dict(draft,docNo=doc_no.strip(),items=[])
            previous_rows={r['seq']:r for r in old['items']} if old else {}
            new_checks=sorted((e for e in edits if e.get('enabled') and
                        (not previous_rows.get(e['seq'],{}).get('enabled') or 'selectedOrder' in e)),
                        key=lambda e:e.get('selectedOrder',0))
            ranks={e['seq']:db['nextId']+i for i,e in enumerate(new_checks)}
            db['nextId']+=len(ranks)
            for e in edits:
                row=original.pop(e['seq'])
                req=e['requirement'].strip()
                scope=e['scope']
                if not req or not isinstance(scope,list) or not scope or not all(isinstance(s,str) and s.strip() for s in scope):
                    raise ValueError('每条要求须填写要求文本和适用类别。')
                result['items'].append(dict(row,id=f"{prefix}-{row['seq']:02d}",docNo=result['docNo'],title=result['title'],
                        rank=ranks.get(row['seq'],previous_rows.get(row['seq'],{}).get('rank',0)),
                        scope=list(dict.fromkeys(s.strip() for s in scope)),requirement=req,enabled=e.get('enabled') is True))
            if old: books[books.index(old)]=result
            else: books.append(result)
            self.write('owners',db)
            return result

    @staticmethod
    def source_key(job, issue):
        origin=job.get('checkpointKey') or job.get('createdAt') or job['document'].get('sha256')
        return [job['document'].get('sha256') or job['document']['name'],origin,issue['id']]

    def collect(self, job, issue, note):
        with LOCK:
            db=self.read('favorites')
            key=self.source_key(job,issue)
            row=next((r for r in db['items'] if r['sourceKey']==key),None)
            if not row:
                row={k:issue.get(k,'') for k in ('title','description','suggestion','category','priority')}
                row.update(id=f"FAV-{db['nextId']:04d}",basis=[{k:b.get(k,'') for k in ('ref','clause_quote')} for b in issue.get('basis',[])],
                           schemeType=job['schemeType'],sourceName=job['document']['name'],sourceIssue=issue['id'],sourceKey=key,
                           collectedAt=datetime.now().isoformat(timespec='microseconds'),enabled=True,note=note)
                db['nextId']+=1
                db['items'].append(row)
                self.write('favorites',db)
            return row

    def edit_favorite(self, fid, changes, remove=False):
        with LOCK:
            db=self.read('favorites')
            row=next((r for r in db['items'] if r['id']==fid),None)
            if row:
                if remove: db['items'].remove(row)
                else: row.update({k:v for k,v in changes.items() if k in ('enabled','note')})
                self.write('favorites',db)

    def compose(self, kind, handwritten):
        with LOCK:
            owners=self.read('owners')['items']
            favorites=self.read('favorites')['items']
        items=[(s,None) for s in dict.fromkeys(handwritten)]
        selected=[(r,b) for b in owners for r in b['items'] if r['enabled'] and (kind in r['scope'] or '通用' in r['scope'])]
        for r,b in sorted(selected,key=lambda pair:pair[0].get('rank',0)):
            items.append((f"[{r['id']}]【{b['docNo']}】{r['requirement']}",dict(r,kind='owner',pageUnit=b['pageUnit'])))
        for r in sorted(favorites,key=lambda r:r['collectedAt'],reverse=True):
            if r['enabled'] and r['schemeType']==kind:
                items.append((f"[{r['id']}]【历史问题】{r['title']}：{r['description'][:60]}。检查本方案是否存在类似问题。",dict(r,kind='favorite')))
        focus,meta=[],{}
        used=0
        for text,entry in items:
            cost=len(text)+(1 if focus else 0)
            if used+cost>FOCUS_LIMIT: break
            focus.append(text)
            used+=cost
            if entry: meta[text]=entry
        return dict(focus=focus,focusSources=meta,focusOmitted=len(items)-len(focus),focusChars=used)


def finalize(job):
    sources=job.get('focusSources',{})
    for r in job.get('focusResults',[]):
        source=sources.get(r['focus'])
        if not source: continue
        owner=source['kind']=='owner'
        display={'发现问题':'未响应' if owner else '本方案也存在','已检视未发现':'已响应' if owner else '未发现类似问题'}
        r['displayStatus']=display.get(r['status'],r['status'])
        ids=set(re.findall(r'(?<![A-Za-z0-9])Q\d+(?!\d)',r['summary']))
        r['issueIds']=[]
        if r['status']!='发现问题':continue
        for item in job['issues']:
            if not ids.intersection([item['id'],*item.get('mergedFrom',[])]):continue
            r['issueIds'].append(item['id'])
            link=dict(id=source['id'],kind=source['kind'])
            if owner: link.update(relation='未响应',ref=source['docNo'],clause_quote=source['quote'],page=source['page'])
            links=item.setdefault('focusLinks',[])
            if link not in links:links.append(link)

