"""正式审查的输入格式。段号和可引用范围由原审查流程决定。"""
import json
from collections import defaultdict

NAMES={'legacy':'完整旧格式','compact':'紧凑格式','readable':'格式 C','slim':'旧格式（瘦身，实验）'}

def choose(value):
    if value not in NAMES:raise ValueError('请选择有效的审查输入格式。')
    return value

def system_text(original, compact_guide, mode):
    if mode=='compact':return original
    if mode=='readable':
        # 沿用紧凑版所有引用、参数与审查要求，只替换输入语法的说明。
        guide=compact_guide.replace('输入按位置分组，段落或普通表格单元为[paragraph段号,逐字原文]。','输入按位置分组，每行 [段号|角色] 后是原文，正文省略角色。')
        start=guide.index('表格的“行”')
        end=guide.index('表与段落',start)
        guide=guide[:start]+'表格逐行列出，用 [段号] 列名=原文 标识每格，多层列名用 / 连接。表头行给出可引用的原段号。\n'+guide[end:]
        guide=guide.replace('[71,"仪器型号"]、[72,"DS1"]','[71|表头] 仪器型号、[72] 仪器型号=DS1')
    elif mode=='slim':
        guide='\n逐段资料的来源见所属批次或来源分组。表格结构按行、列、跨度和段号关联逐段资料，省略的重复文字从相同段号读取。locationEnd 表示 location 为 section 的前若干字符。'
    else:
        guide=''
    return original.replace(compact_guide,guide)

def as_line(value):
    if value.startswith('"') or any(c in value for c in ('\n','\r',' | ')):
        return json.dumps(value,ensure_ascii=False)
    return value

def message(data,mode):
    if mode!='readable':
        return json.dumps(data,ensure_ascii=False,separators=(',',':'))
    # 用文本块保留真实换行；其他字段仍用 JSON 表示。
    lines=[]
    for k,v in data.items():
        if k in ('本次资料文本','回查原文文本','工程概况摘录') and isinstance(v,str):
            lines.append(k+': |-')
            lines.extend('  '+s for s in v.split('\n'))
        else:lines.append(k+': '+json.dumps(v,ensure_ascii=False,separators=(',',':')))
    return '\n'.join(lines)

def rows_with_roles(rows,refs):
    result=[]
    for row in rows:
        item=dict(row)
        mark=refs[row['source']].get(row['paragraph'],{}).get('role')
        if mark:item['role']=mark
        result.append(item)
    return result

def slim_rows(rows):
    result=[]
    for row in rows:
        item={k:v for k,v in row.items() if k!='source'}
        loc=item.get('location','')
        sec=item.get('section','')
        if sec and sec==loc:item.pop('section')
        elif loc and sec.startswith(loc+' → '):
            item.pop('location');item['locationEnd']=len(loc)
        result.append(item)
    return result

def slim_material(rows,tables,source,refs):
    # 表头与同一行其他单元格可能来自 table_context 补发，须在删重前补齐原段。
    flat=rows_with_roles(rows,refs)
    seen={r['paragraph']:r['text'] for r in flat}
    structures=[]
    for t in tables:
        cells=[]
        for c in t['cells']:
            for pid in c['paragraphs']:
                if pid in seen or pid not in refs[source]:continue
                row=refs[source][pid]
                item=dict(source=source,paragraph=pid,text=row['text'],location=row.get('location',row.get('section','')),
                          cell={k:v for k,v in row.get('table',{}).items() if k in ('id','row','col','colEnd','rowStart','rowEnd')})
                if row.get('chapter'):item['section']=row['chapter']
                if row.get('role'):item['role']=row['role']
                flat.append(item);seen[pid]=row['text']
            cell={k:v for k,v in c.items() if k!='text'}
            if not all(p in seen for p in c['paragraphs']) or ' / '.join(seen[p] for p in c['paragraphs'])[:1200]!=c['text']:
                cell['text']=c['text']
            cells.append(cell)
        structures.append({k:v for k,v in t.items() if k not in ('source','cells')}|{'cells':cells})
    return slim_rows(flat),structures

def header_depth(cells,declared):
    depth=max(declared or [1])
    # 跨行表头和同层跨列组共同界定下一级表头，包括未在 Word 勾选“重复标题行”的行。
    for c in cells:
        if c['row']<=depth:depth=max(depth,c['rowEnd'])
    while True:
        parents=[c for c in cells if c['row']<=depth==c['rowEnd'] and c['colEnd']>c['col']]
        children=[c for c in cells if c['row']==depth+1 and c.get('text','').strip()]
        if not parents or not children or not any(c['row']>depth+1 for c in cells):break
        if not all(any(p['col']<=c['col']<=c['colEnd']<=p['colEnd'] for p in parents) for c in children):break
        if not all(any(ch.isalpha() for ch in c['text']) for c in children):break
        depth+=1
    return depth

def table_lines(table,refs,selected):
    cells=table['cells']
    # 部分表格在回查或拆批时只带表头和命中行。完整布局只用于解读列名。
    layout=next((refs[pid]['tableLayout'] for c in cells for pid in c['paragraphs']
                 if pid in refs and refs[pid].get('tableLayout',{}).get('id')==table['table']),table)
    full=layout['cells']
    depth=header_depth(full,layout['headerRows'])
    labels=defaultdict(list)
    for c in full:
        if c['row']>depth:continue
        label=''.join(refs[p]['text'] for p in c['paragraphs'] if p in refs) or c['text']
        if label:
            for col in range(c['col'],c['colEnd']+1):labels[col].append(label)
    caption=table.get('captionParagraph')
    refrow=next((refs[p] for c in cells for p in c['paragraphs'] if p in refs),{})
    title=refrow.get('tableCaption') or f"表 {table['table']}"
    output=[title+(f'（表题段 {caption}）' if caption else '')]
    by_row=defaultdict(list)
    for c in cells:
        keys=list(dict.fromkeys('/'.join(labels[col]) or f'第{col}列' for col in range(c['col'],c['colEnd']+1)))
        label=as_line('、'.join(keys))
        for pid in c['paragraphs']:
            if pid in selected:raw=selected[pid]
            elif pid in refs:raw=refs[pid]['text']
            elif len(c['paragraphs'])==1:raw=c['text']
            else:raise ValueError('表格含未能定位的多段单元格，请重新导入原件。')
            role=refs.get(pid,{}).get('role','')
            head=c['row']<=depth
            mark=('表头' if head and not role else role)
            tag=f"[{pid}"+(f'|{mark}' if mark else '')+'] '
            cell=as_line(raw)
            if not head:
                span=f"（第{c['row']}～{c['rowEnd']}行共用）" if c['rowEnd']>c['row'] else ''
                cell=label+span+'='+cell
            by_row[c['row']].append(tag+cell)
        if not c['paragraphs'] and c['row']>depth:by_row[c['row']].append(label+'='+as_line(c['text']))
    output.extend(f'第{r}行 '+' | '.join(entries) for r,entries in by_row.items())
    return output

def readable_material(groups,tables,rows,refs):
    selected={r['paragraph']:r['text'] for r in rows}
    table_by_marker={f"表 {t['table']} 见表格结构":t for t in tables}
    lines=[]
    last=None
    for g in groups:
        loc=g['位置'] or g.get('section','')
        if loc!=last:lines.append('## '+loc);last=loc
        for entry in g['段落']:
            if isinstance(entry,str):
                lines.extend(table_lines(table_by_marker[entry],refs,selected))
            else:
                pid,txt,*roles=entry
                mark=roles[0] if roles else ''
                prefix='### ' if mark.startswith('h') else ''
                lines.append(prefix+f'[{pid}'+(f'|{mark}' if mark else '')+'] '+as_line(txt))
    return '\n'.join(lines)

def render(payload,source,refs,mode,wire):
    choose(mode)
    if mode=='compact':return wire['compact'](payload,source,refs)
    if mode=='readable':
        data=wire['compact'](payload,source,refs)
        if '本次资料' in data:
            groups=data.pop('本次资料')
            data.pop('本批表格结构')
            data['本次资料文本']=readable_material(groups,payload['本批表格结构'],payload['本次资料'],refs[source])
            data['工程概况摘录']=readable_material(data['工程概况摘录'],[],[],refs['plan'])
        if '回查原文' in data:
            parts=[];notes=[]
            for group in data.pop('回查原文'):
                name=group['来源']
                tables=[t for t in payload['表格结构'] if t['source']==name]
                rows=[r for r in payload['回查原文'] if r['source']==name]
                parts+=['来源 '+name,readable_material(group['正文'],tables,rows,refs[name])]
                if group.get('段落附注'):notes.append({'来源':name,'段落附注':group['段落附注']})
            data.pop('表格结构',None)
            data['回查原文文本']='\n'.join(parts)
            if notes:data['段落附注']=notes
        return data
    data=dict(payload)
    if '本次资料' in data:
        data['本次资料']=rows_with_roles(data['本次资料'],refs)
        data['工程概况摘录']=rows_with_roles(data.get('工程概况摘录',[]),refs)
        if mode=='slim':
            data['来源']=source
            data['本次资料'],data['本批表格结构']=slim_material(payload['本次资料'],payload['本批表格结构'],source,refs)
            data['工程概况摘录']={'来源':'plan','段落':slim_rows(data['工程概况摘录'])}
    if '回查原文' in data:
        data['回查原文']=rows_with_roles(data['回查原文'],refs)
        if mode=='slim':
            groups=defaultdict(list)
            for r in payload['回查原文']:groups[r['source']].append(r)
            del data['表格结构']
            data['回查原文']=[]
            for name,rows in groups.items():
                flat,tables=slim_material(rows,[t for t in payload['表格结构'] if t['source']==name],name,refs)
                data['回查原文'].append({'来源':name,'段落':flat,'表格结构':tables})
    return data
