"""相同方案两次独立审查的本地对照。段号、问题编号各自属于一轮审查。"""
from collections import Counter
from difflib import SequenceMatcher
import re
import unicodedata

THRESHOLD = 0.18
UNREVIEWED = '上一轮尚未复核，对照结果只能区分再报与未报'


def plan_refs(issue):
    return [c for c in issue.get('citations', []) if c.get('source') == 'plan']


def align(old, new):
    """相等文本作顺序锚点。长度不等的改动区，先配最相似的行。"""
    result = []
    def row(a, b):
        kind = '新增' if a is None else '删除' if b is None else '未变' if a['text'] == b['text'] else '改写'
        result.append({'old': a and a['id'], 'new': b and b['id'], 'kind': kind})

    def gap(a, b):
        if len(a) == len(b):
            for left, right in zip(a, b):
                row(left, right)
        elif not a or not b:
            for left in a:
                row(left, None)
            for right in b:
                row(None, right)
        else:
            # 大块重写没有可靠的段对段依据。保留为删除、新增供人核对。
            best = (0, 0, 0)
            if len(a) * len(b) <= 4096:
                for i, left in enumerate(a):
                    for j, right in enumerate(b):
                        score = SequenceMatcher(None, left['text'][:800], right['text'][:800], autojunk=False).ratio()
                        if score > best[0]:
                            best = (score, i, j)
            score, i, j = best
            if score < .25:
                gap(a, [])
                gap([], b)
            else:
                gap(a[:i], b[:j])
                row(a[i], b[j])
                gap(a[i+1:], b[j+1:])
    matcher = SequenceMatcher(None, [r['text'] for r in old], [r['text'] for r in new], autojunk=False)
    for _, a, b, c, d in matcher.get_opcodes():
        gap(old[a:b], new[c:d])
    return result


def features(issue):
    text = unicodedata.normalize('NFKC', issue['title']+' '+issue['description']).lower()
    text = ''.join(ch for ch in text if ch.isalnum())
    return set(zip(text, text[1:]))


def auto_pairs(previous, current, mapping):
    translated = {r['old']:r['new'] for r in mapping if r['old'] and r['new']}
    def prepare(items, before):
        vectors = []
        for issue in items:
            ids = {c['paragraph'] for c in plan_refs(issue)}
            if before:
                ids = {translated[p] for p in ids if p in translated}
            vectors.append((issue['id'], ids, features(issue)))
        return vectors
    edges = []
    right = prepare(current, False)
    for oid, op, ow in prepare(previous, True):
        nearby = {v+d for v in op for d in range(-3,4)}
        for nid, np, nw in right:
            if nearby.isdisjoint(np):
                continue
            score = len(ow & nw) / max(1, len(ow | nw))
            if score >= THRESHOLD:
                dist = min(abs(a-b) for a in op for b in np)
                edges.append((-score, dist, oid, nid))
    used = set()
    matched = {}
    for score, dist, oid, nid in sorted(edges):
        if oid not in matched and nid not in used:
            matched[oid] = dict(current=nid, score=round(-score,6), distance=dist)
            used.add(nid)
    return matched


def is_processed(review):
    return review.get('status') in ('已修改','确认修改','不采纳','退回补查')


def build(previous, current, oldrows, newrows, filename, digest):
    issues = previous['diagnosis']['issues']
    reviews = previous.get('reviews', {})
    mapping = align(oldrows, newrows)
    lookup = {r['old']:r for r in mapping if r['old']}
    left = {r['id']:r['text'] for r in oldrows}
    right = {r['id']:r['text'] for r in newrows}
    prior = []
    for issue in issues:
        oid = issue['id']
        citations = []
        for p in dict.fromkeys(c['paragraph'] for c in plan_refs(issue)):
            m = lookup[p]
            citations.append(dict(**m,before=left[p],after=right.get(m['new'],'')))
        prior.append(dict(id=oid,title=issue['title'],description=issue['description'],
                          priority=issue['priority'],review=reviews.get(oid,{}),citations=citations))
    return dict(version=1, filename=filename, sha256=digest, previous=prior, paragraphs=mapping,
                auto=auto_pairs(issues,current['issues'],mapping), manual={}, inherited={}, revision=0,
                hasReviews=any(is_processed(i['review']) for i in prior))


def adjust(state, oid, nid, current):
    if oid not in {r['id'] for r in state['previous']} or (nid is not None and nid not in {i['id'] for i in current}):
        raise ValueError('请选择当前两份记录中的问题。')
    if nid:
        for other, target in state['pairs'].items():
            if target == nid and other != oid:
                state['manual'][other] = None
    state['manual'][oid] = nid


def remove_inherited(state, reviews):
    clean = dict(reviews)
    for nid, prior in (state or {}).get('inherited',{}).items():
        if clean.get(nid) == prior['value']:
            if prior['before'] is None:
                clean.pop(nid,None)
            else:
                clean[nid] = prior['before']
    return clean


def evaluate(state, current, reviews):
    pairs = {oid:v['current'] for oid,v in state['auto'].items()}
    pairs.update(state['manual'])
    pairs = {oid:nid for oid,nid in pairs.items() if nid}
    if len(set(pairs.values())) != len(pairs):
        raise ValueError('同一条意见只能关联一次。')
    prior_inherited = state['inherited']
    # 曾手动覆盖继承的判断（包括改回待复核），后续调整配对时继续保留。
    overrides = set(state.get('overrides',[]))
    overrides.update(n for n,r in prior_inherited.items() if reviews.get(n) != r['value'])
    clean = remove_inherited(state,reviews)
    inherited = {}
    oldmarks, newmarks = {}, {}
    for issue in state['previous']:
        oid = issue['id']
        nid = pairs.get(oid)
        review = issue['review']
        status = review.get('status')
        if not state['hasReviews']:
            label = '再报' if nid else '未报'
        elif status == '已修改':
            label = '改得不彻底' if nid else '已解决'
        elif status == '确认修改':
            cites = issue['citations']
            label = '仍未修改' if cites and all(c['kind']=='未变' for c in cites) else '待确认'
        elif status == '不采纳':
            label = '此前不采纳' if nid else '无需处理'
            if nid and nid not in overrides and not is_processed(clean.get(nid,{})) and not clean.get(nid,{}).get('note'):
                note = '沿用上轮判断'
                if review.get('note'):
                    note += '。上轮理由：'+review['note']
                value = dict(status='不采纳',note=note)
                inherited[nid] = dict(before=clean.get(nid),value=value)
                clean[nid] = value
        else:
            label = '上轮未处理'
        oldmarks[oid] = label
        if nid:
            newmarks[nid] = label
    kinds = {r['new']:r['kind'] for r in state['paragraphs'] if r['new']}
    for i in current:
        if i['id'] in newmarks:
            continue
        refs = [kinds.get(c['paragraph']) for c in plan_refs(i)]
        if not state['hasReviews']:
            label = '本轮新增'
        elif '新增' in refs or '改写' in refs:
            label = '可能由修改引入'
        elif refs and all(k=='未变' for k in refs):
            label = '原文已有，上轮未报'
        else:
            label = '原文位置待核'
        newmarks[i['id']] = label
    state.update(pairs=pairs,oldMarks=oldmarks,newMarks=newmarks,overrides=sorted(overrides),inherited=inherited,
                 counts=dict(Counter(oldmarks.values())),newCount=len(current)-len(pairs),
                 newKinds=dict(Counter(newmarks[i['id']] for i in current if i['id'] not in set(pairs.values()))))
    state['revision'] += 1
    return clean


def markdown(state, current):
    now = {i['id']:i for i in current}
    lines = ['','## 复审对照','','上轮记录：'+state['filename'], 'SHA-256：'+state['sha256'],'']
    if not state['hasReviews']:
        lines.append(UNREVIEWED)
    lines.append('上轮 '+str(len(state['previous']))+' 条，'+'、'.join(k+' '+str(v) for k,v in state['counts'].items())+'。')
    lines.append('本轮新增 '+str(state['newCount'])+' 条。'+'、'.join(k+' '+str(v) for k,v in state['newKinds'].items()))
    for label in ('改得不彻底','仍未修改'):
        lines.extend(['','### '+label,''])
        rows = [i for i in state['previous'] if state['oldMarks'][i['id']]==label]
        if not rows:
            lines.append('0 条')
        for i in rows:
            n = now.get(state['pairs'].get(i['id']))
            lines.append('- 上轮 '+i['id']+' '+i['title']+' → '+('本轮 '+n['id']+' '+n['title'] if n else '本轮未报'))
            lines.append('  '+i['description'])
            if n:
                lines.append('  本轮意见：'+n['description'])
            for r in i['citations']:
                lines.append('  原 P'+str(r['old'])+' → '+('本轮 P'+str(r['new']) if r['new'] else '已删除')+'（'+r['kind']+'）')
    return '\n'.join(lines)+'\n'
