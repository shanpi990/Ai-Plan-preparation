"""相同方案两次独立审查的本地对照。段号、问题编号各自属于一轮审查。"""
from collections import Counter
from difflib import SequenceMatcher
import re
import unicodedata

THRESHOLD = 0.18
WEAK_THRESHOLD = 0.085
WEAK_RADIUS = 8
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


def section_key(row):
    """整条标题路径可区分不同章中同名的最末级标题。无标题不作同节。"""
    path = row.get('chapterPath') or row.get('chapter') or row.get('section') or ''
    if isinstance(path,str):
        path=path.split('→')
    keys = [v.strip() for v in path if isinstance(v,str) and v.strip()]
    if keys and re.match(r'^(?:表|图)\s*\d',keys[-1]):
        keys.pop()
    return tuple(keys) if keys and keys != ['文档开头'] and keys != ['正文'] else ()


def weak_candidates(previous, current, rows):
    sections = {r['id']:section_key(r) for r in rows}
    right = []
    for i in current:
        refs = plan_refs(i)
        ids = {c['paragraph'] for c in refs}
        paths = {sections.get(c['paragraph']) or section_key(c) for c in refs}
        right.append((i['id'],ids,paths-{()},features(i)))
    hints = {}
    for old in previous:
        if old['review'].get('status') != '已修改':
            continue
        ids = {c['new'] for c in old['citations'] if c['new'] is not None}
        paths = {sections.get(c['new']) or tuple(c.get('oldSection',())) for c in old['citations']} - {()}
        words = features(old)
        candidates = []
        for nid, refs, titles, other in right:
            common = paths & titles
            distance = min((abs(a-b) for a in ids for b in refs),default=None)
            if not common and (distance is None or distance > WEAK_RADIUS):
                continue
            similarity = len(words & other) / max(1,len(words | other))
            if similarity > WEAK_THRESHOLD:
                candidates.append(dict(current=nid,score=round(similarity,6),distance=distance,
                                       section=' → '.join(sorted(common)[0]) if common else ''))
        if candidates:
            hints[old['id']] = sorted(candidates,key=lambda x:(-x['score'],x['current']))
    return hints


def decide(state, oid, nid, outcome):
    hints = state['weak'].get(oid,[])
    previous = state['decisions'].get(oid)
    if outcome=='reset' and previous:
        state['decisions'].pop(oid)
        return
    if not hints or (oid in state['pairs'] and not previous):
        raise ValueError('当前问题没有待确认的弱关联。')
    if outcome=='residual' and nid in {h['current'] for h in hints}:
        state['decisions'][oid] = dict(result=outcome,current=nid)
    elif outcome=='unreported' and nid is None:
        state['decisions'][oid] = dict(result=outcome)
    else:
        raise ValueError('请选择本条问题的候选意见或确认本轮未再报。')


def upgrade(state,current,rows):
    """旧对照记录已有段号映射、上轮意见与人工配对，直接补算弱关联。"""
    state.update(version=2,weak=weak_candidates(state['previous'],current,rows),decisions={})


def is_processed(review):
    return review.get('status') in ('已修改','确认修改','不采纳','退回补查')


def build(previous, current, oldrows, newrows, filename, digest):
    issues = previous['diagnosis']['issues']
    reviews = previous.get('reviews', {})
    mapping = align(oldrows, newrows)
    lookup = {r['old']:r for r in mapping if r['old']}
    left = {r['id']:r for r in oldrows}
    right = {r['id']:r['text'] for r in newrows}
    prior = []
    for issue in issues:
        oid = issue['id']
        citations = []
        for p in dict.fromkeys(c['paragraph'] for c in plan_refs(issue)):
            m = lookup[p]
            citations.append(dict(**m,before=left[p]['text'],after=right.get(m['new'],''),oldSection=list(section_key(left[p]))))
        prior.append(dict(id=oid,title=issue['title'],description=issue['description'],
                          priority=issue['priority'],review=reviews.get(oid,{}),citations=citations))
    return dict(version=2, weak=weak_candidates(prior,current['issues'],newrows), decisions={}, filename=filename, sha256=digest, previous=prior, paragraphs=mapping,
                auto=auto_pairs(issues,current['issues'],mapping), manual={}, inherited={}, revision=0,
                hasReviews=any(is_processed(i['review']) for i in prior))


def adjust(state, oid, nid, current):
    if oid not in {r['id'] for r in state['previous']} or (nid is not None and nid not in {i['id'] for i in current}):
        raise ValueError('请选择当前两份记录中的问题。')
    state['decisions'].pop(oid,None)
    if nid:
        for other, target in state['pairs'].items():
            if target == nid and other != oid:
                state['manual'][other] = None
                state['decisions'].pop(other,None)
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
    # 一条候选可证明多个上轮问题。优先保留已存在的正式关联。
    occupied=set(pairs.values())
    for oid, decision in state['decisions'].items():
        nid=decision.get('current')
        if decision['result']=='residual' and oid not in pairs and nid not in occupied:
            pairs[oid]=nid
            occupied.add(nid)
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
            decision = state['decisions'].get(oid,{}).get('result')
            if nid or decision=='residual':
                label = '改得不彻底'
            elif not decision and state['weak'].get(oid):
                label = '疑似未解决'
            else:
                label = '本轮未再报'
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
    lines.append('“本轮未再报”只表示本轮没有报出同一条意见。整改是否到位仍需核对原文。')
    for label in ('改得不彻底','仍未修改','疑似未解决'):
        lines.extend(['','### '+label,''])
        rows = [i for i in state['previous'] if state['oldMarks'][i['id']]==label]
        if not rows:
            lines.append('0 条')
        for i in rows:
            oid=i['id']
            decision=state['decisions'].get(oid,{})
            n = now.get(state['pairs'].get(oid) or decision.get('current'))
            lines.append('- 上轮 '+i['id']+' '+i['title']+' → '+('本轮 '+n['id']+' '+n['title'] if n else ('待人工确认' if label=='疑似未解决' else '本轮未报')))
            lines.append('  '+i['description'])
            if n:
                lines.append('  本轮意见：'+n['description'])
            if decision:
                lines.append('  人工确认：'+label)
            if label=='疑似未解决':
                for h in state['weak'][oid]:
                    lines.append('  候选 '+h['current']+' · '+now[h['current']]['title'])
            for r in i['citations']:
                lines.append('  原 P'+str(r['old'])+' → '+('本轮 P'+str(r['new']) if r['new'] else '已删除')+'（'+r['kind']+'）')
    return '\n'.join(lines)+'\n'
