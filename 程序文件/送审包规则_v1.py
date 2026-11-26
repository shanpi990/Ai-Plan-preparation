"""编制助手交换协议。编号按原包顺序固定，跨审查围绕引文和标题匹配。"""
import base64
import hashlib
import json
import re
import unicodedata
from pathlib import Path

PARAM_ID = re.compile(r'CS-[0-9]+')
LIMIT = 1500


def side_names(name):
    stem = Path(name).stem
    return list(dict.fromkeys(s+'.送审包.json' for s in (stem, stem.removesuffix('_清洁版'))))


def native_selection(window):
    files = window.create_file_dialog(file_types=('方案文件 (*.docx;*.pdf;*.txt)',))
    if not files:
        return None
    path = Path(files[0])
    if path.suffix.lower() not in ('.docx', '.pdf', '.txt') or path.stat().st_size > 60_000_000:
        raise ValueError('请选择 60 MB 以内的 Word、PDF 或 TXT 文件。')
    content=path.read_bytes()
    data = dict(name=path.name, raw=base64.b64encode(content).decode('ascii'))
    if path.suffix.lower()=='.docx':
        for name in side_names(path.name):
            file=path.with_name(name)
            if file.is_file() and file.stat().st_size <= 12_000_000:
                raw=file.read_bytes()
                if read_pack(path.name,name,raw,hashlib.sha256(content).hexdigest()):
                    data['sidecar']=dict(name=name,raw=base64.b64encode(raw).decode('ascii'))
                    break
    return data


def read_pack(docname, name, raw, digest):
    if Path(docname).suffix.lower() != '.docx' or name.casefold() not in [n.casefold() for n in side_names(docname)]:
        return None
    try:
        obj=json.loads(raw.decode('utf-8-sig'))
        if obj['schema']!='bianshen/v1' or obj['docx']['sha256'].lower()!=digest:
            return None
        params,pending=obj['parameters'],obj['pending']
        if not all(isinstance(arr,list) and all(isinstance(x,dict) for x in arr) for arr in (params,pending)):
            return None
        confirmed=[(n,p) for n,p in enumerate(params,1) if p.get('confirmed') is True]
        reserved={p.get('id') for _,p in confirmed if isinstance(p.get('id'),str) and PARAM_ID.fullmatch(p['id'])}
        used=set()
        output=[]
        for n,p in confirmed:
            ref=p.get('id')
            if not isinstance(ref,str) or not PARAM_ID.fullmatch(ref):
                ref=f'CS-{n:03d}'
                while ref in reserved or ref in used:
                    n+=1
                    ref=f'CS-{n:03d}'
            if ref in used or not isinstance(p.get('label'),str) or not p['label'].strip() or p.get('value') in (None,''):
                return None
            used.add(ref)
            output.append(dict(p,id=ref))
        if any(not isinstance(x.get('id'),str) or not x['id'] or not isinstance(x.get('title'),str) for x in pending):
            return None
        if len({x['id'] for x in pending})!=len(pending):
            return None
        result=dict(packSha256=hashlib.sha256(raw).hexdigest(),parameters=output,pending=pending,matched=True)
        if isinstance(obj.get('paragraphMap'),list):
            result['paragraphMap']=[dict(paragraph=x['paragraph'],blockId=x['blockId']) for x in obj['paragraphMap']
                                    if isinstance(x,dict) and type(x.get('paragraph')) is int and isinstance(x.get('blockId'),str)]
        if isinstance(obj.get('previousReview'),dict):
            result['previousReview']=obj['previousReview']
        return result
    except (ValueError,TypeError,KeyError,AttributeError,UnicodeError):
        return None


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKC',str(value)).lower() if c.isalnum())


def grams(s):
    return {s[i:i+2] for i in range(len(s)-1)}


def source_label(p):
    s=p.get('source') or {}
    if not isinstance(s,dict):
        return str(s)
    return ' '.join(filter(None,[str(s.get('doc') or ''),f"第{s['page']}页" if s.get('page') else ''])) or p.get('origin') or '来源待核'


def param_line(p):
    scope=f"（{p['zone']}）" if p.get('zone') else ''
    return f"[{p['id']}]【已确认参数】{p['label']}{scope}={p['value']} {p.get('unit') or ''}，来源：{source_label(p)}"


def select_params(params,payload):
    if payload.get('任务类型')=='设计提取':
        return []
    rows=payload.get('本次资料',payload.get('回查原文',[]))
    sections=' '.join(str(row.get('section','')) for row in rows if isinstance(row,dict))
    text=' '.join(str(row.get('text','')) for row in rows if isinstance(row,dict))
    parents=payload.get('候选问题',payload.get('已有问题',[]))
    text+=' '+' '.join(str(i.get('title',''))+' '+str(i.get('description','')) for i in parents)
    prior={b['ref'] for i in parents for b in i.get('parameterBasis',[]) if 'ref' in b}
    chapter,body=norm(sections),norm(text)
    terms=grams(chapter+' '+body)
    ranking=[]
    for n,p in enumerate(params):
        label,zone=norm(p['label']),norm(p.get('zone') or '')
        wide=zone in ('','全项目','项目级','项目','全工程','全局','全线','全站','全场','通用')
        overlap=grams(label)&terms
        score=12*(p['id'] in prior)+8*(label in chapter)+6*(label in body)+4*(bool(zone) and zone in chapter+body)
        if len(overlap)>=2 and len(overlap)/max(1,len(grams(label)))>=0.5:
            score+=2
        if wide or score:
            ranking.append((-(score+int(wide)),n,p))
    lines=[]
    length=0
    for _,_,p in sorted(ranking):
        line=param_line(p)
        size=len(line)+bool(lines)
        if length+size<=LIMIT:
            lines.append(line)
            length+=size
    return lines
