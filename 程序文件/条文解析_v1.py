"""按文档顺序识别规范正文、位置与条文说明。"""
import io
import re
import hashlib
from collections import Counter
from pathlib import Path

NUM=r'(?:\d{1,2}|[A-Z])(?:\.\d{1,2}){2,3}'
CODE=r'(?:T\s*/\s*CECS|DG\s*/\s*TJ|JGJ(?:\s*/\s*T)?|GB(?:\s*/\s*T)?|CJJ(?:\s*/\s*T)?|DGJ|DB\d+(?:/T)?)\s*\d+(?:[.-]\d+)*[-－—]\d{4}'
def code(value):
    compact=re.sub(r'\s+','',value.upper()).replace('—','-').replace('－','-')
    match=re.fullmatch(r'(DB\d+/T|[A-Z/]+)(\d.*)',compact)
    return match[1]+' '+match[2] if match else compact

def parts(name, raw):
    ext=Path(name).suffix.lower()
    if ext=='.pdf':
        from pypdf import PdfReader
        pages=[]
        for i,p in enumerate(PdfReader(io.BytesIO(raw)).pages,1):
            txt=p.extract_text() or ''
            if not txt.strip() and p.images:raise ValueError(f'PDF第{i}页需要 OCR')
            pages.append([line.strip() for line in txt.splitlines() if line.strip()])
        freq=Counter(line for lines in pages for line in set(lines[:2]+lines[-2:]))
        for i,lines in enumerate(pages,1):
            for j,line in enumerate(lines):
                if len(pages)>2 and (j<2 or j>=len(lines)-2) and freq[line]>=max(2,len(pages)*.3):continue
                yield f'PDF第{i}页',line,False
    elif ext=='.docx':
        from docx import Document
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        doc=Document(io.BytesIO(raw));section=1
        for node in doc.element.body:
            loc=f'DOCX第{section}节'
            if node.tag.endswith('}p'):
                p=Paragraph(node,doc);runs=[r for r in p.runs if r.text.strip()]
                bold=bool(runs) and all(r.bold or '黑体' in r._r.xml for r in runs)
                for line in p.text.splitlines():yield loc,line,bold
                if node.xpath('./w:pPr/w:sectPr'):section+=1
            elif node.tag.endswith('}tbl'):
                for row in Table(node,doc).rows:yield loc,'| '+' | '.join(c.text for c in row.cells)+' |',False
    elif ext=='.txt':
        try:txt=raw.decode('utf-8-sig')
        except UnicodeDecodeError:txt=raw.decode('gb18030')
        for i,line in enumerate(txt.splitlines(),1):yield f'TXT第{i}行',line,False
    else:raise ValueError('支持 PDF、DOCX 和 TXT')

def parse(name,raw):
    lines=[(loc,s.strip().replace('．','.'),bold) for loc,s,bold in parts(name,raw) if s.strip()]
    corrections=[]
    for i,(loc,line,bold) in enumerate(lines):
        prefix=re.match(r'^([A-Z0-9]+(?:\s*\.\s*[\dO]+){1,3})(?![A-Za-z])',line)
        if prefix:
            number=re.sub(r'\s','',prefix[1])
            if 'O' in number[1:]:
                normalized=number[0]+number[1:].replace('O','0')
                corrections.append(f'{loc} 条号 {number} 按 {normalized} 提取，请核对')
                number=normalized
            lines[i]=(loc,number+line[prefix.end():],bold)
    # 编号、标题被 PDF 分成两行时先合并，单独的页码仍按页脚处理。
    merged=[]
    for i,(loc,line,bold) in enumerate(lines):
        if merged and merged[-1][0]==loc and re.fullmatch(r'\d{1,2}(?:\.\d{1,2})?',merged[-1][1]) and re.fullmatch(r'[\u4e00-\u9fff ]{2,24}',line) and i+1<len(lines) and re.match(NUM,lines[i+1][1]):
            merged[-1]=(loc,merged[-1][1]+' '+line,bold)
        else:merged.append((loc,line,bold))
    lines=merged
    head='\n'.join(s for loc,s,_ in lines if loc in ('PDF第1页','PDF第2页')) or '\n'.join(s for _,s,_ in lines[:28])
    found=re.search(CODE,name+' '+head,re.I)
    std=code(found[0]) if found else ''
    titles=[s for s in head.splitlines() if re.search(r'[\u4e00-\u9fff]{2}',s) and '中华人民共和国' not in s and len(s)<65 and re.search(r'(规程|规范|标准)$',s)]
    date=re.search(r'(\d{4})[年－/-](\d{1,2})[月－/-](\d{1,2})日?\s*实施',head)
    whole=bool(re.match(r'GB 55\d{3}-',std))
    meta=dict(id=hashlib.sha256(raw).hexdigest(),code=std,title=max(titles,key=len,default=Path(name).stem),whole_mandatory=whole,effective_date='%04d-%02d-%02d'%tuple(map(int,date.groups())) if date else '',source_name=name,categories=[],status='现行')
    starts=[i for i,(_,line,_) in enumerate(lines) if re.fullmatch(r'1\s*总\s*则',line)]
    start=None
    for i in starts:
        for _,line,_ in lines[i+1:i+9]:
            if re.fullmatch(r'1\s*总\s*则|条\s*文\s*说\s*明',line):break
            if re.match(r'1\.0\.\d+(?![\d.])',line) and not re.search(r'[.…·]{3,}\s*\d+$',line):
                start=i
                break
        if start is not None:break
    if start is None and starts:
        start=starts[0]
        corrections.append('总则后八行未识别正文条号，请核对目录起点')
    pre=''.join(s for _,s,_ in lines[:start if start is not None else 100])
    pre=re.sub(r'\s+','',pre)
    if '强制性条艾' in pre:
        corrections.append('公告文字层含“强制性条艾”，请对照公告校对强条清单')
        pre=pre.replace('强制性条艾','强制性条文')
    marks=set()
    for m in re.finditer(r'((?:第?\s*'+NUM+r'\s*(?:条|及|和|、|，|,|\s)*?)+)条?为强制性条文',pre):
        marks.update(re.findall(NUM,m[1]))
    rows={};warnings=corrections;chapter=section='';current=None;expl=False
    skipping=False
    for index,(loc,s,bold) in enumerate(lines[start or 0:],start or 0):
        if re.search(r'[.…·]{3,}\s*\d+$',s) or re.fullmatch(r'[-—]?\s*(?:\d+|[IVXLCDM]+)\s*[-—]?',s):continue
        tight=re.sub(r'\s','',s)
        if rows and re.fullmatch(r'(?:四[、.])?条文说明',tight):
            expl=True;skipping=False;current=None;continue
        if rows and tight in ('起草说明','附：条文说明','中华人民共和国国家标准','本规范用词说明','引用标准名录'):
            current=None;skipping=True
            if '条文说明' in tight:expl=True;skipping=False
            continue
        if skipping:continue
        if re.match(r'^附录\s*[A-Z](?:\s|$)',s):chapter=s;section='';current=None;continue
        m=re.match(r'^('+NUM+r')(?![\d.])\s*(.*)',s)
        if m and current and current['explanation' if expl else 'body'].rstrip().endswith('第') and m[2].startswith('条'):
            m=None
        if m:
            num,body=m.groups()
            if expl:
                span=re.match(r'^[～~至—-]\s*('+NUM+')',body)
                if span:warnings.append('区间说明 '+num+'～'+span[1]+'，请校对区间内各条说明')
                current=rows.get(num)
                if current:current['explanation']=(current['explanation']+'\n'+body).strip()
                else:warnings.append('说明无对应条文 '+num)
            elif num in rows:current=None;warnings.append('条号重复 '+num)
            else:
                if rows:
                    last=next(reversed(rows))
                    if last.rsplit('.',1)[0]==num.rsplit('.',1)[0] and int(num.split('.')[-1])>int(last.split('.')[-1])+1:warnings.append('条号跳号 '+last+' → '+num)
                current=rows[num]=dict(number=num,body=body,location=loc,chapter_path=' > '.join(filter(None,[chapter,section])),explanation='',mandatory=whole or bold or num in marks,enabled=True,edited=False)
            continue
        h=re.fullmatch(r'(\d{1,2})(?:\.(\d{1,2}))?\s*([\u3400-\u9fff][^\d。；，：]{0,29})',s)
        previous=current and current['explanation' if expl else 'body'].rstrip()
        if h and (not previous or previous.endswith(('。','；','：','！','？','.',';',':'))):
            major=int(h[1]);minor=int(h[2] or 0)
            old_major=int(chapter.split()[0]) if chapter and chapter.split()[0].isdigit() else 0
            old_minor=int(section.split()[0].split('.')[-1]) if section else 0
            if minor and major==old_major and minor>old_minor:
                section=f'{major}.{minor} {h[3]}';current=None;continue
            if not minor and major>old_major and (not current or any(re.match(h[1]+r'\.\d',line) for _,line,_ in lines[index+1:index+4])):
                chapter=f'{major} {h[3]}';section='';current=None;continue
        if current:
            k='explanation' if expl else 'body'
            current[k]=(current[k]+'\n'+s).strip()
    for n,row in rows.items():
        if not row['body'] or len(row['body'])>3000:warnings.append('正文为空或超过3000字 '+n)
    warnings.extend('强条未找到 '+n for n in sorted(marks-rows.keys()))
    if start is None:warnings.append('未识别到总则起点，请核对前言及目录')
    if not rows:warnings.append('未识别到条号')
    return dict(meta_guess=meta,clauses=list(rows.values()),warnings=warnings)


