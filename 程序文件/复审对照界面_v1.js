(() => {
    const style = document.createElement('link');
    style.rel = 'stylesheet';
    style.href = '/round-compare.css';
    document.head.append(style);
    const menu = $('.more-menu');
    const entry = document.createElement('button');
    entry.id = 'roundEntry';
    entry.textContent = '复审对照';
    entry.disabled = true;
    menu.append(entry);
    const summary = document.createElement('section');
    summary.id = 'roundSummary';
    summary.className = 'round-panel';
    summary.hidden = true;
    $('#jobNotes').parentElement.after(summary);
    const HIST = '上轮问题';
    let filter = '', owner = '';
    const state = () => job?.roundComparison;
    const weak = text => ['可能由修改引入','原文已有，上轮未报','原文位置待核','本轮新增'].includes(text);
    const tone = text => weak(text) ? 'weak' : ['改得不彻底','仍未修改'].includes(text) ? 'warn' : 'neutral';
    const html = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    const tag = text => '<span class="round-tag '+tone(text)+'">'+html(text)+'</span>';
    const findOld = id => state().previous.find(i => i.id===id);
    const currentFor = id => job.issues.find(i => i.id===state().pairs[id]);
    const oldFor = id => Object.keys(state().pairs).find(oid => state().pairs[oid]===id);
    const apiRound = (action, data={}) => api('/api/extended/round-'+action,{id:job.id,revision:state()?.revision||0,...data});
    function open(title, body) {
        if ($('#dialog').open) $('#dialog').close();
        modal(title,body);
    }
    function pinFilter(label) {
        filter = filter===label ? '' : label;
        drawJob();
        if (filter && state().previous.some(i=>!state().pairs[i.id] && state().oldMarks[i.id]===filter)) {
            const old = $('#roundHistoryList');
            if (old) old.open=true;
        }
    }
    function countButtons(counts) {
        return Object.entries(counts).map(([label,num])=>'<button type="button" data-round-filter="'+html(label)+'" aria-pressed="'+(filter===label)+'">'+html(label)+' <b>'+Number(num)+'</b></button>').join('');
    }
    function showSummary() {
        const s=state();
        entry.disabled = job?.status!=='done';
        entry.hidden = !$('#tab-review').classList.contains('active');
        summary.hidden=!s;
        if (!s) return;
        const missing=s.previous.filter(i=>!s.pairs[i.id] && (!filter || filter===s.oldMarks[i.id]));
        summary.innerHTML='<div class="round-head"><h3>复审对照</h3><small>上轮 '+s.previous.length+' 条 · '+html(s.filename)+'</small><button id="roundManage">管理关联</button></div>'+
            (!s.hasReviews?'<p>上一轮尚未复核，对照结果只能区分再报与未报</p>':'')+
            '<div class="round-filters">'+countButtons(s.counts)+countButtons({'本轮新增':s.newCount})+
            countButtons(Object.fromEntries(Object.entries(s.newKinds).filter(([k])=>k!=='本轮新增')))+(filter?'<button id="roundReset">清除筛选</button>':'')+'</div>'+
            '<details id="roundHistoryList"'+(filter && missing.length?' open':'')+'><summary>'+HIST+' · 本轮未匹配 '+missing.length+' 条</summary>'+
            missing.map(i=>'<button class="round-row" data-round-old="'+html(i.id)+'">'+tag(s.oldMarks[i.id])+'<strong>'+html(i.id)+' · '+html(i.title)+'</strong><span>查看原文 ›</span></button>').join('')+
            (!missing.length?'<p class="fieldnote">当前筛选下没有未匹配的上轮问题。</p>':'')+'</details>';
        summary.querySelectorAll('[data-round-filter]').forEach(b=>b.onclick=()=>pinFilter(b.dataset.roundFilter));
        summary.querySelectorAll('[data-round-old]').forEach(b=>b.onclick=()=>oldDetail(b.dataset.roundOld));
        if ($('#roundReset')) $('#roundReset').onclick=()=>pinFilter(filter);
        $('#roundManage').onclick=()=>manage();
    }
    function oldText(i) {
        return '<div class="round-side"><h4>上轮 · '+html(i.id)+' · '+html(i.priority)+'级</h4><strong>'+html(i.title)+'</strong><p>'+html(i.description)+'</p><small>人工复核 · '+html(i.review.status||'待复核')+'</small>'+
            (i.review.note?'<p>'+html(i.review.note)+'</p>':'')+'</div>';
    }
    function newText(i) {
        return '<div class="round-side"><h4>本轮 · '+html(i.id)+' · '+html(i.priority)+'级</h4><strong>'+html(i.title)+'</strong><p>'+html(i.description)+'</p>'+
            (i.citations||[]).filter(c=>c.source==='plan').slice(0,3).map(c=>'<blockquote>P'+html(c.paragraph)+'　'+html(c.quote)+'</blockquote>').join('')+'</div>';
    }
    function passages(i) {
        return i.citations.map(r=>'<div class="round-cols round-passages"><div><small>上轮 P'+html(r.old)+'</small><p>'+html(r.before)+'</p></div><div><small>'+
            (r.new?'本轮 P'+html(r.new):'本轮已删除')+' · '+html(r.kind)+'</small><p>'+html(r.after||'—')+'</p></div></div>').join('') || '<p>该问题没有方案正文引文。</p>';
    }
    function oldDetail(oid) {
        const i=findOld(oid), curr=currentFor(oid);
        open(HIST+' · '+i.id,tag(state().oldMarks[oid])+'<div class="round-cols">'+oldText(i)+(curr?newText(curr):'<div class="round-side"><h4>本轮</h4><p>未匹配到本轮意见</p></div>')+'</div><h4>引文段落对照</h4>'+passages(i)+'<button id="roundLinkOld">调整关联</button>');
        $('#roundLinkOld').onclick=()=>manage(oid);
    }
    function applyResponse(r) {
        job.roundComparison=r.state;
        reviews=r.reviews;
        reviewCache[job.id]=reviews;
        filter=''; drawJob();
        if ($('#dialog').open) $('#dialog').close();
        toast('复审对照已保存'+(r.saved?' · '+r.saved:''));
    }
    function guarded(button, action) {
        button.onclick=async()=>{
            const id=job?.id;
            button.disabled=true;
            try {await action(id)} catch(e) {toast(e.message)}
            finally {if(button.isConnected) button.disabled=false}
        };
    }
    function manage(oid, nid) {
        const s=state();
        if(!s.previous.length) return toast('上轮没有问题可以关联。');
        const def=oid || (nid && oldFor(nid)) || s.previous[0].id;
        const options=(items,id)=>items.map(i=>'<option value="'+html(i.id)+'"'+(i.id===id?' selected':'')+'>'+html(i.id+' · '+i.title)+'</option>').join('');
        open('管理复审关联','<div class="round-picker"><label>上轮问题<select id="roundOld">'+options(s.previous,def)+'</select></label>'+
            '<label>本轮问题<select id="roundNew"><option value="">未关联</option>'+options(job.issues,nid||s.pairs[def])+'</select></label>'+
            '<p id="roundLinksNow"></p><div id="roundLinkPreview" class="round-cols"></div><div class="round-actions"><button id="roundUnlink">取消关联</button><button class="primary" id="roundSaveLink">保存关联</button></div></div>');
        const left=$('#roundOld'),right=$('#roundNew');
        const preview=()=>{
            const linked=s.pairs[left.value],other=oldFor(right.value);
            $('#roundLinksNow').textContent='现有关联：'+left.value+' → '+(linked||'无')+(other&&other!==left.value?'。保存后将解除 '+other+' → '+right.value:'');
            $('#roundLinkPreview').innerHTML=oldText(findOld(left.value))+(right.value?newText(job.issues.find(i=>i.id===right.value)):'');
            $('#roundUnlink').disabled=!linked;
            $('#roundSaveLink').disabled=!right.value || right.value===linked;
        };
        left.onchange=()=>{right.value=s.pairs[left.value]||'';preview()};
        right.onchange=preview;
        for(const [id,unlink] of [['roundUnlink',true],['roundSaveLink',false]]) guarded($('#'+id),async jid=>{
            const r=await apiRound('adjust',{previous:left.value,current:unlink?null:right.value,reviews});
            if(job?.id===jid)applyResponse(r);
        });
        preview();
    }
    entry.onclick=async()=>{
        menu.closest('details').open=false;
        const jid=job.id;
        try {
            const {records}=await apiRound('list');
            if(job?.id!==jid)return;
            open('选择上一轮审查记录','<div class="round-picker"><label>同方案记录<select id="roundRecord">'+
                (records.length?records.map(r=>'<option value="'+html(r.name)+'">'+html(r.date.replace('T',' ')+' · 已处理 '+r.processed+' / 共 '+r.total+' 条 · '+r.name)+'</option>').join(''):'<option value="">未找到同方案记录</option>')+
                '</select></label><label>或选择本地 JSON<input id="roundFile" type="file" accept=".json"></label><p id="roundWarning" class="fieldnote"></p><div class="round-actions"><button id="roundRun" class="primary">开始对照</button></div></div>');
            const btn=$('#roundRun'), file=$('#roundFile'), select=$('#roundRecord');
            let warning='';
            const change=()=>{warning='';$('#roundWarning').textContent='';btn.textContent='开始对照';btn.disabled=!file.files.length&&!select.value};
            select.onchange=()=>{file.value='';change()};file.onchange=change;
            guarded(btn,async id=>{
                const chosen=file.files.length?await fileData(file.files[0]):{name:select.value};
                if(job?.id!==id)return;
                const r=await apiRound('compare',{...chosen,reviews,allowUnreviewed:!!warning,expectedSha:warning});
                if(job?.id!==id)return;
                if(r.warning){warning=r.sha256;$('#roundWarning').textContent=r.warning;btn.textContent='继续对照';return}
                applyResponse(r);
            });
            change();
        }catch(e){toast(e.message)}
    };
    const drawList=drawIssues;
    drawIssues=function(){
        const original=job,s=state();
        if(owner!==job?.id){owner=job?.id;filter=''}
        try{
            if(s&&filter){
                const matched=new Set(Object.values(s.pairs));
                job={...job,issues:job.issues.filter(i=>filter==='本轮新增'?!matched.has(i.id):s.newMarks[i.id]===filter)};
            }
            drawList();
        }finally{job=original}
        if(s)document.querySelectorAll('#issues [data-issue]').forEach(b=>b.insertAdjacentHTML('beforeend',' '+tag(s.newMarks[b.dataset.issue])));
    };
    const drawOne=drawDetail;
    drawDetail=function(){
        drawOne();
        const s=state(),i=job?.issues.find(v=>v.id===selected);
        if(!i||!s)return;
        const oid=oldFor(i.id),mark=s.newMarks[i.id];
        const block=document.createElement('section');
        block.className='round-detail';
        block.innerHTML='<div class="round-head">'+tag(mark)+'<button id="roundEditLink">调整关联</button></div>'+
            (oid?'<div class="round-cols">'+oldText(findOld(oid))+newText(i)+'</div><button id="roundSeeOriginal">查看两轮原文</button>':'');
        $('#detail .resultsummary')?.after(block);
        block.querySelector('#roundEditLink').onclick=()=>manage(oid,i.id);
        if(oid)block.querySelector('#roundSeeOriginal').onclick=()=>oldDetail(oid);
    };
    function dashboard(){
        document.querySelector('#roundImpact')?.remove();
        const target=$('#tab-impact');
        if(!state()||!target?.classList.contains('active'))return;
        const s=state();
        const area=document.createElement('section');
        area.id='roundImpact';area.className='round-panel';
        area.innerHTML='<h3>复审对照</h3><div class="round-metrics">'+Object.entries({...s.counts,'本轮新增':s.newCount}).map(([k,v])=>'<span>'+html(k)+' <b>'+Number(v)+'</b></span>').join('')+'</div>';
        (target.querySelector('.im-assume')||null)?target.querySelector('.im-assume').before(area):target.append(area);
    }
    const draw=drawJob;
    drawJob=function(){draw();showSummary();dashboard()};
    const priorTab=tab;
    tab=function(name){priorTab(name);entry.hidden=name!=='review';if(name==='impact')dashboard()};
    new MutationObserver(()=>{if(state() && $('#tab-impact.active') && !$('#roundImpact'))dashboard()}).observe($('#tab-impact'),{childList:true});
    showSummary();
})();
