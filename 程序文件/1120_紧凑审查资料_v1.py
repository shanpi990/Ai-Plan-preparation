"""审查请求的紧凑文字、表格和引用。原始段号始终保留。"""
import json
import re
from collections import defaultdict

def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

GUIDE = """
输入按位置分组，段落或普通表格单元为[paragraph段号,逐字原文]。来源见批次的“来源”，回查按来源分组，工程概况来自plan。
表格的“行”为[原表行号,单元格列表]，从左向右读取；多段、跳列或合并单元另外给出段落、col、rowspan、colspan。空格无段号。
表与段落可同等引用，输出citations或evidence仍填source、paragraph、quote；quote必须逐字摘自同一段。输入中的引文编号指向本批引文表，回查和汇总复用原引文时可直接在 citations 或 evidence 数组填该整数编号。新引用写全 source、paragraph、quote。
表格的行号、列号和段号不同。每个 quote 只能复制同一个段号旁的连续文字。比如两个单元格 [71,"仪器型号"]、[72,"DS1"]，取值的引用是 {"source":"plan","paragraph":72,"quote":"DS1"}。不要把表头、单位或相邻格拼入 quote；需要多格证据就分成多条引用。最终只返回新增参数和新增问题，已经提供的参数无需再报。"""

def role(row):
    if row.get('role'):return row['role']
    level=(row.get('heading') or {}).get('level')
    if isinstance(level,int) and 0<=level<9:return f'h{level+1}'
    return ''

def keeps_next(row):
    mark=role(row)
    return not row['text'].strip() or mark=='表题' or bool(re.fullmatch(r'h[1-9]',mark))

def join_titles(batches):
    result=[]
    pending=[]
    for batch in batches:
        rows=pending+batch
        cut=len(rows)
        while cut and keeps_next(rows[cut-1]):cut-=1
        if cut:result.append(rows[:cut])
        pending=rows[cut:]
    # 原件以孤立标题结尾时必须保留原文；此时没有下一段可随同发送。
    if pending:
        if result:result[-1].extend(pending)
        else:result.append(pending)
    return result

def split_rows(rows):
    middle=len(rows)//2
    cut=middle
    while cut and keeps_next(rows[cut-1]):cut-=1
    if cut:return rows[:cut],rows[cut:]
    cut=middle
    while cut<len(rows) and (cut==0 or keeps_next(rows[cut-1])):cut+=1
    if 0<cut<len(rows):return rows[:cut],rows[cut:]
    # 标题组连一个特长正文段时，切正文并保留原段号。
    for idx,row in enumerate(rows):
        if not keeps_next(row) and len(row['text'])>1:
            mid=len(row['text'])//2
            return rows[:idx]+[dict(row,text=row['text'][:mid])],[dict(row,text=row['text'][mid:])]+rows[idx+1:]
    raise ValueError('标题与首段或固定资料超过初审批次字符上限，请核对配置。')

def materials(rows, tables, refs):
    positions = []
    covered = {t['table'] for t in tables}
    placed = set()
    metadata = []
    selected = {}
    for r in rows:
        pid, txt = r['paragraph'], r['text']
        selected[pid] = txt
        extra = {k:r[k] for k in ('imageIds','media','textBox') if r.get(k)}
        if extra:
            metadata.append([pid,extra])
        cell = r.get('cell', {})
        table = cell.get('id')
        section = r.get('section','')
        location = r.get('location','')
        if table in covered:
            if table in placed:
                continue
            placed.add(table)
            # 同表各格 location 含不同的行列号；只保留原始表名和章节。
            location = re.sub(r'\s*第\s*\d+\s*行.*$', '', location).rstrip(' ·/→')
            entry = f'表 {table} 见表格结构'
        else:
            mark=role(refs.get(pid,{}) or r) or role(r)
            entry = [pid,txt,mark] if mark else [pid,txt]
        if not positions or (positions[-1]['位置'],positions[-1].get('section','')) != (location,section if section!=location else ''):
            group = {'位置':location,'段落':[]}
            if section and section != location:
                group['section']=section
            positions.append(group)
        positions[-1]['段落'].append(entry)

    grids=[]
    for table in tables:
        matrix={}
        next_col={}
        for cell in table['cells']:
            ri,ci=cell['row'],cell['col']
            parts=[]
            for pid in cell['paragraphs']:
                text=selected.get(pid)
                if text is None:
                    row=refs.get(pid)
                    if row is not None:
                        text=row['text']
                    elif len(cell['paragraphs'])==1:
                        text=cell['text']
                    else:
                        raise ValueError('表格含未能定位的多段单元格，请重新导入原件。')
                mark=role(refs.get(pid,{})) or ('表头' if ri in table['headerRows'] else '')
                parts.append([pid,text,mark] if mark else [pid,text])
            info={}
            if ci != next_col.get(ri,1):info['col']=ci
            if cell['rowEnd']>ri:info['rowspan']=cell['rowEnd']-ri+1
            if cell['colEnd']>ci:info['colspan']=cell['colEnd']-ci+1
            next_col[ri]=cell['colEnd']+1
            value=parts[0] if len(parts)==1 else parts
            if info or len(parts)>1:value=dict(info,段落=parts)
            matrix.setdefault(ri,[]).append(value)
        grids.append({'表':table['table'],**({'表题段号':table['captionParagraph']} if table.get('captionParagraph') else {}),'表头行':table['headerRows'],'行':list(matrix.items())})
    return positions,grids,metadata

def compact(payload, source, refs):
    data=dict(payload)
    if '本次资料' in data:
        pos,grid,meta=materials(data['本次资料'],data['本批表格结构'],refs[source])
        data.update(来源=source,本次资料=pos,本批表格结构=grid)
        if meta:data['段落附注']=meta
        # 本批资料已覆盖的概况，直接引用原段号。
        present={r['paragraph'] for r in payload['本次资料']} if source=='plan' else set()
        overview=data.get('工程概况摘录',[])
        extra,_,notes=materials([r for r in overview if r['paragraph'] not in present],[],refs['plan'])
        data['工程概况摘录']=extra
        if notes:data['概况段落附注']=notes
    if '回查原文' in data:
        groups=defaultdict(list)
        for row in data['回查原文']:groups[row['source']].append(row)
        sources=[]
        for name,rows in groups.items():
            pos,grid,meta=materials(rows,[t for t in data['表格结构'] if t['source']==name],refs[name])
            part={'来源':name,'正文':pos,'表格':grid}
            if meta:part['段落附注']=meta
            sources.append(part)
        data['回查原文']=sources
        del data['表格结构']
    quotes={}
    for field in ('候选问题','已有问题','已提取参数','设计要求','已提取设计要求'):
        if field not in data:continue
        summaries=[]
        for item in data[field]:
            entry={k:v for k,v in item.items() if k not in ('citations','checkReason','candidateIds','reviewHistory','location','bucket','aiReviewHistory')}
            ids=[]
            for c in item.get('citations',[]):
                key=(c['source'],c['paragraph'],c['quote'])
                ids.append(quotes.setdefault(key,len(quotes)+1))
            if ids:entry['引文编号']=ids
            summaries.append(entry)
        data[field]=summaries
    if quotes:data['引文表']=[[i,*key] for key,i in quotes.items()]
    return data

def expand_quotes(result, payload):
    quotes={n:dict(source=s,paragraph=p,quote=q) for n,s,p,q in payload.get('引文表',[])}
    if not quotes:return
    def expand(item,field):
        if isinstance(item,dict) and isinstance(item.get(field),list):
            item[field]=[quotes.get(v,v) if type(v) is int else v for v in item[field]]
    for field in ('issues','parameters'):
        for item in result.get(field,[]) or []:expand(item,'citations')
    for field in ('reviews','mergeGroups'):
        for item in result.get(field,[]) or []:
            expand(item,'evidence')
            if isinstance(item,dict):expand(item.get('issue'),'citations')
