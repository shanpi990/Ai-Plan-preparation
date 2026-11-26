(function(){
'use strict';
const ext=(name,data={})=>api('/api/focus-ext/'+name,data);
const guard=fn=>async(event)=>{try{await fn(event)}catch(e){toast(e.message)}};
const page=$('#tab-focus');
page.insertAdjacentHTML('beforeend',`<div class="focusExtras">
<section class="panel"><div class="panelhead"><h2>业主文件要求</h2><button class="primary" id="ownerImport">导入业主文件</button><input type="file" id="ownerFile" accept=".pdf,.docx,.txt" hidden></div>
<small id="ownerStatus">文字版 PDF、DOCX、TXT</small><div id="ownerBooks"></div></section>
<section class="panel"><div class="panelhead"><h2>收藏的问题</h2><select id="favFilter" aria-label="筛选收藏问题的方案类别"></select></div><div id="favRows"></div></section>
<p id="focusQuota" role="status"></p></div>`);
page.insertAdjacentHTML('beforeend',`<style>
.focusExtras{display:grid;gap:16px;margin:16px 0}.focusExtras .panel{padding:20px}.focusExtras h2{font-size:18px}
.focusExtras .panelhead,.fxEntry,.fxRowActions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.fxEntry{padding:12px 0;border-bottom:1px solid var(--border,#aab4c044)}.fxEntry>div:first-child{flex:1;min-width:180px}.fxEntry small,.fxProof{display:block;margin-top:4px}
.fxDraft{display:grid;gap:10px}.fxDraft article{border:1px solid var(--border,#aab4c077);border-radius:8px;padding:12px}.fxDraft textarea{width:100%;margin:6px 0;min-height:48px}.fxProof{white-space:pre-wrap}.fxTag{padding:2px 7px;border-radius:5px;background:#2375b51a;color:inherit}.fxScope{display:flex;gap:8px;flex-wrap:wrap}.fxScope label{display:inline-flex;align-items:center;gap:3px}.fxScope input,.fxDraft input[type=checkbox]{width:auto}.fxStar{color:#bb7900}.fxWarning{color:var(--orange,#aa6100)}
</style>`);
const resultPanel=document.createElement('section');resultPanel.className='panel';resultPanel.style.padding='20px';
const results=$('#focusResults'),heading=results.previousElementSibling;
if(heading?.matches('h3'))resultPanel.append(heading);
resultPanel.append(results);page.append(resultPanel);
let db={owners:[],favorites:[]},tick=0,quotaTimer,latest=0;
const types=()=>library.categories.map(c=>c.name);
function draw(){
 const filter=$('#favFilter'),value=filter.value;
 const kinds=[...new Set([...types(),...db.favorites.map(r=>r.schemeType)])];
 filter.replaceChildren(new Option('全部类别',''),...kinds.map(k=>new Option(k,k)));
 filter.value=kinds.includes(value)?value:'';
 $('#ownerBooks').innerHTML=db.owners.map(b=>`<div class="fxEntry"><div><strong>${esc(b.title)}</strong><small>${esc(b.docNo)} · ${b.items.length} 条要求 · ${b.items.filter(r=>r.enabled).length} 条加入审查</small></div><button data-book="${esc(b.sha256)}">校对要求</button></div>`).join('')||'<p class="fieldnote">尚未导入业主文件。</p>';
 $('#favRows').innerHTML=db.favorites.filter(r=>!filter.value||r.schemeType===filter.value).slice().reverse().map(r=>`<div class="fxEntry"><div><strong>${esc(r.title)}</strong><small>${esc(r.id)} · ${esc(r.schemeType)} · ${esc(r.priority)} · ${esc(r.sourceIssue)}</small><small>${esc(r.sourceName)}${r.note?' · '+esc(r.note):''}</small></div><div class="fxRowActions"><button data-fav="${esc(r.id)}" data-act="toggle">${r.enabled?'停用':'启用'}</button><button data-fav="${esc(r.id)}" data-act="note">备注</button><button data-fav="${esc(r.id)}" data-act="remove">删除</button></div></div>`).join('')||'<p class="fieldnote">当前类别暂无收藏。可在诊断问题的人工复核处收藏。</p>';
 scheduleQuota();
}
async function refresh(){const n=++latest;const data=await ext('state');if(n===latest){db=data;draw()}}
function scheduleQuota(){
 clearTimeout(quotaTimer);
 const v=++tick;
 if(!token)return;
 quotaTimer=setTimeout(guard(async()=>{
 const p=await ext('preview',{schemeType:currentType()?.name||'通用',focus});
 if(v!==tick)return;
 const msg=`${currentType()?.name||'通用'} · 本次送审 ${p.focus.length} 项 · ${p.focusChars} / 2000 字`+(p.focusOmitted?` · 已超出上限，后 ${p.focusOmitted} 项未送审`:'');
 $('#focusQuota').textContent=msg;$('#focusQuota').classList.toggle('fxWarning',!!p.focusOmitted);
 let tip=$('#focusQuotaReview');
 if(!tip){$('#focusBrief').insertAdjacentHTML('afterend','<small id="focusQuotaReview" class="fieldnote"></small>');tip=$('#focusQuotaReview')}
 tip.textContent=msg;
 }),180);
}
const previousSummary=updateFocusSummary;
updateFocusSummary=function(){previousSummary();scheduleQuota()};
const oldTab=tab;
tab=function(name){oldTab(name);if(name==='focus'&&token)guard(refresh)()};
$('#favFilter').onchange=draw;
$('#ownerImport').onclick=()=>$('#ownerFile').click();
$('#ownerFile').onchange=guard(async e=>{
 const file=e.target.files[0];e.target.value='';
 if(!file)return;
 if(file.size>60000000)throw Error('文件超过 60 MB。');
 if(!confirm('本地读取文件后，将正文发送至已配置的国内模型提取要求。继续导入？'))return;
 const b=$('#ownerImport'),s=$('#ownerStatus');b.disabled=true;s.textContent='正在读取正文并提取要求…';
 try{
 const raw=await new Promise((ok,fail)=>{const r=new FileReader();r.onerror=()=>fail(Error('文件读取失败'));r.onload=()=>ok(r.result.split(',')[1]);r.readAsDataURL(file)});
 const request={raw,name:file.name};let result=await ext('import',request),overwrite=false;
 if(result.duplicate){if(!confirm('同一文件已入库，重新提取并覆盖？取消将跳过。'))return;overwrite=true;result=await ext('import',{...request,overwrite})}
 proof(result,overwrite);
 }finally{b.disabled=false;s.textContent='文字版 PDF、DOCX、TXT'}
});
$('#ownerBooks').onclick=guard(async e=>{const b=e.target.closest('[data-book]');if(b)proof(await ext('edit-book',{sha256:b.dataset.book}),true)});
function proof({key,draft:d},overwrite){
 const list=d.items.map(r=>({...r,scope:[...r.scope]}));
 modal('业主文件要求校对',`<p><b>${esc(d.title)}</b></p><label>文号 <input id="fxNo" value="${esc(d.docNo)}" placeholder="请填写文件文号"></label><p class="fieldnote">${list.length} 条摘录已对应原文 · 丢弃 ${Number(d.dropped)} 条 · 用量 ${Number(d.usage?.total_tokens||0)} tokens</p><div id="fxDraft" class="fxDraft"></div><div class="actions"><button class="primary" id="fxSave">确认保存</button></div>`);
 function rows(){
 $('#fxDraft').innerHTML=list.map((r,i)=>`<article data-index="${i}"><div class="panelhead"><label><input data-check type="checkbox" ${r.enabled?'checked':''}> 加入审查</label><small>${esc(r.id||'要求 '+r.seq)}${r.management?' · 管理事项':''}</small><button data-del>移除条目</button></div><textarea data-req aria-label="要求文本">${esc(r.requirement)}</textarea><div class="fxScope">${[...new Set([...types(),'盾构','联络通道',...r.scope])].map(k=>`<label><input data-scope="${esc(k)}" type="checkbox" ${r.scope.includes(k)?'checked':''}>${esc(k)}</label>`).join('')}</div><small>原文 · 第 ${Number(r.page)} ${esc(d.pageUnit)}</small><blockquote class="fxProof">${esc(r.quote)}</blockquote></article>`).join('');
 }
 const toolbar=$('#fxSave').parentElement;
 toolbar.style.cssText='position:sticky;top:0;z-index:1;justify-content:flex-end;background:var(--surface,Canvas);padding:6px 0';
 $('#fxDraft').before(toolbar);
 rows();
 const box=$('#fxDraft');
 box.oninput=e=>{const r=list[+e.target.closest('article').dataset.index];if(e.target.matches('[data-req]'))r.requirement=e.target.value;
 if(e.target.matches('[data-check]')){r.enabled=e.target.checked;r.selectedOrder=Date.now()}
 if(e.target.matches('[data-scope]'))r.scope=[...e.target.closest('article').querySelectorAll('[data-scope]:checked')].map(x=>x.dataset.scope)};
 box.onclick=e=>{if(e.target.matches('[data-del]')){list.splice(+e.target.closest('article').dataset.index,1);rows()}};
 $('#fxSave').onclick=guard(async e=>{const b=e.target;b.disabled=true;try{await ext('save-book',{key,items:list,docNo:$('#fxNo').value,overwrite});$('#dialog').close();await refresh();toast('业主要求已保存')}finally{b.disabled=false}});
}
$('#favRows').onclick=guard(async e=>{
 const b=e.target.closest('[data-fav]');if(!b)return;
 const r=db.favorites.find(x=>x.id===b.dataset.fav);
 const data={favoriteId:r.id};
 if(b.dataset.act==='note'){data.note=prompt('收藏备注',r.note);if(data.note===null)return}
 if(b.dataset.act==='toggle')data.enabled=!r.enabled;
 if(b.dataset.act==='remove'){if(!confirm('删除这条收藏？'))return;data.remove=true}
 db=await ext('favorite',data);
 if(data.remove&&job){for(const i of job.issues)if(i.favoriteId===r.id)delete i.favoriteId;drawIssues()}
 draw();
});
const oldDetail=drawDetail;
drawDetail=function(){
 oldDetail();const issue=job?.issues.find(i=>i.id===selected);
 const heading=[...document.querySelectorAll('#detail h3')].find(x=>x.textContent==='人工复核');
 if(!heading||!issue)return;
 const b=document.createElement('button');b.className='fxStar';b.style.marginLeft='12px';
 b.textContent=issue.favoriteId?'★ 已收藏':'☆ 收藏问题';heading.append(b);
 b.onclick=guard(async()=>{const id=job.id,on=!issue.favoriteId,note=on?prompt('收藏备注（选填）',''):'';
 if(note===null)return;b.disabled=true;
 try{const v=await ext('collect',{id,issueId:issue.id,enabled:on,note});issue.favoriteId=v.favoriteId;
 if(job?.id===id)drawIssues();await refresh();toast('收藏状态已写入审查记录')}finally{b.disabled=false}});
 for(const l of issue.focusLinks||[]){
 const div=document.createElement('div');div.className='quote';
 div.innerHTML=l.kind==='owner'?`<b class="fxTag">业主要求</b> ${esc(l.relation)} · ${esc(l.ref)}<blockquote>${esc(l.clause_quote)}</blockquote>`:`<span class="fxTag">与收藏问题 ${esc(l.id)} 相似</span>`;
 heading.before(div);
 }
};
const oldIssues=drawIssues;
drawIssues=function(){oldIssues();if(!job)return;const stars=new Set(job.issues.filter(i=>i.favoriteId).map(i=>i.id));
 for(const b of document.querySelectorAll('#issues [data-issue]'))if(stars.has(b.dataset.issue))b.querySelector('strong')?.insertAdjacentHTML('afterbegin','<span class="fxStar" aria-label="已收藏">★ </span>')};
const oldJob=drawJob;
drawJob=function(){oldJob();if(!job?.focusResults?.length||!job.focusSources)return;
 $('#focusResults').innerHTML=job.focusResults.map(r=>{
 const s=job.focusSources[r.focus];
 return `<div class="quote"><strong>${esc(r.focus)}</strong><small>${esc(r.displayStatus||r.status)}</small><p>${esc(r.summary)}</p>${s?.kind==='owner'?`<details><summary>文件原文 · ${esc(s.docNo)} · 第 ${Number(s.page)} ${esc(s.pageUnit)}</summary><blockquote>${esc(s.quote)}</blockquote></details>`:''}${(r.issueIds||[]).map(i=>`<button data-fx-issue="${esc(i)}">查看 ${esc(i)}</button>`).join(' ')}</div>`;
 }).join('');
};
$('#focusResults').onclick=e=>{const b=e.target.closest('[data-fx-issue]');if(b){$('#categoryFilter').value='';$('#priorityFilter').value='';selected=b.dataset.fxIssue;tab('review');drawIssues();$('#detail').scrollIntoView({block:'center'})}};
if(token)guard(refresh)();
})();
