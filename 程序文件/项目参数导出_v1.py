"""把有方案原文依据的项目参数导出给编制助手。"""
from datetime import datetime
import json
from pathlib import Path
import re
from threading import Lock


SAVE_LOCK = Lock()


def build(job, document):
    source = job['document']
    digest = source.get('sha256', '')
    if not re.fullmatch(r'[0-9a-fA-F]{64}', digest) or document.get('sha256') != digest:
        raise ValueError('参数与方案原文未关联，请先关联本次审查的原文件。')
    name = Path(source['name']).name
    rows = {row['id']: row for row in document['rows']}
    accepted = []
    for item in job['parameters']:
        refs = []
        for citation in item.get('citations') or []:
            if citation.get('source') != 'plan':
                continue
            number, quote = citation.get('paragraph'), citation.get('quote')
            row = rows.get(number) if type(number) is int else None
            if row and isinstance(quote, str) and quote.strip() and quote in row['text']:
                refs.append(dict(paragraph=number, section=row.get('section') or '', quote=quote))
        if refs and item['name'].strip() and item['value'].strip():
            accepted.append(dict(label=item['name'], zone=item.get('scope') or '', value=item['value'],
                                 unit=item.get('unit') or '', origin='已有方案提取', citations=refs))
    package = dict(schema='bianshen-params/v1', exportedAt=datetime.now().astimezone().isoformat(timespec='seconds'),
                   sourceDocument=dict(name=name, sha256=digest), parameters=accepted)
    return dict(package=package, filename=Path(name).stem+'.项目参数.json', exported=len(accepted),
                skipped=len(job['parameters'])-len(accepted))


def save(result, path, atomic_json):
    summary = {key: result[key] for key in ('filename', 'exported', 'skipped')}
    if not result['exported']:
        return summary
    if not path.name.endswith('.项目参数.json'):
        raise ValueError('文件名须以「.项目参数.json」结尾，供编制助手识别。')
    with SAVE_LOCK:
        if path.exists():
            try:
                previous = json.loads(path.read_bytes())
            except (OSError, ValueError):
                previous = None
            keys = ('schema', 'sourceDocument', 'parameters')
            if not isinstance(previous, dict) or any(previous.get(k) != result['package'][k] for k in keys):
                raise ValueError('已有同名文件且内容不同，请另选文件名或保存位置。')
        else:
            atomic_json(path, result['package'])
    return dict(summary, path=str(path))
