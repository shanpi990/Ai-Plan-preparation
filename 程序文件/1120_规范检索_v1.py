import json,math,re,sqlite3,threading
from contextlib import closing
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DB=ROOT.parent/'配置文件/1120_规范原文库_v1.sqlite3'
TERMS=(ROOT.parent/'配置文件/1120_施工术语表_v1.txt').read_text('utf-8-sig').split()
CACHE={};LOCK=threading.Lock()
def grams(s,k):
    return [v[i:i+k] for v in re.findall(r'[\u3400-\u9fff]+',s) for i in range(len(v)-k+1) if v[i:i+k] not in ('应符合','应按照','的规定','的要求')]
def book_reservations(ranked, book_for):
    """先给每本命中规范一个位置，再为有第二条的规范分配第二轮。"""
    first, second = [], []
    counts = Counter()
    for candidate in ranked:
        book = book_for(candidate)
        if counts[book] == 0:
            first.append(candidate)
        elif counts[book] == 1:
            second.append(candidate)
        counts[book] += 1
    return first + second


def fit_excerpts(ordered, budget, reserved_refs=(), priority_refs=()):
    """先为保留的条目分配原文，余下字符按传入的优先顺序使用。"""
    if sum(len(row['text']) for row in ordered) <= budget:
        return ordered
    by_ref = {row['ref']: row for row in ordered}
    # 先按第一轮、第二轮的顺序给保底条目留位。字符数少于席位数时也保持这个顺序。
    reserved = list(dict.fromkeys(reserved_refs))[:budget]
    book_for = {ref: ref.split('#', 1)[0] for ref in by_ref}
    limits = dict.fromkeys(reserved, 1)
    available = Counter()
    if reserved:
        demand = Counter()
        for ref, row in by_ref.items():
            demand[book_for[ref]] += len(row['text']) - limits.get(ref, 0)
        # 用各书入选正文长度分摊缩减量，以免排在最后的一本承担全部截断。
        remainder = budget - len(reserved)
        total = sum(demand.values())
        fractions = {}
        for book, length in demand.items():
            available[book], fractions[book] = divmod(remainder * length, total)
        for book in sorted(fractions, key=fractions.get, reverse=True)[:remainder-sum(available.values())]:
            available[book] += 1

        priority_set = set(priority_refs)
        for ref in priority_refs:
            book = book_for[ref]
            size = limits.get(ref, 0)
            extra = min(available[book], len(by_ref[ref]['text']) - size)
            limits[ref] = size + extra
            available[book] -= extra
        protected = defaultdict(list)
        for ref in reserved:
            if ref in priority_set:
                continue
            protected[book_for[ref]].append(ref)
        for book, refs in protected.items():
            for index, ref in enumerate(sorted(refs, key=lambda ref: len(by_ref[ref]['text']))):
                count = len(refs) - index
                share = (available[book] + count - 1) // count
                extra = min(len(by_ref[ref]['text']) - 1, share)
                limits[ref] += extra
                available[book] -= extra

    result = []
    for row in ordered:
        ref = row['ref']
        if ref in limits:
            size = limits[ref]
        elif reserved:
            book = book_for[ref]
            size = min(available[book], len(row['text']))
            available[book] -= size
        else:
            size = min(budget, len(row['text']))
            budget -= size
        if size:
            result.append(dict(row, text=row['text'][:size]))
    return result


def retrieve(text,*,book_ids,category=None,top_k=12,char_budget=6000,must_include_mandatory=True,backend='auto',database=None,only_mandatory=False,with_source=False,demote_refs=(),reserve_per_book=True):
    if not book_ids or not text or top_k <= 0 or char_budget <= 0:return []
    db=Path(database or DB)
    with LOCK:
        stamp=(str(db),db.stat().st_mtime_ns,db.stat().st_size)
        if stamp not in CACHE:
            with closing(sqlite3.connect(db)) as c:
                c.row_factory=sqlite3.Row
                rows={r['id']:dict(r) for r in c.execute("select c.*,b.code,b.categories,b.whole_mandatory from clause c join book b on b.id=c.book_id where c.enabled=1")}
            index=defaultdict(dict);length={};trigram_df=Counter()
            for i,r in rows.items():
                terms=Counter(grams((r['chapter_path'] or '')+' '+r['body'],2));length[i]=sum(terms.values())
                trigram_df.update(set(grams(r["body"]+" "+(r["chapter_path"] or ""),3)))
                for term,f in terms.items():index[term][i]=f
            CACHE.clear();CACHE[stamp]=(rows,index,length,trigram_df)
        rows,index,length,trigram_df=CACHE[stamp]
    allowed={i for i,r in rows.items() if r['book_id'] in book_ids and (not category or not json.loads(r['categories']) or category in json.loads(r['categories'])) and (not only_mandatory or r['mandatory'])}
    scores=Counter();terms=[t for t in TERMS if t in text]
    relevant=set(grams(text,3)).intersection(trigram_df)
    ranked_terms=sorted(relevant,key=lambda t:(trigram_df[t],t))
    queries=list(dict.fromkeys(terms+ranked_terms))[:420]
    if backend!='python' and queries:
        try:
            with closing(sqlite3.connect(db)) as c:
                for i,rank in c.execute('select rowid,bm25(clause_fts,1,2,1) from clause_fts where clause_fts match ?',(' OR '.join('"'+q+'"' for q in queries if len(q)>=3) or '""',)):
                    if i in allowed:scores[i]=-rank
        except sqlite3.OperationalError:
            if backend=='fts':raise
            backend='python'
    if backend=='python' or not scores:
        mean=sum(length.values())/max(1,len(length))
        for token in set(grams(text,2)):
            posting=index.get(token,{})
            idf=math.log1p((len(rows)-len(posting)+.5)/(len(posting)+.5))
            for i,f in posting.items():
                if i in allowed:scores[i]+=idf*f*2.2/(f+1.2*(.25+.75*length[i]/max(mean,1)))
    single_mandatory = {i for i in allowed if rows[i]['mandatory'] and not rows[i]['whole_mandatory']}
    exact=set()
    compact=re.sub(r'\s','',text.upper())
    for i in allowed:
        r=rows[i]
        if compact==r['number'] or re.search(re.escape(r['code'].replace(' ','').upper())+r'(?:第|#)?'+re.escape(r['number'])+r'(?![\d.])',compact):exact.add(i);scores[i]+=1
        for term in terms:
            if term in (r['chapter_path'] or ''):scores[i]+=2
            elif term in r['body']:scores[i]+=.5
        if i in single_mandatory:scores[i]*=1.5
    demoted=set(demote_refs)
    for i in scores:
        if i not in exact and rows[i]['code']+'#'+rows[i]['number'] in demoted:
            scores[i]*=.35
    ranked = sorted((i for i in scores if scores[i] > 0),
                    key=lambda i: (i not in exact, -scores[i], rows[i]['ord'], i))
    if must_include_mandatory and not exact.intersection(single_mandatory):
        strong = next((i for i in ranked if i in single_mandatory), None)
        if strong is not None:
            ranked.remove(strong)
            ranked.insert(len(exact), strong)

    reserved = book_reservations(ranked, lambda i: rows[i]['book_id'])[:top_k] if reserve_per_book else []
    chosen = set(reserved)
    for i in ranked:
        if len(chosen) >= top_k:
            break
        chosen.add(i)
    selected = [i for i in ranked if i in chosen]
    if must_include_mandatory and sum(min(800, len(rows[i]['body'])) for i in selected) > char_budget:
        selected.sort(key=lambda i: (i not in exact, i not in single_mandatory))

    result = []
    for i in selected:
        r = rows[i]
        entry = dict(ref=r['code']+'#'+r['number'], book_id=r['book_id'], code=r['code'],
                     number=r['number'], chapter_path=r['chapter_path'], mandatory=bool(r['mandatory']),
                     whole_mandatory=bool(r['whole_mandatory']), text=r['body'][:800], score=round(scores[i],5))
        if with_source:
            entry.update(original=r['body'], explanation=r['explanation'] or '', location=r['location'])
        result.append(entry)
    reserved_refs = [rows[i]['code']+'#'+rows[i]['number'] for i in reserved]
    priority_refs = [item['ref'] for i,item in zip(selected,result)
                     if i in exact or (must_include_mandatory and i in single_mandatory)]
    return fit_excerpts(result, char_budget, reserved_refs, priority_refs)
