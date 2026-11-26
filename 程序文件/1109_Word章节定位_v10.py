"""依据Word样式和自动编号还原可读位置；不改正文及内部段号。"""
from pathlib import Path
import io,re,zipfile,runpy,xml.etree.ElementTree as ET
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
STRUCT=runpy.run_path(str(Path(__file__).with_name('1109_文档结构解析_v6.py')))


def chinese(n):
    if n==0:return '零'
    digits='零一二三四五六七八九';result='';pending=False
    for unit,label in ((10000,'万'),(1000,'千'),(100,'百'),(10,'十'),(1,'')):
        part,n=divmod(n,unit)
        if part:
            if pending:result+='零'
            result+=(chinese(part) if part>9 else digits[part])+label;pending=False
        elif result and n:pending=True
    return result[1:] if result.startswith('一十') else result


def number_text(n,fmt):
    if fmt in ('decimal','decimalEnclosedCircle','decimalZero'):
        return str(n).zfill(2) if fmt=='decimalZero' else str(n)
    if fmt in ('chineseCounting','chineseCountingThousand','ideographTraditional'):return chinese(n)
    if fmt in ('upperLetter','lowerLetter'):
        text=''
        while n:n,v=divmod(n-1,26);text=chr(65+v)+text
        return text if fmt=='upperLetter' else text.lower()
    if fmt in ('upperRoman','lowerRoman'):
        text=''
        for value,label in ((1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')):
            count,n=divmod(n,value);text+=label*count
        return text if fmt=='upperRoman' else text.lower()
    return None


def props(node):
    result={}
    if node is None:return result
    for key,path in (('numId','numPr/numId'),('ilvl','numPr/ilvl'),('outline','outlineLvl')):
        item=node.find('/'.join(W+x for x in path.split('/')))
        if item is not None:result[key]=int(item.get(W+'val','0'))
    return result


def enrich_docx(doc,raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        tree=ET.fromstring(z.read('word/document.xml'))
        styles=ET.fromstring(z.read('word/styles.xml')) if 'word/styles.xml' in z.namelist() else ET.Element('styles')
        numbering=ET.fromstring(z.read('word/numbering.xml')) if 'word/numbering.xml' in z.namelist() else ET.Element('numbering')
    style_nodes={s.get(W+'styleId'):s for s in styles.findall(W+'style')};style_cache={}
    def style_props(key,seen=()):
        if key in style_cache:return style_cache[key]
        if key in seen:return {}
        node=style_nodes.get(key)
        if node is None:return {}
        parent=node.find(W+'basedOn');name=node.find(W+'name')
        data=dict(style_props(parent.get(W+'val'),seen+(key,))) if parent is not None else {}
        data.update(props(node.find(W+'pPr')))
        data['styleName']=name.get(W+'val','') if name is not None else key
        if 'outline' not in data:
            match=re.fullmatch(r'(?:heading|标题)\s*([1-9])',data['styleName'],re.I)
            if match:data['outline']=int(match[1])-1
        style_cache[key]=data;return data
    abstracts={n.get(W+'abstractNumId'):{int(l.get(W+'ilvl')):l for l in n.findall(W+'lvl')} for n in numbering.findall(W+'abstractNum')}
    definitions={}
    for num in numbering.findall(W+'num'):
        link=num.find(W+'abstractNumId')
        levels=dict(abstracts.get(link.get(W+'val') if link is not None else '',{}));starts={}
        for override in num.findall(W+'lvlOverride'):
            index=int(override.get(W+'ilvl'));level=override.find(W+'lvl');start=override.find(W+'startOverride')
            if level is not None:levels[index]=level
            if start is not None:starts[index]=int(start.get(W+'val','1'))
        definitions[int(num.get(W+'numId'))]=(levels,starts)
    counters={}
    def label(properties):
        num_id=properties.get('numId',0);index=properties.get('ilvl',0)
        if not num_id or num_id not in definitions:return ''
        levels,starts=definitions[num_id];level=levels.get(index)
        if level is None:return ''
        values=counters.setdefault(num_id,{})
        def val(node,key,default):
            item=node.find(W+key) if node is not None else None
            return item.get(W+'val',default) if item is not None else default
        for deeper,node in levels.items():
            restart=int(val(node,'lvlRestart',str(deeper)))
            if deeper>index and restart and index<restart:values.pop(deeper,None)
        values[index]=values.get(index,starts.get(index,int(val(level,'start','1')))-1)+1
        template=val(level,'lvlText','');legal=level.find(W+'isLgl') is not None
        if val(level,'numFmt','decimal') in ('bullet','none'):return ''
        supported=True
        def substitute(match):
            nonlocal supported
            i=int(match[1])-1
            if i not in values:supported=False;return ''
            text=number_text(values[i],'decimal' if legal else val(levels.get(i),'numFmt','decimal'))
            if text is None:supported=False;return ''
            return text
        text=re.sub(r'%([1-9])',substitute,template)
        return text.strip() if supported else ''

    nodes=list(STRUCT['walk'](tree));parents={id(c):p for p in nodes for c in STRUCT['children'](p)}
    def ancestor(node,tag):
        parent=parents.get(id(node))
        while parent is not None:
            if parent.tag==tag:return parent
            parent=parents.get(id(parent))
    if doc.get('parserVersion')=='v6':
        entries=[(p,STRUCT['paragraph_content'](p)[0]) for p in nodes if p.tag==W+'p']
    else:
        entries=[(p,''.join(t.text or '' for t in p.iter(W+'t')).strip()) for p in tree.iter(W+'p')]
    entries=[(p,text) for p,text in entries if text]
    if len(entries)!=len(doc['rows']) or any(text!=r['text'] for (_,text),r in zip(entries,doc['rows'])):
        raise ValueError('原文解析顺序与记录不一致，未套用章节位置。')
    mapping={id(p):row for (p,_),row in zip(entries,doc['rows'])}
    stack=[];headings=[];captions={};caption_ids={};used_captions=set();last=None
    for node in nodes:
        if node.tag==W+'tbl':
            if last and last['caption'] and last['id'] not in used_captions:
                captions[id(node)]=last['caption'];caption_ids[id(node)]=last['id'];used_captions.add(last['id'])
            continue
        if node.tag!=W+'p':continue
        row=mapping.get(id(node))
        if row is None:continue
        properties=dict(style_props(row.get('style','')));properties.update(props(node.find(W+'pPr')))
        toc=bool(re.match(r'toc',row.get('style',''),re.I) or re.match(r'toc',properties.get('styleName',''),re.I))
        auto='' if toc else label(properties)
        text=row['text'].strip();inside_table=ancestor(node,W+'tbl');inside_box=ancestor(node,W+'txbxContent')
        outline=properties.get('outline');style_name=properties.get('styleName','').lower()
        manual_chapter=re.match(r'^第[一二三四五六七八九十百零〇\d]+章(?:\s*|(?=[\u4e00-\u9fff]))',text)
        manual_section=re.match(r'^(\d+(?:\.\d+){1,5})(?:[.、\s]+(?=\S)|(?=[\u4e00-\u9fff]))',text)
        if outline is None and inside_table is None and len(text)<100:
            if manual_chapter:outline=0
            elif manual_section and not re.search(r'[。；;]',text):outline=manual_section[1].count('.')
        is_heading=not toc and inside_table is None and inside_box is None and isinstance(outline,int) and 0<=outline<9 and style_name not in ('title','subtitle')
        caption=(auto+' '+text).strip() if auto.startswith('表') else text if re.match(r'^表\s*\d+(?:[.．-]\d+)*\s*',text) and len(text)<150 else ''
        # “表头k”在表格外是表题；单元格中的表头以网格标记为准。
        figure_style=re.search(r'图(?:题|标题|名|注|尾)|figure caption',style_name)
        if not toc and inside_box is None:
            if auto.startswith('图') or figure_style or (style_name in ('caption','题注') and text.startswith('图')):
                row['role']='图题'
            elif inside_table is not None and re.search(r'表(?:格)?表头|表头|table head(?:er|ing)',style_name):
                row['role']='表头'
            elif inside_table is None and (auto.startswith('表') or re.search(r'表(?:格标题|标题|题|名|头)|table caption',style_name)):
                caption=caption or text
                row['role']='表题'
            elif inside_table is None and caption and not is_heading:
                row['role']='表题'
            if row.get('role'):is_heading=False
        if is_heading:
            row['role']=f'h{outline+1}'
            explicit=manual_chapter or manual_section
            full=text if explicit else (auto+' '+text).strip()
            if not full:continue
            stack=[x for x in stack if x['level']<outline]
            heading={'level':outline,'label':full,'title':text,'number':auto,'paragraph':row['id']}
            stack.append(heading);headings.append(heading);row['heading']=heading
        path=[x['label'] for x in stack]
        row['chapter']=' → '.join(path)
        numbered=[h['label'] for h in stack if h.get('number') or re.match(r'^(?:第.+章|\d+(?:\.\d+)+)',h['label'])]
        short=([path[0]]+numbered[-1:]+[path[-1]]) if path else []
        short=list(dict.fromkeys(short))
        table_caption=captions.get(id(inside_table),'') if inside_table is not None else ''
        if table_caption:short.append(table_caption)
        elif inside_table is not None:short.append('表格')
        if toc:location='目录'
        elif short:location=' → '.join(short)
        else:location='文档开头' if not headings else '正文'
        row['location']=location;row['section']=location
        row['chapterPath']=path
        if table_caption:
            row['tableCaption']=table_caption
            if row.get('tableLayout'):row['tableLayout']['captionParagraph']=caption_ids[id(inside_table)]
        if inside_table is None:last={'id':row['id'],'caption':caption}
    # 旧解析器曾读取Word备用图文布局，沿用同一容器的位置，不改变旧段号。
    all_parents={id(c):p for p in tree.iter() for c in p}
    for paragraph,_ in entries:
        row=mapping[id(paragraph)]
        if row.get('location'):continue
        parent=all_parents.get(id(paragraph));owner=None
        while parent is not None and owner is None:
            candidate=mapping.get(id(parent))
            if candidate and candidate.get('location'):owner=candidate;break
            if parent.tag.endswith('AlternateContent'):
                owner=next((mapping[id(p)] for p in STRUCT['walk'](parent) if id(p) in mapping and mapping[id(p)].get('location')),None)
            parent=all_parents.get(id(parent))
        if owner:
            for key in ('location','section','chapter','chapterPath','tableCaption'):
                if key in owner:row[key]=owner[key]
        else:row['location']=row['section']='备用布局文字（章节未识别）'
        row['alternateLayout']=True
    doc['headings']=headings;doc['headingCount']=len(headings);doc['locationVersion']='v10'
    return doc


def display_location(row):
    if row.get('location'):return row['location']
    if row.get('page'):return '第'+str(row['page'])+'页'
    section=row.get('section','')
    return section if section and not re.search(r'表\d+ 第\d+行',section) else '正文（关联原方案后可显示章节）'


def refresh_job(job,docs):
    refs={'plan':{r['id']:r for r in docs[0]['rows']}} if docs and docs[0] else {}
    for i,doc in enumerate(docs[1:],1):
        if doc:refs['design'+str(i)]={r['id']:r for r in doc['rows']}
    def visit(value):
        if isinstance(value,dict):
            if {'source','paragraph','quote'}<=value.keys():
                row=refs.get(value['source'],{}).get(value['paragraph'])
                if row and ''.join(value['quote'].split()) in ''.join(row['text'].split()):
                    value['location']=display_location(row);value['section']=row.get('section','')
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(job)
    return job
