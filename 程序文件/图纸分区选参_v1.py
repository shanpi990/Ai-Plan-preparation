"""图纸识别专用的分区归一和按批选参。原始候选的证据、编号及用户确认值分别保存。"""
import json
import re
import unicodedata
from pathlib import Path

COMMON='全场通用'
FIELDS=('开挖深度','围护形式及规格','支撑道数')
OVERVIEW=('概况','工程简介','编制依据','设计概况')
COMPARISON='只与同一分区、同一部位、同一工况的参数比较；不同分区的数值不同不构成问题。原文没写明分区时，不得据此判定不一致，最多标为待核。'

def clean(text):
    return ''.join(unicodedata.normalize('NFKC',str(text)).lower().split())

def anchors(name):
    return re.findall(r'(?:[0-9]+[a-z]?|[一二三四五六七八九十]+)号(?:安全出入口|出入口|风亭|风井|竖井|工作井|通道)',clean(name))

def zones_from(candidates):
    names=list(dict.fromkeys(c.get('rawZone',c.get('zone','')).strip() for c in candidates if c.get('name')=='开挖深度'))
    # 有完整部位名，且不是更完整名称的唯一前缀。保留本工程其他具名分区。
    usable=[n for n in names if anchors(n) or re.search(r'(?:[A-ZⅠ-Ⅹ一二三四五六七八九十0-9]+区|[东西南北]区|工作井|车站主体|区间隧道)$',n,re.I)]
    return [n for n in usable if not any(clean(other).startswith(clean(n)) and len(clean(other))>len(clean(n)) for other in usable)]

def match_zones(raw,standard):
    key=clean(raw)
    if not key:return []
    exact=[z for z in standard if clean(z)==key]
    if exact:return exact
    direct=[z for z in standard if len(key)>=3 and clean(z).startswith(key)]
    if len(direct)==1:return direct
    # 顿号也可能出现在单个分区内部（6、7 号安全出入口）。先做完整名和前缀匹配，再拆合写的部位。
    parts=re.split('[、，,及和与]',key)
    hits=[]
    for part in parts:
        if not part:continue
        matches=[z for z in standard if clean(z)==part or (len(part)>=3 and clean(z).startswith(part))]
        if len(matches)==1 and matches[0] not in hits:hits.append(matches[0])
    return hits

def with_scope(scope,raw):
    if raw and (scope==raw or scope.endswith('，'+raw)):return scope
    return '，'.join(x for x in [scope,raw] if x)

def normalize(snapshot):
    rows=snapshot['candidates'];standard=zones_from(rows);mapped={}
    for c in rows:
        raw=c.setdefault('rawZone',c.get('zone',''))
        zones=match_zones(raw,standard)
        c.update(zone='、'.join(zones) or COMMON,drawingZones=zones)
        c['drawingScope']=with_scope(c.get('phase',''),raw if not zones else '')
        mapped[c['id']]=c
    for p in snapshot['parameters']:
        c=mapped.get(p.get('candidateId'))
        if c:
            scope=p.setdefault('confirmedScope',p.get('drawingScope',''))
            p.update(rawZone=c['rawZone'],drawingZones=list(c['drawingZones']),zone=c['zone'],
                     drawingScope=with_scope(scope,c['rawZone'] if not c['drawingZones'] else ''))
    return standard

def terms(text):
    return {text[i:i+2] for i in range(len(text)-1)}

def source_line(p):
    scope='，'.join(x for x in (p.get('zone'),p.get('drawingScope')) if x)
    value=p['value']
    unit=p.get('unit','')
    if unit and not clean(value).endswith(clean(unit)):value+=' '+unit
    src=p.get('source') or {}
    if isinstance(src,dict):
        doc=Path(src.get('doc','')).stem
        suf=re.search(r'(总说明[（(][^）)]+[）)])$',doc)
        name=suf[1] if suf else doc
        source=f"〔{name} p{src['page']}〕" if name and src.get('page') else ''
    else:source=''
    return f"[{p['id']}] {scope}｜{p['label']}={value}{source}"

def mentioned(zone,text):
    keys=anchors(zone)
    # 保留分区首部别名，避免把“7号出入口”匹配到“17号出入口”。
    return any(re.search(r'(?<![0-9a-z])'+re.escape(key),text) for key in {clean(zone),*keys} if key)

def select(params,payload,char_limit=3000):
    if payload.get('任务类型')=='设计提取':return []
    rows=payload.get('本次资料',payload.get('回查原文',[]))
    section=clean(' '.join(str(row.get('section','')) for row in rows))
    body=clean(' '.join(str(row.get('text','')) for row in rows))
    parents=payload.get('候选问题',payload.get('已有问题',[]))
    description=clean(' '.join(str(i.get('title',''))+' '+str(i.get('description','')) for i in parents))
    prior={v['ref'] for i in parents for v in i.get('parameterBasis',[]) if v.get('ref')}
    words=section+' '+body+' '+description
    standard=list(dict.fromkeys(z for p in params for z in p.get('drawingZones',[p.get('zone','')]) if z and z!=COMMON))
    hit={z for z in standard if mentioned(z,words)}
    overview=any(k in section for k in OVERVIEW)
    ranking=[];covered=set();pairs_by_id={}
    grams=terms(words)
    for idx,p in enumerate(params):
        zs=p.get('drawingZones') or ([p['zone']] if p.get('zone') and p['zone']!=COMMON else [])
        zhit=bool(hit.intersection(zs))
        label=p['label'];literal=clean(label)
        score=(12 if literal in section else 0)+(8 if literal in words else 0)+len(terms(literal)&grams)
        common=not zs
        pairs={(z,label) for z in zs} if overview and label in FIELDS else set()
        if pairs or zhit or p['id'] in prior or score or common:
            pairs_by_id[p['id']]=pairs
            rank=0 if p['id'] in prior else 1 if pairs else 2 if zhit else 3
            ranking.append((rank,-int(zhit),-score,idx,p))
    ordered=sorted(ranking,key=lambda x:x[:4])
    # 概况批先给每个已有分区字段一个位置，再给不同工况、同分区和全场资料。
    first=[];rest=[]
    for rank,_,_,_,p in ordered:
        pairs=pairs_by_id[p['id']]
        if rank==0 or pairs-covered:
            first.append(p);covered.update(pairs)
        else:rest.append(p)
    lines=[];size=0
    for p in first+rest:
        line=source_line(p)
        n=len(line)+bool(lines)
        if size+n<=char_limit:
            lines.append(line);size+=n
    return lines

def estimate(text):
    # 中文和标点按一字一 token，ASCII 字母按每三字节一 token 粗估；请求最终仍经过客户端的真实序列化检查。
    return len(re.sub('[\\x00-\\x7f]','',text))+(sum(ord(c)<128 for c in text)+2)//3
