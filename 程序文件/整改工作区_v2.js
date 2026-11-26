const decisions={'确认修改':'需修改','不采纳':'不采纳','退回补查':'需复核'};
function detailsFor(id){
 const i=job?.issues.find(x=>x.id===id);
 if(!i)return esc(id);
 return '<details class="issueInfo"><summary><b class="priority '+esc(i.priority)+'">'+esc(i.priority)+'</b> '+esc(i.id)+' · '+esc(i.title)+'</summary><div><p>'+esc(i.category)+' · '+esc(priorityName[i.priority])+'　'+esc(i.priorityReason)+'</p><p><b>问题</b>　'+esc(i.description)+'</p><p><b>建议</b>　'+esc(i.suggestion)+'</p>'+i.citations.map(c=>'<blockquote>'+esc(citationLocation(c))+'<br>'+esc(c.quote)+'</blockquote>').join('')+(reviews[id]?.note?'<p><b>人工修改意见</b>　'+esc(reviews[id].note)+'</p>':'')+'</div></details>';
}
const originalDetail=drawDetail;
drawDetail=function(){
 originalDetail();
 const select=$('#reviewState'),note=$('#reviewNote');
 if(!select||!note)return;
 select.hidden=true;
 select.insertAdjacentHTML('afterend','<div class="actions decisionButtons">'+Object.entries(decisions).map(([key,value])=>'<button data-decision="'+key+'">'+value+'</button>').join('')+'</div>');
 note.placeholder='填写人工修改内容或需要核对的信息';
 function refresh(){
  for(const b of document.querySelectorAll('[data-decision]')){const active=b.dataset.decision===select.value;b.classList.toggle('primary',active);b.setAttribute('aria-pressed',active)}
  note.hidden=select.value!=='退回补查'&&!note.value;
 }
 for(const b of document.querySelectorAll('[data-decision]'))b.onclick=()=>{select.value=b.dataset.decision;saveReview();drawIssues();if(b.dataset.decision==='退回补查')$('#reviewNote')?.focus()};
 refresh();
};
const renderIssues=drawIssues;
drawIssues=function(){
 renderIssues();
 for(const row of document.querySelectorAll('[data-issue]')){
  const status=reviews[row.dataset.issue]?.status;
  row.classList.toggle('dismissedIssue',status==='不采纳');
  if(decisions[status])row.querySelector('.meta span:last-child').textContent=decisions[status];
 }
};
pickAmend=function(){
 if(!job||job.status==='running')return toast('请先完成审查或导入审查记录。');
 const items=job.issues.filter(i=>!['不采纳','已修改'].includes(reviews[i.id]?.status));
 modal('选择需要整改的问题','<div class="pickBar actions"><button id="pickAll">全选</button><button id="pickNone">取消全选</button><small id="pickedTotal"></small><button class="primary" id="confirmGenerate">生成选中问题的整改文本</button></div><p class="fieldnote">已勾选诊断页标记为“需修改”的问题。按住勾选框向下或向上拖动可连续选择。生成将调用模型。</p>'+items.map(i=>'<div class="pickIssue"><input aria-label="选择 '+esc(i.id)+'" type="checkbox" data-amend-issue="'+esc(i.id)+'" '+(reviews[i.id]?.status==='确认修改'?'checked':'')+'><div>'+detailsFor(i.id)+'<small>'+esc(decisions[reviews[i.id]?.status]||'待判断')+'</small></div></div>').join(''));
 const boxes=[...document.querySelectorAll('[data-amend-issue]')];
 function count(){const n=boxes.filter(b=>b.checked).length;$('#pickedTotal').textContent='已选 '+n+' / '+boxes.length;$('#confirmGenerate').disabled=!n}
 $('#pickAll').onclick=()=>{boxes.forEach(b=>b.checked=true);count()};$('#pickNone').onclick=()=>{boxes.forEach(b=>b.checked=false);count()};boxes.forEach(b=>b.onchange=count);
 $('#confirmGenerate').onclick=async()=>{try{await cacheCurrentReviews();await generateAmend()}catch(e){toast(e.message)}};count();
};
$('#generateAmend').onclick=pickAmend;$('#pickAmend').onclick=pickAmend;
let stroke=null,suppressClick=false;
const selector='[data-amend-issue],.acceptEdit';
function paint(box,value){box.checked=value;box.dispatchEvent(new Event('change',{bubbles:true}))}
document.addEventListener('pointerdown',e=>{
 if(e.button!==0||e.pointerType!=='mouse'||!e.target.matches(selector))return;
 stroke={boxes:[...e.target.closest('tbody,#dialogBody').querySelectorAll(selector)],last:e.target,value:!e.target.checked};suppressClick=true;e.preventDefault();paint(e.target,stroke.value);
});
document.addEventListener('pointerover',e=>{
 if(!stroke||!(e.buttons&1))return;
 const box=e.target.closest('.pickIssue,tr[data-edit]')?.querySelector(selector);
 const a=stroke.boxes.indexOf(stroke.last),b=stroke.boxes.indexOf(box);
 if(b<0||a===b)return;stroke.boxes.slice(Math.min(a,b),Math.max(a,b)+1).forEach(x=>paint(x,stroke.value));stroke.last=box;
});
document.addEventListener('click',e=>{if(suppressClick&&e.target.matches(selector)){e.preventDefault();e.stopImmediatePropagation()}},true);
function endStroke(){stroke=null;setTimeout(()=>suppressClick=false,0)}
window.addEventListener('pointerup',endStroke);window.addEventListener('blur',endStroke);
const renderAmends=drawAmendments;
drawAmendments=function(){
 renderAmends();
 for(const [index,row] of [...document.querySelectorAll('#amendRows [data-edit]')].entries()){
  const e=amendDraft.edits[index];row.cells[1].innerHTML=e.issueIds.map(detailsFor).join('')+'<p>'+esc(e.location)+'</p><small>'+esc(e.reason)+'</small>';
 }
 $('#amendUnresolved').innerHTML=amendDraft.unresolved.map(x=>'<div class="pendingIssue"><b>待补信息</b>　'+esc(x.reason)+detailsFor(x.issueId)+'</div>').join('');
};
$('#pickAmend').insertAdjacentHTML('beforebegin','<button id="importAmend">导入整改记录</button><input type="file" id="amendFile" hidden accept=".json">');
$('#importAmend').onclick=()=>$('#amendFile').click();
$('#amendFile').onchange=async e=>{
 const file=e.target.files[0];e.target.value='';if(!file)return;
 try{
 const record=JSON.parse((await file.text()).replace(/^\uFEFF/,''));
 if(desktopAmendDirty&&document.querySelector('[data-edit]')){await extended('save-draft',{id:job.id,edits:readEdits()});desktopAmendDirty=false}
 if(record.diagnosis){
  await cacheCurrentReviews();const r=await api('/api/import-result',{record});adoptRecord(r);tab('amend');await loadAmendments();
 }else if(record.originalSha256&&Array.isArray(record.edits)){
  if(!job)throw Error('请先导入对应的审查记录，再导入修改记录。');
  await cacheCurrentReviews();amendDraft=await extended('import-amend-log',{id:job.id,record});amendJobId=job.id;drawAmendments();
 }else throw Error('请选择保存的审查记录 JSON 或导出 Word 时生成的修改记录 JSON。');
 toast('已导入整改记录，共 '+amendDraft.edits.length+' 处替换内容。');
 }catch(err){toast(err.message)}
};
document.head.insertAdjacentHTML('beforeend','<style>.reviewgrid:has(.decisionButtons){grid-template-columns:1fr}.decisionButtons button{min-width:78px}.dismissedIssue strong{text-decoration:line-through;color:var(--muted)}.pickBar{position:sticky;top:0;z-index:1;background:var(--surface);padding:8px}.pickIssue{display:grid;grid-template-columns:24px 1fr;gap:8px;padding:10px 8px;border-bottom:1px solid var(--line)}.pickIssue input{margin-top:5px}.issueInfo summary{cursor:pointer;font-weight:500}.issueInfo p,.issueInfo blockquote{margin:6px 0;white-space:pre-wrap}.issueInfo blockquote{background:var(--soft);padding:8px}.pendingIssue{padding:12px;margin:8px 0;background:var(--semi-color-warning-light-default);border-radius:6px}.pendingIssue details{margin-top:5px}#amendRows td:nth-child(2){min-width:230px}</style>');
if(job){drawIssues();if(amendJobId===job.id)drawAmendments()}


/* 按页面分配工具，沿用现有控件及绑定的导入、生成事件。 */
recordLine.append($('#importAmend'), $('#amendFile'));
const workspaceFooter = document.querySelector('main > footer');
if (workspaceFooter) workspaceFooter.parentElement.append(workspaceFooter);
const switchBusinessTab = tab;
tab = function(name) {
    switchBusinessTab(name);
    document.body.dataset.businessPage = name;
};
tab(document.querySelector('.tab.active')?.id.replace('tab-', '') || 'review');
document.head.insertAdjacentHTML('beforeend', `<style>
#generateAmend,body:not([data-business-page="amend"]) #importAmend {display:none!important}
body[data-business-page="amend"] #documentWorkspace > :not(.toolbar),
body[data-business-page="amend"] .toolbar-actions {display:none!important}
body[data-business-page="amend"] .record-line {margin:0;padding:0;border:0;flex-wrap:wrap}
#documentWorkspace[hidden],#documentWorkspace [hidden],.reviewgrid [hidden] {display:none!important}
.reviewgrid .decisionButtons{gap:10px;flex-wrap:wrap}
.decisionButtons button[data-decision]{min-width:106px;min-height:44px;padding:8px 16px;font-weight:650;font-size:15px;border:1px solid var(--edge);color:var(--fg);background:var(--tint);border-radius:7px}
[data-decision="确认修改"]{--fg:#8b3325;--edge:#df998b;--tint:#ffe3da;--solid:#a03c2d}
[data-decision="不采纳"]{--fg:#3e4d61;--edge:#abb8c8;--tint:#e7edf4;--solid:#4b5c73}
[data-decision="退回补查"]{--fg:#704900;--edge:#dab04d;--tint:#ffedb7;--solid:#805600}
body[theme-mode="dark"] [data-decision="确认修改"]{--fg:#ffd5cd;--edge:#ad7164;--tint:#58362e}
body[theme-mode="dark"] [data-decision="不采纳"]{--fg:#e0e9fc;--edge:#7b8ba0;--tint:#374252}
body[theme-mode="dark"] [data-decision="退回补查"]{--fg:#ffe3a7;--edge:#a78a4f;--tint:#4e4026}
.decisionButtons button[data-decision]:hover{box-shadow:inset 0 0 0 1px var(--edge)}
.decisionButtons button[aria-pressed="true"]{color:white;background:var(--solid);border-color:var(--edge)}
.decisionButtons button[aria-pressed="true"]::before{content:'✓ ';font-weight:700}
</style>`);
