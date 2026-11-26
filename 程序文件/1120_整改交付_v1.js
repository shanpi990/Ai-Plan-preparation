/* 整改工作区沿用当前记录、手动复核和批量勾选。 */
(() => {
    const scopeOptions = '<option value="all">全部问题</option><option value="confirmed">仅需修改</option><option value="ungenerated">仅未生成改文</option>';
    $('.more-menu').insertAdjacentHTML('beforeend','<button id="commentOnlyReview">导出审查意见批注版 Word</button>');
    $('#applyAmend').textContent = '导出采纳的修改';
    $('#applyAmend').closest('.actions').insertAdjacentHTML('beforebegin',
        '<div class="rect-export" aria-label="Word 导出设置"><label><input type="radio" name="rectMode" value="tracked" checked>修订版</label>'+
        '<label><input type="radio" name="rectMode" value="direct">直接替换版</label><label><input id="rectNotes" type="checkbox" checked>附加审查批注</label>'+
        '<label>批注范围 <select id="rectScope">'+scopeOptions+'</select></label><button id="commentOnlyAmend">仅导出批注版 Word</button></div>');
    $('#amendUnresolved').insertAdjacentHTML('afterend','<button id="rectRetry" hidden>重试失败的问题</button>');
    $('#amendStatus').insertAdjacentHTML('afterend','<div id="rectResult" role="status"></div>');
    let request = 0;
    function guarded(fn) {
        return async function(event) {
            const button=event.currentTarget;
            button.disabled=true;
            try { await fn(); } catch(error) { toast(error.message); }
            finally { button.disabled=false; }
        };
    }
    function status(result) {
        const box=$('#rectResult');
        box.replaceChildren();
        if(!result?.verification)return;
        const v=result.verification;
        const line=document.createElement('p');
        line.className=v.passed?'rect-pass':'rect-error';
        line.textContent=v.passed?'校验通过 · '+result.count+' 处修改 · '+result.comments+' 条批注':'校验未通过 · '+v.errors.join('；');
        const file=document.createElement('small');
        file.textContent=displayFilePath(result.path);
        box.append(line,file);
    }
    function reviewed(data) {
        reviews=data.reviews;
        reviewCache[job.id]=structuredClone(reviews);
        dirtyReviews[job.id]=false;
        drawJob();
    }
    async function commentOnly(reviewPage) {
        if(!job)throw Error('请先完成审查或导入审查记录。');
        const id=job.id;
        await cacheCurrentReviews();
        const r=await extended('comment-word',{id,scope:reviewPage?'all':$('#rectScope').value});
        if(job?.id===id)status(r);
        modal('审查意见批注版 Word','<p>'+esc(r.verification.passed?'已核对 '+r.comments+' 条批注的位置。':r.verification.errors.join('；'))+'</p><p class="rect-path">'+esc(displayFilePath(r.path))+'</p>');
    }
    $('#commentOnlyReview').onclick=guarded(()=>commentOnly(true));
    $('#commentOnlyAmend').onclick=guarded(()=>commentOnly(false));
    $('#applyAmend').onclick=guarded(async()=>{
        const id=job.id, edits=readEdits();
        const pending=edits.filter(e=>e.selected).reduce((n,e)=>n+(e.after.match(/【待补[：:][^】\n]+】/g)||[]).length,0);
        if(pending&&!window.confirm('还有 '+pending+' 处待补信息，确认按占位导出？'))return;
        await cacheCurrentReviews();
        const r=await extended('apply',{id,edits,mode:document.querySelector('[name="rectMode"]:checked').value,
            comments:$('#rectNotes').checked,scope:$('#rectScope').value,confirmPlaceholders:pending});
        if(job?.id!==id)return toast('已导出至 '+displayFilePath(r.path));
        desktopAmendDirty=false;
        reviewed(r);
        await loadAmendments();
        toast(r.verification.passed?'已导出并核对 Word':'Word 校验未通过，请查看具体段落。');
    });
    $('#rectRetry').onclick=guarded(async()=>{
        if(!window.confirm('仅重新生成失败或遗漏的问题，确认调用模型？'))return;
        const id=job.id;
        await cacheCurrentReviews();
        if(desktopAmendDirty){
            await extended('save-draft',{id,edits:readEdits()});
            desktopAmendDirty=false;
        }
        const r=await extended('retry-amend',{id,config:cfg(),consent:true});
        await waitOperation(r.id,'正在重试');
        if(job?.id===id)await loadAmendments();
    });
    function diffHtml(parts) {
        const after=parts.filter(([type])=>type!=='del').map(([,v])=>v).join('');
        const spans=[...after.matchAll(/【待补[：:][^】\n]+】/g)].map(m=>[m.index,m.index+m[0].length]);
        let pos=0;
        return parts.map(([type,value])=>{
            let s='',cursor=0;
            if(type!=='del'){
                for(const [a,b] of spans){
                    const lo=Math.max(0,a-pos),hi=Math.min(value.length,b-pos);
                    if(lo<hi){s+=esc(value.slice(cursor,lo))+'<mark>'+esc(value.slice(lo,hi))+'</mark>';cursor=hi;}
                }
                pos+=value.length;
            }
            s+=esc(value.slice(cursor));
            return type==='equal'?s:type==='ins'?'<ins>'+s+'</ins>':'<del>'+s+'</del>';
        }).join('');
    }
    async function findTypo(id) {
        const focusJob=job.id;
        const data={id:focusJob,editId:id,edits:readEdits()};
        const r=await extended('typo-find',data);
        if(job?.id!==focusJob)return;
        if(!r.matches.length)return toast('全文未找到其他可替换的相同写法。');
        modal('全文另有 '+r.matches.length+' 处相同写法',r.matches.map(m=>'<label class="rect-hit"><input type="checkbox" data-hit="'+esc(m.key)+'"> 第 '+m.paragraph+' 段 · '+esc(m.old)+' → '+esc(m.new)+'<small>'+esc(m.context)+'</small></label>').join('')+'<button id="rectAddHits" class="primary">加入对照表</button>');
        $('#rectAddHits').onclick=guarded(async()=>{
            const keys=[...document.querySelectorAll('[data-hit]:checked')].map(n=>n.dataset.hit);
            if(!keys.length)throw Error('请勾选需要一并修改的位置。');
            if(job?.id!==focusJob)throw Error('审查记录已切换。');
            amendDraft=await extended('typo-add',{...data,keys});
            desktopAmendDirty=false;
            $('#dialog').close();
            drawAmendments();
        });
    }
    const base=drawAmendments;
    drawAmendments=function(){
        base();
        const epoch=++request;
        $('#rectRetry').hidden=!amendDraft.unresolved.some(x=>x.retryable);
        status(amendDraft.lastExport);
        if(amendDraft.undoExport){
            const b=document.createElement('button');
            b.textContent='撤销上次状态回写';
            $('#rectResult').append(b);
            b.onclick=guarded(async()=>{
                const id=job.id;
                await cacheCurrentReviews();
                const r=await extended('undo-amend',{id,exportId:amendDraft.undoExport});
                if(job?.id===id){reviewed(r);await loadAmendments();}
            });
        }
        const initial=[];
        document.querySelectorAll('#amendRows [data-edit]').forEach((row,index)=>{
            const e=amendDraft.edits[index];
            const editor=row.querySelector('.afterEdit');
            const view=document.createElement('div');
            view.className='rect-diff';
            view.setAttribute('aria-label','字符改动');
            editor.before(view);
            if(e.op==='insert_after'){
                const label=document.createElement('b');
                label.className='rect-insert';
                label.textContent='在第 '+e.paragraph+' 段后新增';
                row.cells[2].prepend(label);
                row.cells[2].classList.add('rect-anchor');
                editor.setAttribute('aria-label','新增正文，一行一段');
            }
            let serial=0,timer;
            const type=e.op||'replace';
            initial.push({before:e.before,after:editor.value,op:type,view,editor});
            editor.oninput=()=>{
                const value=editor.value,seq=++serial;
                clearTimeout(timer);
                timer=setTimeout(async()=>{
                    try {
                        const r=await extended('amend-diff',{before:e.before,after:value,op:type});
                        if(epoch===request&&seq===serial)view.innerHTML=diffHtml(r.diff);
                    } catch(error) { if(epoch===request)view.textContent=error.message; }
                },180);
            };
            if(type==='replace'&&!e.localTypo&&e.issueIds.some(k=>job.issues.find(i=>i.id===k)?.category==='错别字与表述问题')){
                const b=document.createElement('button');
                b.dataset.sameWord=e.editId;
                b.textContent='查找全文相同写法';
                b.onclick=guarded(()=>findTypo(e.editId));
                row.cells[1].append(b);
            }
        });
        if(document.querySelector('[data-same-word]')){
            extended('typo-counts',{id:job.id}).then(r=>{
                if(epoch!==request)return;
                document.querySelectorAll('[data-same-word]').forEach(b=>{
                    const n=r.counts[b.dataset.sameWord];
                    if(n>0)b.textContent='全文另有 '+n+' 处相同写法';
                });
            }).catch(()=>{ /* 点击行内按钮仍可重新检索。 */ });
        }
        if(initial.length)extended('amend-diffs',{edits:initial.map(({before,after,op})=>({before,after,op}))})
            .then(r=>{if(epoch===request)r.diffs.forEach((v,i)=>{if(initial[i].editor.value===initial[i].after)initial[i].view.innerHTML=diffHtml(v);});})
            .catch(e=>toast(e.message));
    };
    // 慢请求完成后只更新其所属的记录。
    loadAmendments=async function(){
        if(!job)return;
        const id=job.id;
        try{
            const d=await extended('amendments',{id});
            if(job?.id!==id)return;
            amendDraft=d;amendJobId=id;drawAmendments();
        }catch(e){toast(e.message);}
    };
    if(job&&amendJobId===job.id)drawAmendments();
})();

