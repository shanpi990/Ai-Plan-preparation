"""忽略排版差异匹配引文，返回能在原文中定位的原始摘句。"""
from string import punctuation

PUNCT = str.maketrans({'，': ',', '。': '.', '；': ';', '：': ':', '？': '?', '！': '!',
                       '（': '(', '）': ')', '【': '[', '】': ']', '％': '%',
                       '“': '"', '”': '"', '「': '"', '」': '"', '‘': "'", '’': "'",
                       '＂': '"', '＇': "'", '．': '.'})
PUNCT.update({ord(c)+0xFEE0: c for c in punctuation})


def normalized(text):
    return ''.join(text.translate(PUNCT).split())


def match_excerpt(source, quote):
    if not isinstance(quote, str) or not quote.strip():
        return ''
    if quote in source:
        return quote
    wanted = normalized(quote)
    offset = normalized(source).find(wanted)
    if offset < 0 or not wanted:
        return ''
    positions = [i for i, char in enumerate(source) if not char.isspace()]
    return source[positions[offset]:positions[offset + len(wanted) - 1] + 1]


def grouped_basis(issue):
    direct,related=[],[]
    for entry in issue.get('basis') or []:
        group=direct if entry.get('relation') in ('违反','未落实') else related
        group.append(entry)
    return direct,related


PARTIAL_REASON = '部分引文未能对应原文，已移除'

def resolve(values, refs, allowed, locate):
    """在相同来源中先核原段，再核唯一的相邻段，保留原文中的实际摘句。"""
    checked, changes = [], []
    if not isinstance(values, list):
        if values is not None:
            changes.append(dict(action='移除', reason='引文列表格式错误', original=values))
        return checked, changes
    for value in values:
        cite = value if isinstance(value, dict) else {}
        source, original, quote = (cite.get(k) for k in ('source', 'paragraph', 'quote'))
        event = dict(source=source, paragraph=original, quote=quote)
        try:
            if type(original) not in (int, str):
                raise ValueError
            pid = int(original)
        except ValueError:
            changes.append(dict(event, action='移除', reason='引用段号错误'))
            continue
        rows = refs.get(source, {}) if isinstance(source, str) else {}
        row = rows.get(pid)
        excerpt = match_excerpt(row['text'], quote) if row else ''
        target = pid
        if not excerpt:
            hits = [(n, match_excerpt(rows[n]['text'], quote))
                    for n in range(pid-3, pid+4) if n != pid and n in rows]
            hits = [(n, text) for n, text in hits if text]
            if len(hits) != 1:
                reason = '相邻段有多个匹配' if hits else '引用无法对应原文'
                changes.append(dict(event, action='移除', reason=reason))
                continue
            target, excerpt = hits[0]
        if allowed is not None and (source, target) not in allowed:
            changes.append(dict(event, action='移除', reason='引用不在本次发送范围内'))
            continue
        if target != pid:
            changes.append(dict(event, action='纠正', paragraph=pid, to=target))
        row = rows[target]
        checked.append(dict(source=source, paragraph=target, quote=excerpt, section=row.get('section',''),
                            page=row.get('page'), location=locate(row)))
    return checked, changes

def annotate(item, changes=(), parents=()):
    fixes = list(item.get('citationFixes', []))
    partial = item.get('partialCitations', False)
    for parent in parents:
        for fix in parent.get('citationFixes', []):
            if fix not in fixes:
                fixes.append(fix)
        partial |= bool(parent.get('partialCitations'))
    for event in changes:
        if event['action'] == '移除':
            partial = True
        elif event['action'] == '纠正':
            fix = {'source':event['source'], 'from':event['paragraph'], 'to':event['to'], 'quote':event['quote']}
            if fix not in fixes:
                fixes.append(fix)
    if fixes:
        item['citationFixes'] = fixes
    if partial:
        item.update(partialCitations=True, aiReview='待核', checkReason=PARTIAL_REASON)
    return item

def audit_rows(changes, kind, title, kept, error=''):
    rows = [dict(e, kind=kind, title=title, kept=kept) for e in changes]
    if not kept:
        rows.append(dict(action='整条丢弃', kind=kind, title=title, reason=error))
    return rows

def counts(events):
    return dict(dropped=sum(e['action']=='整条丢弃' for e in events),
                partialRemoved=sum(e['action']=='移除' and e['kept'] for e in events),
                corrected=sum(e['action']=='纠正' for e in events))
