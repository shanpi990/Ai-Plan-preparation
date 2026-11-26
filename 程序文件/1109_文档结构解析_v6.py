"""读取Word表格逻辑列、合并关系和图文对象，不改原文件。"""
import io,zipfile
import xml.etree.ElementTree as ET
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
M='{http://schemas.openxmlformats.org/officeDocument/2006/math}'
MC='{http://schemas.openxmlformats.org/markup-compatibility/2006}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

def children(node):
    if node.tag==MC+'AlternateContent':
        chosen=node.find(MC+'Choice')
        if chosen is None:chosen=node.find(MC+'Fallback')
        return list(chosen) if chosen is not None else []
    return list(node)

def walk(node):
    yield node
    for c in children(node):yield from walk(c)

def math_text(node):
    name=node.tag.split('}')[-1]
    def part(key):
        child=node.find(M+key)
        return math_text(child) if child is not None else ''
    if name=='t':return node.text or ''
    if name=='f':return '('+part('num')+')/('+part('den')+')'
    if name=='sSup':return part('e')+'^('+part('sup')+')'
    if name=='sSub':return part('e')+'_('+part('sub')+')'
    if name=='sSubSup':return part('e')+'_('+part('sub')+')^('+part('sup')+')'
    if name=='rad':return '根号['+part('deg')+']('+part('e')+')'
    if name.endswith('Pr'):return ''
    return ''.join(math_text(c) for c in children(node))

def paragraph_content(p):
    texts=[];media=[]
    def visit(node):
        if node is not p and node.tag==W+'p':return
        if node.tag in (M+'oMath',M+'oMathPara'):
            value=math_text(node)
            texts.append('【Word公式：'+value+'】')
            media.append({'kind':'math','transcribed':True});return
        if node.tag==W+'t':texts.append(node.text or '');return
        if node.tag==W+'tab':texts.append(' ');return
        if node.tag in (W+'br',W+'cr'):texts.append('\n');return
        if node.tag in (W+'drawing',W+'pict',W+'object'):
            # 段内图片、OLE公式及形状留下位置标记；文本框中的段落另行读取。
            media.append({'kind':'object' if node.tag==W+'object' else 'drawing','transcribed':False})
        for c in children(node):visit(c)
    visit(p)
    text=''.join(texts).strip()
    media=[dict(t) for t in {tuple(sorted(x.items())) for x in media}]
    if not text and media:text='【图形或嵌入对象：请回看原件】'
    return text,media

def extract_docx(raw):
    import re
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        info=z.getinfo('word/document.xml')
        if info.file_size>35_000_000:raise ValueError('正文过大，请拆分后导入。')
        tree=ET.fromstring(z.read(info))
    nodes=list(walk(tree));parents={id(c):p for p in nodes for c in children(p)}
    def ancestor(node,tag):
        node=parents.get(id(node))
        while node is not None:
            if node.tag==tag:return node
            node=parents.get(id(node))
    rows=[];mapping={};section=[]
    for p in nodes:
        if p.tag!=W+'p':continue
        text,media=paragraph_content(p)
        if not text:continue
        style=p.find(W+'pPr/'+W+'pStyle');style=style.get(W+'val','') if style is not None else ''
        h=re.fullmatch(r'Heading([1-9])',style)
        if h:section=section[:int(h[1])-1]+[text]
        row={'id':len(rows)+1,'text':text,'section':' / '.join(section),'chapter':' / '.join(section),'style':style}
        if media:row['media']=media
        if ancestor(p,W+'txbxContent') is not None:row['textBox']=True
        rows.append(row);mapping[id(p)]=row
    tables=[n for n in nodes if n.tag==W+'tbl']
    for ti,table in enumerate(tables,1):
        trlist=table.findall(W+'tr');cells=[];active={};owned=[];header_rows=set()
        for ri,tr in enumerate(trlist,1):
            flag=tr.find(W+'trPr/'+W+'tblHeader')
            if ri==1 or (flag is not None and flag.get(W+'val','true') not in ('0','false','off')):header_rows.add(ri)
            before=tr.find(W+'trPr/'+W+'gridBefore');col=int(before.get(W+'val','0'))+1 if before is not None else 1
            next_active={};horizontal=None
            for cell in tr.findall(W+'tc'):
                prop=cell.find(W+'tcPr')
                span_node=prop.find(W+'gridSpan') if prop is not None else None
                span=max(1,int(span_node.get(W+'val','1'))) if span_node is not None else 1
                vm=prop.find(W+'vMerge') if prop is not None else None
                hm=prop.find(W+'hMerge') if prop is not None else None
                own=[mapping[id(p)] for p in cell.iter(W+'p') if id(p) in mapping and ancestor(p,W+'tbl') is table]
                text=' / '.join(x['text'] for x in own)
                if hm is not None and hm.get(W+'val','continue')=='continue' and horizontal is not None:
                    anchor=horizontal;anchor['colEnd']=col+span-1;anchor['paragraphs'] += [x['id'] for x in own]
                    if text:anchor['text']+=' / '+text
                elif vm is not None and vm.get(W+'val','continue')=='continue' and col in active:
                    anchor=active[col];anchor['rowEnd']=ri
                    anchor['paragraphs'] += [x['id'] for x in own]
                    if text and text!=anchor['text']:anchor['text']+=' / '+text
                else:
                    anchor={'row':ri,'rowEnd':ri,'col':col,'colEnd':col+span-1,'text':text,'paragraphs':[x['id'] for x in own]}
                    cells.append(anchor)
                if hm is not None and hm.get(W+'val','continue')=='restart':horizontal=anchor
                elif hm is None:horizontal=None
                if vm is not None:
                    for c in range(col,col+span):next_active[c]=anchor
                for row in own:owned.append((row,anchor,ri,col,col+span-1))
                col+=span
            active=next_active
        for row,anchor,ri,start,end in owned:
            start=anchor['col'];end=anchor['colEnd']
            header=[]
            for h in cells:
                if h['row'] in header_rows and h['col']<=start<=h['colEnd'] and h['text'] and h['text'] not in header:header.append(h['text'])
            loc=f"表{ti} 第{ri}行 第{start}"+(f"—{end}" if end>start else '')+'列'
            if anchor['row']<ri:loc+=f"（纵向合并至第{anchor['row']}行）"
            row['section']=row['chapter']+(' / ' if row['chapter'] else '')+loc
            if ri in header_rows:row['role']='表头'
            row['table']={'id':ti,'row':ri,'col':start,'colEnd':end,'rowStart':anchor['row'],'rowEnd':anchor['rowEnd'],'headers':header}
        if owned:
            owned[0][0]['tableLayout']={'id':ti,'headerRows':sorted(header_rows),'cells':cells}
    return rows

def table_context(doc,rows,source):
    selected={}
    for row in rows:
        t=row.get('table')
        if t:selected.setdefault(t['id'],set()).add(t['row'])
    result=[]
    for row in doc['rows']:
        layout=row.get('tableLayout')
        if not layout or layout['id'] not in selected:continue
        keep=selected[layout['id']]|set(layout['headerRows'])
        cells=[]
        for c in layout['cells']:
            if not any(c['row']<=ri<=c['rowEnd'] for ri in keep):continue
            cells.append({**c,'text':c['text'][:1200]})
        result.append({'source':source,'table':layout['id'],'headerRows':layout['headerRows'],'cells':cells,**({'captionParagraph':layout['captionParagraph']} if layout.get('captionParagraph') else {})})
    return result
