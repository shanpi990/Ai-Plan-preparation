(() => {
    const request = (action,data={})=>api('/api/library/'+action,data);
    const safe = (fn)=>async (...args)=>{try {await fn(...args);} catch(e){toast(e.message);}};
    const nav=document.createElement('button');
    nav.dataset.tab='standards';
    nav.innerHTML='<span>▤</span>规范库';
    document.querySelector('nav [data-tab="focus"]').after(nav);
    desktopTitles.standards=['规范库','校对条文后入库，按方案类别选用。'];
    const page=document.createElement('section');
    page.className='tab';page.id='tab-standards';
    $('#tab-focus').after(page);
    page.innerHTML='<div class="norm-layout"><section class="panel norm-reader"><div class="norm-head"><h2>规范原文</h2><label class="norm-upload">＋ 导入规范<input id="normFile" type="file" accept=".pdf,.docx,.txt"></label></div><p role="status" id="normMsg"></p><div id="normLibrary"></div></section><aside class="panel norm-builtins"><h2>条文查阅</h2><input id="normQuery" placeholder="搜索当前规范"><button id="normFind">检索</button><div id="normRows"></div></aside></div>';
    const panel=document.createElement('details');
    panel.className='panel';panel.style.padding='14px 18px';
    panel.innerHTML='<summary>本次审查选用规范 <small id="normCount"></small></summary><div id="normOptions"></div>';
    $('#tab-review').prepend(panel);
    let active='', books=[], listed=[],category='', chosen=new Map(), draft=null, pos=0, loading=0;
    const wholeBadge='<span class="norm-whole-badge">全文强制</span>';
    function individualBasis(b) {
        const code=b.code||b.ref.split('#')[0];
        const book=job?.standardSelection?.standards?.find(s=>s.code===code);
        const whole=b.whole_mandatory ?? book?.whole_mandatory ?? books.find(s=>s.code===code)?.whole_mandatory ?? /^GB\s*55\d{3}-/.test(code);
        return b.mandatory && !whole;
    }
    function picked(){return chosen.get(currentType()?.id)||new Set();}
    async function options(){
        if(!token)return;
        const id=currentType()?.id||'',seq=++loading;
        const r=await request('catalog',{category:id});
        if(seq!==loading)return;
        category=id;listed=r.standards;
        const ids=chosen.get(id)||new Set(listed.filter(b=>b.default_selected).map(b=>b.code));
        chosen.set(id,new Set(listed.filter(b=>ids.has(b.code)).map(b=>b.code)));
        $('#normOptions').innerHTML=listed.map(b=>'<label style="display:block;padding:6px"><input type="checkbox" value="'+esc(b.code)+'" '+(picked().has(b.code)?'checked':'')+'> '+esc(b.code)+' 《'+esc(b.title)+'》'+(b.whole_mandatory?wholeBadge:'')+' · '+(b.book_id?'有原文 '+b.clause_count+' 条':'仅目录')+'</label>').join('')||'当前类别暂无可选规范';
        $('#normCount').textContent='已选 '+picked().size+' 本';
    }
    $('#normOptions').onchange=e=>{if(e.target.checked)picked().add(e.target.value);else picked().delete(e.target.value);$('#normCount').textContent='已选 '+picked().size+' 本';};
    const baseDraw=drawTypes;
    drawTypes=function(){baseDraw();safe(options)();};
    const baseApi=api;
    api=async function(path,data){
        if(path==='/api/start'){await options();data={...data,standardCodes:[...picked()]};}
        return baseApi(path,data);
    };
    const adopt=adoptRecord;
    adoptRecord=function(r){const id=library.categories.find(c=>c.name===r.job?.schemeType)?.id;
        if(id && r.job.standardSelection)chosen.set(id,new Set((r.job.standardSelection.standards||[]).map(b=>b.code)));
        adopt(r);};
    function btn(parent,label,fn){
        const b=document.createElement('button');b.textContent=label;b.onclick=safe(fn);parent.append(b);return b;
    }
    function rows(data,book=books.find(b=>b.id===active)){
        const host=$('#normRows');host.replaceChildren();
        const groups=new Map();
        for(const x of data){
            const group=x.chapter_path||'正文';
            if(!groups.has(group)){const d=document.createElement('details'),s=document.createElement('summary');s.textContent=group;d.open=data.length<=12;d.append(s);host.append(d);groups.set(group,d);}
            const detail=document.createElement('details'),heading=document.createElement('summary'),body=document.createElement('p');
            heading.textContent=(x.mandatory&&!book?.whole_mandatory?'【强条】 ':'')+x.number+'　'+(x.body||x.text).slice(0,30);
            body.style.whiteSpace='pre-wrap';body.textContent=[x.location,x.body||x.text,x.explanation&&'条文说明\n'+x.explanation].filter(Boolean).join('\n');
            detail.append(heading,body);groups.get(group).append(detail);
            if(x.id)btn(detail,'编辑条文',()=>{modal('编辑条文','<textarea id="libBody">'+esc(x.body)+'</textarea><label '+(book?.whole_mandatory?'hidden':'')+'><input type="checkbox" id="libForce" '+(x.mandatory?'checked':'')+'>强条</label><label><input type="checkbox" id="libOn" '+(x.enabled?'checked':'')+'>启用</label><button id="libSave">保存</button>');$('#libSave').onclick=safe(async()=>{await request('update_clause',{id:x.id,body:$('#libBody').value,mandatory:$('#libForce').checked,enabled:$('#libOn').checked});$('#dialog').close();await refresh();});});
        }
        if(!data.length)host.textContent='暂无条文';
    }
    async function show(id){active=id;const r=await request('read',{id});if(active===id)rows(r.rows,r.book);}
    async function refresh(){
        books=(await request('list')).books;const host=$('#normLibrary');host.replaceChildren();
        for(const b of books){
            const card=document.createElement('div');card.style.cssText='padding:12px 0;border-top:1px solid var(--semi-color-border)';
            const h=document.createElement('strong');h.textContent=b.code+'　'+b.title;
            if(b.whole_mandatory)h.insertAdjacentHTML('beforeend',wholeBadge);
            const info=document.createElement('p');info.textContent=b.status+' · '+b.clause_count+' 条启用'+(b.whole_mandatory?'':' · '+b.mandatory_count+' 条强条');
            card.append(h,info);host.append(card);
            btn(card,'查看',()=>show(b.id));btn(card,b.status==='现行'?'停用':'启用',async()=>{await request('update_book',{id:b.id,status:b.status==='现行'?'停用':'现行'});await refresh();});
            btn(card,'编辑信息',()=>{
                modal('编辑规范信息','<label>名称<input id="bkName" value="'+esc(b.title)+'"></label><label>实施日期<input type="date" id="bkDate" value="'+esc(b.effective_date||'')+'"></label><fieldset><legend>适用类别（留空表示通用）</legend>'+library.categories.map(c=>'<label><input class="bkCat" type="checkbox" value="'+esc(c.id)+'" '+(b.categories.includes(c.id)?'checked':'')+'>'+esc(c.name)+'</label>').join(' ')+'</fieldset><button id="bkSave">保存</button>');
                $('#bkSave').onclick=safe(async()=>{await request('update_book',{id:b.id,title:$('#bkName').value,effective_date:$('#bkDate').value,categories:[...document.querySelectorAll('.bkCat:checked')].map(x=>x.value)});$('#dialog').close();await refresh();});
            });
            btn(card,'导出 JSON',async()=>{const r=await request('export',{id:b.id}),a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:'application/json'}));a.download=b.title+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);});
            btn(card,'删除',async()=>{if(!confirm('确认从原文库删除《'+b.title+'》及其条文？'))return;await request('delete_book',{id:b.id});await refresh();});
        }
        if(!books.length){host.textContent='尚未导入规范';rows([]);active='';}
        else await show(books.some(x=>x.id===active)?active:books[0].id);
        await options();
    }
    $('#normFind').onclick=safe(async()=>{if(!active)return;const id=active,q=$('#normQuery').value.trim();if(!q)return show(id);const r=await request('search',{id,text:q});if(active===id)rows(r.rows);});
    function editor(){
        const m=draft.meta_guess,cs=draft.clauses,x=cs[pos];
        modal('校对规范原文',(m.whole_mandatory?wholeBadge:'')+'<div class="actions"><label>编号<input id="edCode" value="'+esc(m.code)+'"></label><label>名称<input id="edTitle" value="'+esc(m.title)+'"></label><label>实施日期<input type="date" id="edDate" value="'+esc(m.effective_date)+'"></label></div><fieldset><legend>适用类别（留空表示通用）</legend>'+library.categories.map(c=>'<label><input class="edCat" type="checkbox" value="'+esc(c.id)+'" '+(m.categories.includes(c.id)?'checked':'')+'>'+esc(c.name)+'</label>').join(' ')+'</fieldset><details style="background:var(--semi-color-warning-light-default);padding:8px" '+(draft.warnings.length?'':'hidden')+'><summary>解析提醒 '+draft.warnings.length+' 项</summary>'+draft.warnings.map(w=>{
            const numbers=w.match(/(?:[A-Z]|\d+)(?:\.\d+){2,3}/g)||[];
            const i=numbers.reverse().map(n=>cs.findIndex(c=>c.number===n)).find(i=>i>=0);
            return i===undefined?esc(w):'<button type="button" data-warning-row="'+i+'">'+esc(w)+'</button>';
        }).join('<br>')+'</details><div style="display:grid;grid-template-columns:30% 1fr;gap:15px;margin:12px 0"><select aria-label="条文列表" id="edList" size="12">'+cs.map((c,i)=>'<option value="'+i+'" '+(i===pos?'selected':'')+'>'+esc(c.number)+' '+esc(c.body.slice(0,14))+'</option>').join('')+'</select><div><small>'+esc(x?.chapter_path||'')+'　'+esc(x?.location||'')+'</small><input id="edNum" aria-label="条号" value="'+esc(x?.number||'')+'"><label '+(m.whole_mandatory?'hidden':'')+'><input type="checkbox" id="edStrong" '+(x?.mandatory?'checked':'')+'>强制性条文</label><label>章节路径<input id="edPath" value="'+esc(x?.chapter_path||'')+'"></label><label>条文说明<textarea id="edExplanation">'+esc(x?.explanation||'')+'</textarea></label><textarea id="edText"  rows="7">'+esc(x?.body||'')+'</textarea><button id="edMerge">合并到上一条</button><button id="edDelete">删除此条</button><button id="edSplit">从光标处拆分</button></div></div><button id="edCommit" class="primary">确认入库</button>');
        function sync(){
            Object.assign(m,{code:$('#edCode').value,title:$('#edTitle').value,effective_date:$('#edDate').value,categories:[...document.querySelectorAll('.edCat:checked')].map(e=>e.value)});
            if(x){const v={chapter_path:$('#edPath').value,explanation:$('#edExplanation').value,body:$('#edText').value,number:$('#edNum').value,mandatory:$('#edStrong').checked};if(Object.keys(v).some(k=>v[k]!==x[k]))Object.assign(x,v,{edited:true});}
        }
        $('#edList').onchange=e=>{sync();pos=Number(e.target.value);editor();};
        for(const b of document.querySelectorAll('[data-warning-row]'))b.onclick=()=>{sync();pos=Number(b.dataset.warningRow);editor();};
        $('#edDelete').disabled=!x;
        $('#edDelete').onclick=()=>{sync();cs.splice(pos,1);pos=Math.max(0,Math.min(pos,cs.length-1));editor();};
        $('#edCommit').disabled=!cs.length;
        $('#edMerge').disabled=!pos;$('#edMerge').onclick=()=>{sync();const prev=cs[pos-1];prev.body+='\n'+x.body;prev.mandatory||=x.mandatory;prev.explanation=[prev.explanation,x.explanation].filter(Boolean).join('\n');prev.edited=true;cs.splice(pos--,1);editor();};
        $('#edSplit').onclick=()=>{sync();const cut=$('#edText').selectionStart;if(!x||cut<=0||cut>=x.body.length)return toast('请把光标放在两段文字之间');const tail=x.body.slice(cut);x.body=x.body.slice(0,cut);x.edited=true;cs.splice(++pos,0,{...x,number:'',body:tail,explanation:''});editor();};
        $('#edCommit').onclick=safe(async()=>{sync();const b=$('#edCommit');b.disabled=true;try{let r=await request('commit',draft);if(r.conflict){if(!confirm('该编号已有现行版本，确认替换并保留旧版？'))return;r=await request('commit',{...draft,replace:true});}active=r.id;$('#dialog').close();draft=null;await refresh();}finally{b.disabled=false;}});
    }
    $('#normFile').onchange=safe(async e=>{
        const input=e.target,file=input.files[0];if(!file)return;input.disabled=true;$('#normMsg').textContent='正在读取文件…';
        try{const r=await request('preview',await fileData(file));let seconds=0;
            for(;;){await new Promise(resolve=>setTimeout(resolve,600));const state=await request('progress',{task:r.task});
                if(state.error)throw Error(state.error);
                if(state.preview){draft=state.preview;pos=0;editor();break;}
                $('#normMsg').textContent='正在提取条文 · '+Math.floor(++seconds*.6)+' 秒';}
        }finally{input.disabled=false;input.value='';$('#normMsg').textContent='';}
    });
    nav.onclick=safe(async()=>{tab('standards');await refresh();});
    const render=drawDetail;
    drawDetail=function(){render();const issue=job?.issues.find(x=>x.id===selected);if(!issue?.basis?.length)return;
        for(const related of [false,true]){
            const entries=issue.basis.filter(b=>(!['违反','未落实'].includes(b.relation))===related);
            if(!entries.length)continue;
            const label=related?'相关条文（供核对）':'规范依据';
            const box=document.createElement('div');box.textContent=label+'　';$('#detail').append(box);
            if(related)box.style.color='var(--muted,GrayText)';
            for(const b of entries){
                const open=btn(box,b.ref+(individualBasis(b)?'（强条）':''),async()=>{
                    modal(label+' · '+b.ref,'<p>'+esc(b.reason||'')+'</p><small>'+esc(b.location||'')+'　'+esc(b.chapter_path||'')+'</small>'+(b.clause_quote?'<h3>条文摘句</h3><mark>'+esc(b.clause_quote)+'</mark>':'')+'<h3>审查时的条文原文</h3><p style="white-space:pre-wrap">'+esc(b.original||b.text||'')+'</p><h3>条文说明</h3><p style="white-space:pre-wrap">'+esc(b.explanation||'无')+'</p>');
                });
                if(related)open.style.color='inherit';
            }
        }
    };
    safe(options)();
})();

