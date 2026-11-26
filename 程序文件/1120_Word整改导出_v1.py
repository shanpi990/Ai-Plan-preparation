"""在原 DOCX 包内按 run 写修订和批注，并从磁盘独立读回核对。"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from lxml import etree as ET
import hashlib
import io
import json
import posixpath
import re
import zipfile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
REL = '{http://schemas.openxmlformats.org/package/2006/relationships}'
CT = '{http://schemas.openxmlformats.org/package/2006/content-types}'
COMMENTS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments'
DOC = 'word/document.xml'
RELS = 'word/_rels/document.xml.rels'
TYPES = '[Content_Types].xml'
CONTROLS = {W+'tab': ' ', W+'br': '\n', W+'cr': '\n'}
PLACEHOLDER = re.compile(r'【待补[：:][^】\n]+】')
SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def diff(before, after):
    return SequenceMatcher(None, before, after, autojunk=False).get_opcodes()


def preview(before, after, op):
    if op == 'insert_after':
        return [['ins', after]]
    result = []
    for kind, a, b, c, d in diff(before, after):
        if kind in ('replace', 'delete'):
            result.append(['del', before[a:b]])
        if kind in ('replace', 'insert', 'equal'):
            result.append(['equal' if kind == 'equal' else 'ins', after[c:d]])
    return result


def surface(p):
    """只接受可无损拆分的普通 run；书签和批注标记保留在原处。"""
    pieces = []
    def content(parent):
        for n in parent:
            if n.tag==W+'hyperlink':
                yield from content(n)
            else:
                yield n
    for child in content(p):
        if child.tag in {W+t for t in ('pPr','bookmarkStart','bookmarkEnd','commentRangeStart','commentRangeEnd','proofErr','permStart','permEnd')}:
            continue
        if child.tag != W+'r':
            return None
        for n in child:
            if n.tag == W+'t':
                pieces.append((n, n.text or ''))
            elif n.tag in CONTROLS:
                pieces.append((n, CONTROLS[n.tag]))
            elif n.tag not in (W+'rPr', W+'commentReference', W+'lastRenderedPageBreak'):
                return None
    return pieces


def plan_changes(p, before, after):
    units = surface(p)
    if units is None:
        raise ValueError('含域、公式、图片或复杂对象，只能批注或在段后新增。')
    original = ''.join(t for _, t in units)
    if original.strip() != before or not before or not isinstance(after, str) or not after.strip():
        raise ValueError('替换原文无法对应，或修改后文字为空。')
    start = len(original) - len(original.lstrip())
    # 只对用户所见的正文做 diff，保留两侧空白。
    operations = [(kind,a+start,b+start,c,d) for kind,a,b,c,d in diff(before,after)]
    offsets = []
    pos = 0
    for node, value in units:
        offsets.append((node, pos, pos+len(value)))
        pos += len(value)
    chunks = defaultdict(list)
    for kind, a, b, c, d in operations:
        if kind == 'equal':
            continue
        if '\t' in after[c:d] or '\n' in after[c:d] or '\r' in after[c:d]:
            raise ValueError('不能新增或移动制表符、换行符，请使用段后新增。')
        for node, lo, hi in offsets:
            if a < hi and lo < b:
                if node.tag != W+'t':
                    raise ValueError('修改跨越制表符或换行符，请分开修改两侧文字。')
                chunks[node].append((max(a,lo)-lo,min(b,hi)-lo,'del',''))
        if d > c:
            # 替换继承首个被改字符的格式，插入优先继承左侧文字。
            options = [(n,lo,hi) for n,lo,hi in offsets if n.tag == W+'t' and lo <= a <= hi]
            if not options:
                raise ValueError('新增文字无法定位到制表符或换行符两侧的文字。')
            node,lo,_ = options[-1] if b>a else options[0]
            chunks[node].append((a-lo,a-lo,'ins',after[c:d]))
    return chunks, original[:start] + after + original[start+len(before):]


def word_text(tag, value):
    node = ET.Element(W+tag)
    node.text = value
    if value != value.strip():
        node.set(SPACE,'preserve')
    return node


class Revisions:
    def __init__(self, tree):
        self.current = max((int(v) for v in tree.xpath('//@w:id',namespaces={'w':W[1:-1]}) if v.isdigit()),default=0)
        self.date = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
        self.ids = set()

    def mark(self, kind):
        self.current += 1
        val = str(self.current)
        self.ids.add(val)
        return ET.Element(W+kind, {W+'id':val,W+'author':'AI审查',W+'date':self.date})


def patch(p, before, after, revisions=None):
    chunks, expected = plan_changes(p,before,after)
    for run in list(p.iter(W+'r')):
        if not any(n in chunks for n in run):
            continue
        prop = run.find(W+'rPr')
        def emit(node, kind='equal'):
            if kind == 'del' and not revisions:
                return
            r = ET.Element(W+'r',dict(run.attrib))
            if prop is not None:
                r.append(deepcopy(prop))
            r.append(node)
            if revisions and kind != 'equal':
                mark = revisions.mark(kind)
                mark.append(r)
                run.addprevious(mark)
            else:
                run.addprevious(r)
        for node in list(run):
            if node is prop:
                continue
            if node not in chunks:
                emit(deepcopy(node))
                continue
            cursor = 0
            value = node.text or ''
            for lo,hi,kind,new in sorted(chunks[node],key=lambda x:(x[0],x[1])):
                if cursor < lo:
                    emit(word_text('t',value[cursor:lo]))
                if kind == 'ins':
                    emit(word_text('t',new),'ins')
                else:
                    emit(word_text('delText',value[lo:hi]),'del')
                cursor = max(cursor,hi)
            if cursor < len(value):
                emit(word_text('t',value[cursor:]))
        run.getparent().remove(run)
    return expected


def insert_block(anchor, template, lines, revisions):
    last = anchor
    for text in lines:
        p = ET.Element(W+'p')
        prop = template.find(W+'pPr')
        pr = deepcopy(prop) if prop is not None else ET.Element(W+'pPr')
        for child in list(pr):
            if child.tag in (W+'sectPr',W+'pPrChange'):
                pr.remove(child)
        rp = pr.find(W+'rPr')
        if rp is not None:
            for n in list(rp):
                if n.tag in (W+'ins',W+'del',W+'rPrChange'):
                    rp.remove(n)
        if revisions:
            if rp is None:
                rp = ET.SubElement(pr,W+'rPr')
            rp.append(revisions.mark('ins'))
        if len(pr):
            p.append(pr)
        r = ET.Element(W+'r')
        first = next((r for r in template.iter(W+'r') if r.find(W+'t') is not None),None)
        style = first.find(W+'rPr') if first is not None else None
        if style is not None:
            r.append(deepcopy(style))
        r.append(word_text('t',text))
        parent = ET.SubElement(p,W+'ins',dict(revisions.mark('ins').attrib)) if revisions else p
        parent.append(r)
        last.addnext(p)
        last = p
    return last


def comment_text(i):
    text = '[{} {} {}] {}｜{}｜{}'.format(*(i.get(k,'') for k in ('id','priority','category','title','description','suggestion')))
    refs = [str(v['ref']) for v in i.get('basis',[]) if v.get('relation') in ('违反','未落实') and v.get('ref')]
    if refs:
        text += '｜规范依据：'+'、'.join(refs)
    if i.get('aiReview') == '待核' or i.get('checkStatus') == '待核' or i.get('checkReason'):
        text += '｜待核 '+str(i.get('checkReason',''))
    return text


def xml(tree):
    return ET.tostring(tree,encoding='UTF-8',xml_declaration=True,standalone=True)


def add_comments(z, tree, indexed, notes, rev):
    rels = ET.fromstring(z.read(RELS))
    types = ET.fromstring(z.read(TYPES))
    rel = next((r for r in rels if r.get('Type') == COMMENTS),None)
    if rel is None:
        target = 'word/comments.xml'
        ids = {r.get('Id') for r in rels}
        num = 1
        while 'rId'+str(num) in ids:
            num += 1
        ET.SubElement(rels,REL+'Relationship',Id='rId'+str(num),Type=COMMENTS,Target='comments.xml')
    else:
        name = rel.get('Target')
        target = name.lstrip('/') if name.startswith('/') else posixpath.normpath(posixpath.join('word',name))
    comments = ET.fromstring(z.read(target)) if target in z.namelist() else ET.Element(W+'comments',nsmap={'w':W[1:-1]})
    if not any(t.get('PartName') == '/'+target for t in types):
        ET.SubElement(types,CT+'Override',PartName='/'+target,ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml')
    used = {n.get(W+'id') for n in comments}
    for tag in ('commentRangeStart','commentRangeEnd','commentReference'):
        used.update(n.get(W+'id') for n in tree.iter(W+tag))
    number = max((int(v) for v in used if v and v.isdigit()),default=-1) + 1
    anchors = {}
    for issue, pid in notes:
        cid = str(number)
        number += 1
        p = indexed[pid]
        start = ET.Element(W+'commentRangeStart',{W+'id':cid})
        p.insert(int(p.find(W+'pPr') is not None),start)
        ET.SubElement(p,W+'commentRangeEnd',{W+'id':cid})
        r = ET.SubElement(p,W+'r')
        ET.SubElement(r,W+'commentReference',{W+'id':cid})
        c = ET.SubElement(comments,W+'comment',{W+'id':cid,W+'author':'AI审查',W+'date':rev.date})
        ET.SubElement(ET.SubElement(c,W+'p'),W+'r').append(word_text('t',comment_text(issue)))
        anchors[cid] = pid
    return {target:xml(comments),RELS:xml(rels),TYPES:xml(types)}, anchors, target


def body_text(p, reject_ids=()):
    """逐段读取显示文本。嵌套文本框段落单独核对，域指令与数学文本亦参与校验。"""
    out = []
    def visit(n):
        if n.tag == W+'p' or n.tag == W+'pPr':
            return
        if n.tag == W+'del' and n.get(W+'id') not in reject_ids:
            return
        if n.tag == W+'ins' and n.get(W+'id') in reject_ids:
            return
        if n.tag in (W+'t',W+'delText',W+'instrText','{http://schemas.openxmlformats.org/officeDocument/2006/math}t'):
            out.append(n.text or '')
        elif n.tag in CONTROLS:
            out.append('\t' if n.tag == W+'tab' else '\n')
        else:
            for c in n:
                visit(c)
    for n in p:
        visit(n)
    return ''.join(out)


def structure(tree, z):
    return {'表格':sum(1 for _ in tree.iter(W+'tbl')),'节属性':sum(1 for _ in tree.iter(W+'sectPr')),
            '图形':sum(1 for n in tree.iter() if n.tag in (W+'drawing',W+'pict')),
            '图片文件': sorted(n for n in z.namelist() if n.startswith('word/media/'))}


def verify(path, accepted, original, expected_structure, rev, anchors, comment_part):
    errors = []
    with zipfile.ZipFile(path) as z:
        tree = ET.fromstring(z.read(DOC))
        paragraphs = list(tree.iter(W+'p'))
        for name, expected, reject in [('接受',accepted,set()),('拒绝',original,rev.ids)]:
            if name == '拒绝' and not reject:
                continue
            actual = []
            for p in paragraphs:
                mark = p.find(W+'pPr/'+W+'rPr/'+W+'ins')
                if mark is not None and mark.get(W+'id') in reject:
                    continue
                actual.append(body_text(p,reject))
            if len(actual)!=len(expected):
                errors.append(f'{name}视图段落数：预计 {len(expected)}，实际 {len(actual)}')
            for index,(got,want) in enumerate(zip(actual,expected),1):
                if got != want:
                    errors.append(f'{name}视图第 {index} 个原生段落：预计 {want[:100]!r}，实际 {got[:100]!r}')
                    break
        if structure(tree,z) != expected_structure:
            errors.append('表格、图片或节数量发生变化')
        if anchors:
            comments = ET.fromstring(z.read(comment_part))
            existing = Counter(n.get(W+'id') for n in comments)
            for cid, index in anchors.items():
                if existing[cid]!=1 or index>=len(paragraphs) or any(not any(n.get(W+'id')==cid for n in paragraphs[index].iter(W+tag)) for tag in ('commentRangeStart','commentRangeEnd','commentReference')):
                    errors.append(f'批注 {cid} 未对应预计段落 {index+1}')
    return dict(passed=not errors,errors=errors,sourceParagraphs=len(original),acceptedParagraphs=len(accepted),
                comments=len(anchors),tables=expected_structure['表格'],media=len(expected_structure['图片文件']),
                drawings=expected_structure['图形'],sections=expected_structure['节属性'],revisions=len(rev.ids))


def export(doc,raw,edits,notes,dest,nodes,mode):
    if Path(doc['name']).suffix.lower()!='.docx' or hashlib.sha256(raw).hexdigest()!=doc['sha256']:
        raise ValueError('请关联与审查记录一致的原始 DOCX。')
    tree, ps = nodes(raw)
    indexed = {r['id']:p for r,p in zip(doc['rows'],ps)}
    all_p = list(tree.iter(W+'p'))
    positions = {p:i for i,p in enumerate(all_p)}
    original = [body_text(p) for p in all_p]
    expected = original.copy()
    extra = defaultdict(list)
    tail = {}
    rev = Revisions(tree)
    tracked = rev if mode == 'tracked' else None
    headings = {h['paragraph'] for h in doc.get('headings',[]) if 'paragraph' in h}
    for e in edits:
        pid = e['paragraph']
        p = indexed[pid]
        i = positions[p]
        if e.get('op','replace')=='replace':
            # 用独立的原文显示（保留原生制表符）构造预期文本。
            preview_text = original[i]
            offset = len(preview_text)-len(preview_text.lstrip())
            after = list(e['after'])
            for k,a,b,c,d in diff(e['before'],e['after']):
                if k=='equal':
                    after[c:d]=preview_text[offset+a:offset+b]
            expected[i]=preview_text[:offset]+''.join(after)+preview_text[offset+len(e['before']):]
            patch(p,e['before'],e['after'],tracked)
        else:
            template = p
            if pid in headings:
                template = next((indexed[k] for k in indexed if k>pid and k not in headings and indexed[k].find(W+'r/'+W+'t') is not None),p)
            tail[pid] = insert_block(tail.get(pid,p),template,e['paragraphs'],tracked)
            # 新段是兄弟节点，复杂锚点的文本框后代仍在锚点内部。
            end = max((positions[q] for q in p.iter(W+'p')),default=i)
            extra[end].extend(e['paragraphs'])
    accepted = [v for i,s in enumerate(expected) for v in [s,*extra.get(i,[])]]
    with zipfile.ZipFile(io.BytesIO(raw)) as src:
        counts = structure(ET.fromstring(src.read(DOC)),src)
        changes, anchors, part = add_comments(src,tree,indexed,notes,rev) if notes else ({},{},None)
        new_positions = {p:i for i,p in enumerate(tree.iter(W+'p'))}
        refs = {cid:new_positions[indexed[pid]] for cid,pid in anchors.items()}
        changes[DOC] = xml(tree)
        with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as out:
            for info in src.infolist():
                out.writestr(info,changes.pop(info.filename) if info.filename in changes else src.read(info))
            for name, value in changes.items():
                out.writestr(name,value)
    return verify(dest,accepted,original,counts,rev,refs,part)

