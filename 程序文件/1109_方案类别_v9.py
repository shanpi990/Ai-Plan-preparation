"""按方案类别保存关注项，旧版关注项迁入通用类别。"""
import copy,datetime,json,re


def validate_library(data):
    if not isinstance(data,dict) or not isinstance(data.get('categories'),list) or not data['categories']:
        raise ValueError('请至少保留一个方案类别。')
    result=[];ids=set();names=set()
    for item in data['categories']:
        if not isinstance(item,dict):raise ValueError('方案类别格式错误。')
        key=item.get('id');name=item.get('name');focus=item.get('focus')
        if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',key) or key in ids:
            raise ValueError('方案类别编号不正确或重复。')
        if not isinstance(name,str) or not name.strip() or len(name.strip())>60 or name.strip() in names:
            raise ValueError('类别名称不能为空、重复或超过60字。')
        if not isinstance(focus,list) or any(not isinstance(x,str) for x in focus):raise ValueError('关注项格式错误。')
        result.append({'id':key,'name':name.strip(),'focus':list(dict.fromkeys(x.strip() for x in focus if x.strip()))})
        ids.add(key);names.add(name.strip())
    selected=data.get('selected',result[0]['id'])
    if selected not in ids:raise ValueError('所选方案类别不存在。')
    return {'categories':result,'selected':selected}


def load_library(root,legacy_focus=()):
    files=list(root.glob('*_方案类别关注项_v*.json'))
    if files:
        path=max(files,key=lambda p:p.stat().st_mtime_ns)
        try:return validate_library(json.loads(path.read_text(encoding='utf-8-sig')))
        except (json.JSONDecodeError,ValueError) as exc:raise ValueError('方案类别读取失败：'+str(exc))
    return {'selected':'general','categories':[
        {'id':'general','name':'通用','focus':list(legacy_focus)},
        {'id':'excavation','name':'深基坑','focus':[]},
        {'id':'formwork','name':'模板支架','focus':[]},
        {'id':'lifting','name':'起重吊装','focus':[]}]}


def save_library(root,data):
    library=validate_library(data)
    prefix=datetime.datetime.now().strftime('%m%d')+'_方案类别关注项'
    n=1
    while (root/f'{prefix}_v{n}.json').exists():n+=1
    (root/f'{prefix}_v{n}.json').write_text(json.dumps(library,ensure_ascii=False,indent=2),encoding='utf-8')
    return copy.deepcopy(library)
