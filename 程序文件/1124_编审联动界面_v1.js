(() => {
    const picker = $('#planUpload');
    const banner = document.createElement('details');
    banner.className = 'panel';
    banner.style.cssText = 'padding:12px 18px;margin:8px 0';
    banner.hidden = true;
    $('#pendingDoc').parentElement.after(banner);

    const filter = document.createElement('select');
    filter.setAttribute('aria-label', '编制登记状态');
    for (const [label, value] of [['全部登记状态',''],['本次新问题','new'],['编制已登记待补','pending'],['相关待补（部分覆盖）','partial']]) {
        filter.add(new Option(label,value));
    }
    filter.hidden = true;
    $('#priorityFilter').after(filter);
    filter.onchange = () => drawIssues();

    const field = v => esc(String(v ?? ''));
    const coverage=i=>i?.bianshenPending?.coverage || (i?.bianshenPending ? 'partial' : '');
    function showPack() {
        const pack = doc ? doc.bianshen : job?.bianshen;
        banner.hidden = !pack?.matched || pack.origin==='审查端图纸识别';
        if (banner.hidden) { banner.replaceChildren(); return; }
        const parameters = pack.parameters.map(p => {
            const s = p.source || {};
            return '<li>['+field(p.id)+'] '+field(p.label)+' '+field(p.zone)+' = '+field(p.value)+' '+field(p.unit)+' · '+field(s.doc || p.origin)+' '+(s.page ? '第'+field(s.page)+'页' : '')+'</li>';
        }).join('');
        const pending = pack.pending.map(p => '<li>'+field(p.title)+' · '+(p.paragraph ? '段 '+field(p.paragraph) : '段号待核')+' '+field(p.deliverable || p.note)+'</li>').join('');
        banner.innerHTML='<summary><strong>来自编制助手：'+pack.parameters.length+' 项已确认参数，'+pack.pending.length+' 项已登记待补</strong></summary><div style="max-height:280px;overflow:auto"><h4>已确认参数</h4><ul>'+parameters+'</ul><h4>已登记待补</h4><ul>'+pending+'</ul></div>';
    }
    const oldUpdate=updateDoc;
    updateDoc=function(){oldUpdate();showPack()};
    const oldAdopt=adoptRecord;
    adoptRecord=function(r){
        filter.value='';
        if(r.doc && r.job?.bianshen?.matched) r={...r,doc:{...r.doc,bianshen:r.job.bianshen}};
        return oldAdopt(r);
    };
    const oldApi=api;
    api=async function(path,data){
        if(path==='/api/start' && doc?.bianshen?.matched && doc.bianshen.origin!=='审查端图纸识别') data={...data,bianshenPackSha:doc.bianshen.packSha256};
        return oldApi(path,data);
    };
    async function importSelection(file,sidecar){
        const r=await api('/api/import',file);
        if(sidecar){
            const result=await api('/api/extended/bianshen-match',{...sidecar,documentName:file.name,sha256:r.doc.sha256});
            if(result.bianshen) r.doc.bianshen=result.bianshen;
        }
        doc=r.doc;updateDoc();toast('方案已导入。');
    }
    const oldClick=$('#importPlan').onclick;
    $('#importPlan').onclick=async function(e){
        if(!window.pywebview?.api?.pick_submission)return oldClick.call(this,e);
        try {
            const file=await window.pywebview.api.pick_submission();
            if(file){const {sidecar,...data}=file;await importSelection(data,sidecar)}
        }catch(err){toast(err.message)}
    };
    // 浏览器文件选择器仅授权读取选中的文件，可同时选方案和同目录送审包。
    picker.multiple=true;
    picker.accept='.docx,.pdf,.txt,.json';
    const oldChange=picker.onchange;
    picker.onchange=async function(e){
        if(this.files.length===1 && !this.files[0].name.toLowerCase().endsWith('.json'))return oldChange.call(this,e);
        const files=Array.from(this.files);
        const docs=files.filter(f=>/\.(docx|txt|pdf)$/i.test(f.name));
        if(docs.length!==1)return toast('请选择一份方案，可同时选中配套送审包。');
        try {
            const stem=docs[0].name.replace(/\.[^.]+$/,'');
            const names=[stem,stem.replace(/_清洁版$/,'')].map(s=>(s+'.送审包.json').toLowerCase());
            const side=files.find(f=>names.includes(f.name.toLowerCase()));
            await importSelection(await fileData(docs[0]),side ? await fileData(side) : null);
        }catch(err){toast(err.message)}
    };
    const oldList=drawIssues;
    drawIssues=function(){
        filter.hidden=!job?.bianshen || job.bianshen.origin==='审查端图纸识别';
        if(filter.hidden)filter.value='';
        const original=job;
        try{
            if(filter.value && original)job={...original,issues:original.issues.filter(i=>filter.value==='new' ? coverage(i)!=='full' : coverage(i)===(filter.value==='pending'?'full':'partial'))};
            oldList();
        }finally{job=original}
        for(const card of document.querySelectorAll('#issues [data-issue]')){
            const i=job?.issues.find(x=>x.id===card.dataset.issue);
            if(['full','partial'].includes(coverage(i)))card.querySelector('.meta')?.append(Object.assign(document.createElement('small'),{textContent:coverage(i)==='full'?'编制已登记待补':'相关待补（部分覆盖）'}));
        }
    };
    const oldDetail=drawDetail;
    drawDetail=function(){
        oldDetail();
        const issue=job?.issues.find(i=>i.id===selected);
        if(!issue)return;
        const info=document.createElement('div');
        const basis=(issue.parameterBasis||[]).filter(b=>b.origin!=='审查端图纸识别').map(b=>'<div class="quote"><b>参数表 · '+field(b.ref)+' · 不一致</b><p>'+field(b.label)+' '+field(b.zone)+' = '+field(b.value)+' '+field(b.unit)+'</p><small>'+field(b.source)+'</small></div>').join('');
        const p=job.bianshen?.pending.find(p=>p.id===(issue.bianshenPending?.id || issue.bianshenPending));
        info.innerHTML=(p?'<p class="job-note">'+(coverage(issue)==='full'?'编制已登记待补':'相关待补')+' · '+field(p.title)+(coverage(issue)==='partial'?'（部分覆盖）':'')+'<br>'+field(issue.bianshenPending?.reason)+'</p>':'')+(issue.previousRejection?'<p class="job-note">编制端不采纳原因 · '+field(issue.previousRejection)+'</p>':'');
        if(info.childElementCount)$('#detail .resultsummary')?.after(info);
        if(basis){
            const sources=Array.from(document.querySelectorAll('#detail > div')).filter(el=>/^(规范依据|相关条文)/.test(el.firstChild?.textContent||''));
            const heading=Array.from(document.querySelectorAll('#detail h3')).find(el=>el.textContent==='原文依据');
            if(sources.length)sources.at(-1).insertAdjacentHTML('afterend',basis);
            else heading?.insertAdjacentHTML('beforebegin',basis);
        }
    };
    const oldJob=drawJob;
    drawJob=function(){
        oldJob();
        const s=job?.bianshenSummary;
        if(!s)return;
        const counts=s.newPriorities;
        $('#countAll').textContent=Object.values(counts).reduce((a,b)=>a+b,0);
        $('#countA').textContent=counts.A;$('#countB').textContent=counts.B;
        let html='<p class="job-note">编制阶段已登记待补 '+s.registered+' 项，本次仍未闭合。关联 '+s.linkedIssues+' 条审查意见。</p>';
        const c=job.bianshenComparison;
        if(c?.unavailable)html+='<p class="fieldnote">复审对比 · '+field(c.reason)+' <label>选择上次审查记录 <input id="bsPrevious" type="file" accept=".json"></label></p>';
        else if(c?.version===2){
            const groups=[['fixed','已整改'],['still','仍存在'],['rejectedAgain','不采纳后再次报出'],['unreported','本次未报出（未整改）'],['new','新出现']];
            html+='<details><summary>复审对比 · '+groups.map(([key,name])=>name+' '+c[key].length+' 条').join('，')+'</summary>';
            for(const [key,name] of groups){
                html+='<h4>'+name+'</h4><ul>'+c[key].map(i=>'<li>'+field(i.previousId?i.previousId+' → ':'')+field(i.id)+' '+field(i.title)
                    +(i.acceptedAgain?' · 采纳后仍报出，请复核':'')+(i.reason?' · '+field(i.reason):'')
                    +(i.before?'<details><summary>查看改文</summary><p>改前　'+field(i.before)+'</p><p>改后　'+field(i.after)+'</p></details>':'')+'</li>').join('')+'</ul>';
            }
            html+='</details>';
        }
        $('#jobNotes').insertAdjacentHTML('beforeend',html);
        const prior=$('#bsPrevious');
        if(prior)prior.onchange=async()=>{
            const id=job.id;
            try{const data=await fileData(prior.files[0]);const r=await api('/api/extended/bianshen-previous',{id,raw:data.raw});if(job?.id===id){job=r.job;drawJob()}}
            catch(err){toast(err.message)}
        };
    };
    showPack();
})();
