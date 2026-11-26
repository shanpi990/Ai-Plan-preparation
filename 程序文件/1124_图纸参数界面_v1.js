(() => {
    const box=document.createElement('details');
    box.id='drawingPanel';box.className='panel input-panel';box.hidden=true;
    $('#tab-review').prepend(box);
    const css=document.createElement('style');
    css.textContent='#drawingPanel{margin-bottom:16px}#drawingPanel summary{cursor:pointer;font-weight:650}#drawingPanel .drbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:10px 0}#drawingPanel .drrows{max-height:380px;overflow:auto}#drawingPanel table{border-collapse:collapse;width:100%}#drawingPanel td,#drawingPanel th{padding:6px 8px;text-align:left;border-bottom:1px solid var(--line)}#drawingPanel td input[type=text]{width:100%;min-width:100px}#drawingPanel [data-conflict]{color:#a1580d}#drawingPanel progress{width:min(400px,75%)}#drawingSource{max-width:90vw;max-height:90vh;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:8px}#drawingSource img{display:block;max-width:85vw;max-height:72vh;object-fit:contain}';
    document.head.append(css);
    box.innerHTML='<summary></summary><div class="drbar"><label>上传图纸 PDF <input id="drawingFiles" type="file" multiple accept=".pdf"></label><button id="drawingRead">读图并提取</button><button id="drawingCancel" hidden>取消</button></div><div id="drawingDocs"></div><div id="drawingProgress" aria-live="polite"></div><p id="drawingNote"></p><div id="drawingCandidates"></div>';
    const modal=document.createElement('dialog');modal.id='drawingSource';document.body.append(modal);
    const field=v=>esc(String(v??''));
    const apiBefore=api;
    let sha='',view=null,timeout=0,epoch=0,choices=new Set(),edits={},person='',busy=false;
    let invalidating=Promise.resolve(),scopes={},split=new Set();
    let items=[],lastRevision=-1,dirty=false,reuseJob=null;
    const key=c=>JSON.stringify([c.zone||'',c.name,c.drawingScope||c.phase||'']);
    const kind=()=>currentType()?.name||'通用';
    const act=(action,data={})=>apiBefore('/api/extended/drawing-'+action,{...data,sha256:sha,revision:view?.draft?.revision});
    async function source(s){
        try{
            const r=await apiBefore('/api/extended/drawing-source',{source:s});
            modal.replaceChildren();
            const close=document.createElement('button');close.textContent='关闭';close.onclick=()=>modal.close();
            const title=document.createElement('h3');title.textContent=s.doc+' · 第'+s.page+'页';
            const img=new Image();img.alt='图纸原文截取';img.src=r.image;
            modal.append(close,title,img);if(!modal.open)modal.showModal();
        }catch(e){toast(e.message)}
    }
    function fromCandidate(c){
        const d=view.draft.documents.find(d=>d.sha256===c.docId);
        const boxes=c.evidence.map(e=>e.bbox).filter(Boolean);
        return {sha256:c.docId,doc:d.name,page:c.page,bbox:boxes.length?[Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1])),Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))]:null};
    }
    function setView(r,reset=false){
        if(r.suppressed){box.hidden=true;return}
        const last=view?.draft;
        view=r;const s=r.draft;
        if(reset||!last||(!dirty&&lastRevision!==s.revision)){
            const ck=new Set(r.conflicts.map(JSON.stringify));
            choices=new Set(s.parameters.length?s.parameters.map(p=>p.candidateId):s.candidates.filter(c=>!ck.has(key(c))).map(c=>c.id));
            edits=Object.fromEntries(s.parameters.filter(p=>p.origin==='人工修改').map(p=>[p.candidateId,p.value]));
            scopes=Object.fromEntries(s.parameters.filter(p=>p.drawingScope).map(p=>[p.candidateId,p.drawingScope]));
            split=new Set(r.conflicts.map(JSON.stringify).filter(k=>s.candidates.filter(c=>key(c)===k&&choices.has(c.id)).length>1));
            person=s.reviewer||person;
        }
        lastRevision=s.revision;render();
        clearTimeout(timeout);
        if(r.progress.status==='running'||r.engine.message==='正在自检读图引擎') timeout=setTimeout(()=>refresh(),850);
    }
    async function refresh(reset=false){
        const id=++epoch;try{const r=await act('status');if(id===epoch)setView(r,reset)}catch(e){if(id===epoch)$('#drawingNote').textContent=e.message}
    }
    async function action(name,data={},reset=false){
        await invalidating;
        const id=++epoch;
        clearTimeout(timeout);
        const result=await act(name,data);
        if(id===epoch)setView(result,reset);
        return result;
    }
    function sync(){
        const next=doc?.sha256||'';
        if(job?.drawingParams?.parameters?.length)reuseJob=job;
        box.hidden=!next||!!(doc?.bianshen?.matched&&doc.bianshen.origin!=='审查端图纸识别');
        if(next===sha&&!box.hidden&&view){render();return}
        ++epoch;clearTimeout(timeout);sha=next;view=null;lastRevision=-1;items=[];choices.clear();edits={};person='';dirty=false;box.open=false;
        if(!box.hidden)refresh(true);
    }
    function render(){
        if(!view)return;
        const s=view.draft,op=view.progress,ready=view.engine.ready;
        busy=op.status==='running';
        const active=s.parameters.length&&!dirty&&s.kind===kind();
        box.querySelector('summary').textContent=active?'已确认 '+s.parameters.length+' 项图纸参数，审查时作为依据':'图纸参数（可选）';
        $('#drawingRead').disabled=busy||!ready||!s.documents.length;
        $('#drawingFiles').disabled=busy||!ready;$('#drawingCancel').hidden=!busy;
        $('#drawingRead').textContent=['failed','cancelled'].includes(op.status)?'继续读图和提取':'读图并提取';
        $('#drawingNote').textContent=[ready?'':view.engine.message,/深基坑|SMW/i.test(kind())?'':'当前方案类别的字段表尚未实测验证',op.error||''].filter(Boolean).join(' · ');
        $('#drawingDocs').innerHTML=s.documents.map((d,i)=>'<div class="drbar"><b>'+field(d.name)+'</b><small>'+d.pages+' 页</small><select data-type="'+i+'" '+(busy?'disabled':'')+'>'+['设计总说明','岩土工程勘察报告'].map(t=>'<option '+(t===d.type?'selected':'')+'>'+t+'</option>').join('')+'</select><button data-remove="'+i+'" '+(busy?'disabled':'')+'>移除</button></div>').join('');
        const elapsed=op.elapsed||0;
        const label=op.phase==='读图'?'第 '+Math.min(op.total,op.page||1)+'/'+op.total+' 张 · 瓦片 '+(op.tile||0)+'/'+(op.tileCount||0):'提取 '+op.done+'/'+op.total+' 批 · 拒收 '+(op.rejected||0)+' 项';
        $('#drawingProgress').innerHTML=op.phase?'<div class="drbar"><progress max="'+Math.max(1,op.phase==='读图'?op.tileCount||1:op.total)+'" value="'+(op.phase==='读图'?op.tile||0:op.done)+'"></progress>'+field(label)+' · 已用 '+elapsed+' s</div>':'';
        const pane=$('#drawingCandidates');pane.replaceChildren();
        if(reuseJob?.drawingParams?.parameters?.length&&!active&&!busy){
            const use=document.createElement('button');use.textContent='沿用《'+reuseJob.document.name+'》的 '+reuseJob.drawingParams.parameters.length+' 项已确认参数';
            use.onclick=()=>run(async()=>{dirty=false;await action('reuse',{recordId:reuseJob.id},true);box.open=false});pane.append(use);
        }
        if(job?.drawingParams&&job.document.sha256===sha){
            const rec=document.createElement('details'),header=document.createElement('summary');
            const snap=job.drawingParams;header.textContent='记录中的图纸参数 · '+snap.parameters.length+' 项 · '+snap.reviewer+' · '+snap.confirmedAt;rec.append(header);
            for(const p of snap.parameters){const b=document.createElement('button');b.className='link';b.textContent=p.id+' '+p.label+' '+p.zone+(p.drawingScope?'（'+p.drawingScope+'）':'')+' = '+p.value+' '+p.unit+' · '+p.source.doc+' 第'+p.source.page+'页';b.onclick=()=>source(p.source);rec.append(b)}
            pane.append(rec);
        }
        if(!s.candidates.length||busy)return;
        const conflicts=new Set(view.conflicts.map(JSON.stringify));
        const grouped=new Map();
        for(const c of s.candidates){if(!grouped.has(key(c)))grouped.set(key(c),[]);grouped.get(key(c)).push(c)}
        const groups=[...grouped].sort(([a],[b])=>a.localeCompare(b,'zh-CN'));
        const checked=new Set(s.parameters.map(p=>p.candidateId));
        let html='<h4>候选 '+s.candidates.length+' 项 · 冲突 '+conflicts.size+' 项 · 拒收 '+s.aiLog.reduce((n,l)=>n+l.rejected,0)+' 项</h4><div class="drbar"><label>确认人 <input id="drawingReviewer" value="'+field(person)+'" autocomplete="off"></label><button id="drawingSafe">确认无冲突项</button><button id="drawingAll" class="primary">全部确认</button></div><div class="drrows"><table><thead><tr><th>选用</th><th>分区 / 字段</th><th>值（可修改）</th><th>单位</th><th>来源</th><th>状态</th></tr></thead><tbody>';
        items=[];
        for(const [k,rows] of groups){
            const conflict=conflicts.has(k),groupIndex=items.length,separate=split.has(k);
            for(const c of rows){
                const i=items.push(c)-1;
                html+='<tr><td><input aria-label="选择候选" data-pick="'+i+'" type="'+(conflict&&!separate?'radio':'checkbox')+'" name="drawGroup'+groupIndex+'" '+(choices.has(c.id)?'checked':'')+'></td><td>'+field([c.zone||'全场',c.drawingScope||c.phase,c.name].filter(Boolean).join(' / '))+(conflict?(separate?'<br><input aria-label="适用工况" data-scope="'+i+'" placeholder="填写适用工况" value="'+field(scopes[c.id]||'')+'">':i===groupIndex?'<br><button data-split="'+i+'">区分工况</button>':''):'')+'</td><td><input type="text" data-edit="'+i+'" value="'+field(edits[c.id]??c.value)+'"></td><td>'+field(c.unit)+'</td><td><button class="link" data-source="'+i+'">'+field(c.source)+'</button></td><td '+(conflict?'data-conflict':'')+'>'+(!dirty&&checked.has(c.id)?'已确认':conflict?'冲突':'待确认')+'</td></tr>';
            }
        }
        pane.insertAdjacentHTML('beforeend',html+'</tbody></table></div>');
        if(!s.extractionComplete){$('#drawingSafe').disabled=true;$('#drawingAll').disabled=true}
        $('#drawingReviewer').oninput=e=>{person=e.target.value};
        $('#drawingSafe').onclick=()=>confirmRows(false);
        $('#drawingAll').onclick=()=>confirmRows(true);
    }
    async function run(fn){try{await fn()}catch(e){toast(e.message);$('#drawingNote').textContent=e.message}}
    async function confirmRows(all){
        await run(async()=>{
            if(!person.trim())throw Error('请填写确认人');
            const conflicts=new Set(view.conflicts.map(JSON.stringify)),selected=[];
            for(const c of items){if(choices.has(c.id)&&(!conflicts.has(key(c))||all))selected.push(c.id)}
            if(all&&[...conflicts].some(k=>!items.some(c=>key(c)===k&&choices.has(c.id))))throw Error('请先为每个冲突字段选定一个值');
            const r=await action('confirm',{all,reviewer:person,selected,edits,scopes});
            dirty=false;setView(r,true);box.open=false;
        });
    }
    $('#drawingFiles').onchange=e=>run(async()=>{
        const files=Array.from(e.target.files);e.target.value='';
        for(const file of files)await action('upload',{...await fileData(file),type:'设计总说明'},true);
    });
    $('#drawingRead').onclick=()=>run(async()=>{dirty=false;await action('start',{kind:kind(),config:cfg()},true)});
    $('#drawingCancel').onclick=()=>run(()=>action('cancel'));
    box.addEventListener('click',e=>{
        const el=e.target;
        if(el.dataset.split!==undefined){split.add(key(items[+el.dataset.split]));render()}
        if(el.dataset.source!==undefined)source(fromCandidate(items[+el.dataset.source]));
        if(el.dataset.remove!==undefined)run(()=>action('remove',{docId:view.draft.documents[+el.dataset.remove].sha256},true));
    });
    function changed(){
        if(!dirty&&view.draft.parameters.length){const id=epoch;const captured=view;
            invalidating=act('invalidate').then(r=>{if(id===epoch&&view===captured){view.draft.revision=r.draft.revision;view.draft.parameters=[];lastRevision=r.draft.revision}}).catch(e=>toast(e.message))}
        dirty=true;box.querySelector('summary').textContent='图纸参数（可选） · 修改后待确认';
    }
    box.addEventListener('change',e=>{
        const el=e.target;
        if(el.dataset.type!==undefined)run(()=>action('type',{docId:view.draft.documents[+el.dataset.type].sha256,type:el.value},true));
        if(el.dataset.pick!==undefined){
            const c=items[+el.dataset.pick];if(el.type==='radio')for(const other of items)if(key(other)===key(c))choices.delete(other.id);
            if(el.checked)choices.add(c.id);else choices.delete(c.id);changed();
        }
    });
    box.addEventListener('input',e=>{if(e.target.dataset.scope!==undefined){scopes[items[+e.target.dataset.scope].id]=e.target.value;changed()}if(e.target.dataset.edit!==undefined){edits[items[+e.target.dataset.edit].id]=e.target.value;changed()}});
    const oldUpdate=updateDoc;
    updateDoc=function(){oldUpdate();sync()};
    $('#schemeType').addEventListener('change',()=>{if(view)render()});
    api=async function(path,data){
        if(path==='/api/start'&&view&&!box.hidden){
            if(busy||dirty)throw Error('请完成图纸提取和确认后开始审查');
            if(view.draft.parameters.length&&view.draft.kind!==kind())throw Error('方案类别已变更，请重新提取并确认');
            if(view.draft.parameters.length)data={...data,bianshenPackSha:view.packSha};
        }
        return apiBefore(path,data);
    };
    const oldDetail=drawDetail;
    drawDetail=function(){
        oldDetail();
        const issue=job?.issues.find(i=>i.id===selected);
        for(const b of issue?.parameterBasis||[]){
            if(b.origin!=='审查端图纸识别')continue;
            const panel=document.createElement('div');panel.className='quote';
            const title=document.createElement('b');title.textContent='图纸参数 '+b.ref+' '+b.label+(b.zone?'（'+b.zone+'）':'')+' = '+b.value+' '+(b.unit||'');
            const link=document.createElement('button');link.className='link';link.textContent=b.source+' · 审查端图纸识别';link.onclick=()=>source(b.drawingSource);
            panel.append(title,document.createElement('br'),link);$('#detail .resultsummary')?.after(panel);
        }
    };
    sync();
})();
