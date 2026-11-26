(() => {
    /* 图纸参数界面 v2（Claude 视觉稿）。接口、事件和状态逻辑与 v1 相同，只改展示。 */
    const box=document.createElement('details');
    box.id='drawingPanel';box.className='panel input-panel dp';box.hidden=true;
    $('#tab-review').prepend(box);
    const css=document.createElement('style');
    css.textContent=`
#drawingPanel [hidden]{display:none!important}
#drawingPanel{--dp-navy:var(--bp-navy,#12305A);--dp-steel:var(--bp-steel,#1B5AC0);--dp-amber:var(--bp-amber,#E09A0E);--dp-green:var(--bp-green,#2E8B57);--dp-red:var(--bp-red,#D2452F);--dp-line:var(--line,#D9E1EC);--dp-soft:var(--soft,#F2F5F9);--dp-muted:var(--muted,#6B7280);--dp-num:var(--num-font,"Segoe UI",sans-serif);margin-bottom:16px;padding:0!important;overflow:hidden}
#drawingPanel>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;padding:14px 18px;user-select:none}
#drawingPanel>summary::-webkit-details-marker{display:none}
#drawingPanel .dp-ico{width:34px;height:34px;border-radius:8px;background:#E7EEFA;color:var(--dp-steel);display:grid;place-items:center;flex:none}
#drawingPanel .dp-ico svg{width:19px;height:19px}
#drawingPanel .dp-title{font-weight:650;font-size:15px;color:var(--dp-navy)}
#drawingPanel .dp-sub{font-size:12px;color:var(--dp-muted);margin-top:1px}
#drawingPanel .dp-chip{margin-left:auto;font-size:12px;padding:3px 10px;border-radius:999px;background:var(--dp-soft);color:var(--dp-muted);white-space:nowrap}
#drawingPanel .dp-chip.run{background:#E7EEFA;color:var(--dp-steel)}
#drawingPanel .dp-chip.todo{background:#FDF3DF;color:#9A6305}
#drawingPanel .dp-chip.ok{background:#E3F2EA;color:var(--dp-green)}
#drawingPanel .dp-caret{color:var(--dp-muted);transition:transform .15s;flex:none}
#drawingPanel[open] .dp-caret{transform:rotate(180deg)}
#drawingPanel .dp-body{border-top:1px solid var(--dp-line);padding:16px 18px 18px}
#drawingPanel .dp-steps{display:flex;gap:0;margin:0 0 16px;counter-reset:s}
#drawingPanel .dp-step{flex:1;display:flex;align-items:center;gap:8px;font-size:12px;color:var(--dp-muted);position:relative}
#drawingPanel .dp-step:not(:last-child)::after{content:"";flex:1;height:2px;background:var(--dp-line);margin:0 10px}
#drawingPanel .dp-step b{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font:600 12px/1 var(--dp-num);background:var(--dp-soft);color:var(--dp-muted);flex:none}
#drawingPanel .dp-step.done b{background:var(--dp-green);color:#fff}
#drawingPanel .dp-step.done:not(:last-child)::after{background:var(--dp-green)}
#drawingPanel .dp-step.now{color:var(--dp-navy);font-weight:600}
#drawingPanel .dp-step.now b{background:var(--dp-steel);color:#fff;box-shadow:0 0 0 4px #E7EEFA}
#drawingPanel .dp-drop{display:flex;align-items:center;gap:14px;border:1.5px dashed #B9C7DB;border-radius:10px;padding:14px 16px;background:#F8FAFD}
#drawingPanel .dp-drop.over{border-color:var(--dp-steel);background:#EEF3FC}
#drawingPanel .dp-drop p{margin:0;font-size:13px;color:var(--dp-navy)}
#drawingPanel .dp-drop small{display:block;color:var(--dp-muted);font-size:12px}
#drawingPanel .dp-drop .dp-actions{margin-left:auto;display:flex;gap:8px}
#drawingPanel input[type=file]{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none}
#drawingPanel .dp-btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--dp-line);background:#fff;color:var(--dp-navy);border-radius:7px;padding:7px 14px;font-size:13px;cursor:pointer;white-space:nowrap}
#drawingPanel .dp-btn:hover:not(:disabled){border-color:var(--dp-steel);color:var(--dp-steel)}
#drawingPanel .dp-btn.primary{background:var(--dp-steel);border-color:var(--dp-steel);color:#fff}
#drawingPanel .dp-btn.primary:hover:not(:disabled){background:#154A9E;color:#fff}
#drawingPanel .dp-btn:disabled{opacity:.45;cursor:not-allowed}
#drawingPanel .dp-btn.ghost{border-color:transparent;background:transparent;color:var(--dp-muted);padding:5px 8px}
#drawingPanel .dp-docs{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:8px;margin-top:10px}
#drawingPanel .dp-doc{display:flex;align-items:center;gap:9px;border:1px solid var(--dp-line);border-radius:8px;padding:6px 6px 6px 9px;background:#fff;min-width:0}
#drawingPanel .dp-doc i{font-style:normal;font:700 10px/1 var(--dp-num);color:#fff;background:var(--dp-red);border-radius:3px;padding:4px 4px;flex:none}
#drawingPanel .dp-doc .nm{min-width:0;flex:1}
#drawingPanel .dp-doc .nm b{display:block;font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#drawingPanel .dp-doc .nm select{border:0;background:transparent;padding:0;font-size:11.5px;color:var(--dp-muted);cursor:pointer}
#drawingPanel .dp-doc [data-remove]{border:0;background:transparent;color:var(--dp-muted);font-size:16px;line-height:1;padding:4px 6px;border-radius:5px;cursor:pointer}
#drawingPanel .dp-doc [data-remove]:hover:not(:disabled){background:#FBEAE7;color:var(--dp-red)}
#drawingPanel .dp-note{margin:10px 0 0;font-size:12px;color:#9A6305;background:#FDF6E7;border-left:3px solid var(--dp-amber);padding:7px 10px;border-radius:0 6px 6px 0}
#drawingPanel .dp-note:empty{display:none}
#drawingPanel .dp-prog{margin-top:14px;display:grid;grid-template-columns:1fr 1fr auto;gap:14px;align-items:center}
#drawingPanel .dp-bar{font-size:12px;color:var(--dp-muted)}
#drawingPanel .dp-bar .hd{display:flex;justify-content:space-between;margin-bottom:5px}
#drawingPanel .dp-bar .hd b{color:var(--dp-navy);font-weight:600}
#drawingPanel .dp-bar .tr{height:6px;border-radius:3px;background:var(--im-track,#E3E9F1);overflow:hidden}
#drawingPanel .dp-bar .tr i{display:block;height:100%;background:var(--dp-steel);border-radius:3px;transition:width .4s}
#drawingPanel .dp-bar.done .tr i{background:var(--dp-green)}
#drawingPanel .dp-bar.wait{opacity:.55}
#drawingPanel .dp-kpis{display:flex;gap:10px;margin:16px 0 12px;flex-wrap:wrap}
#drawingPanel .dp-kpi{border:1px solid var(--dp-line);border-radius:8px;padding:8px 14px;min-width:104px;background:#fff}
#drawingPanel .dp-kpi b{display:block;font:600 22px/1.2 var(--dp-num);color:var(--dp-navy)}
#drawingPanel .dp-kpi span{font-size:11.5px;color:var(--dp-muted)}
#drawingPanel .dp-kpi.warn b{color:var(--dp-amber)}
#drawingPanel .dp-kpi.ok b{color:var(--dp-green)}
#drawingPanel .dp-kpi.mute b{color:var(--dp-muted)}
#drawingPanel .dp-kpi.info{flex:1;min-width:220px;border-style:dashed;background:#F8FAFD;font-size:12px;color:var(--dp-muted);display:flex;align-items:center;line-height:1.6}
#drawingPanel .dp-tool{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
#drawingPanel .dp-pills{display:flex;gap:6px;flex-wrap:nowrap;overflow-x:auto;flex:1;min-width:0;padding-bottom:4px;scrollbar-width:thin}
#drawingPanel .dp-pill{border:1px solid var(--dp-line);background:#fff;border-radius:999px;padding:3px 11px;font-size:12px;color:var(--dp-navy);cursor:pointer;white-space:nowrap}
#drawingPanel .dp-pill em{font-style:normal;color:var(--dp-muted);margin-left:4px;font-family:var(--dp-num)}
#drawingPanel .dp-pill.sel{background:var(--dp-navy);border-color:var(--dp-navy);color:#fff}
#drawingPanel .dp-pill.sel em{color:#C3D0E4}
#drawingPanel .dp-pill.cf{border-color:#F0D29A;color:#9A6305;background:#FDF6E7}
#drawingPanel .dp-pill.cf.sel{background:var(--dp-amber);border-color:var(--dp-amber);color:#fff}
#drawingPanel .dp-confirm{display:flex;gap:10px;align-items:center;justify-content:flex-end;margin-top:10px;padding:10px 12px;border-radius:8px;background:#F4F7FB;border:1px solid var(--dp-line)}
#drawingPanel .dp-confirm .sum{margin-right:auto;font-size:12.5px;color:var(--dp-navy)}
#drawingPanel .dp-confirm .sum b{font-family:var(--dp-num);font-size:15px}
#drawingPanel .dp-confirm label{font-size:12px;color:var(--dp-muted);display:flex;align-items:center;gap:6px}
#drawingPanel .dp-confirm input{width:120px;padding:6px 9px;font-size:13px;border:1px solid var(--dp-line);border-radius:6px}
#drawingPanel .drrows{max-height:440px;overflow:auto;border:1px solid var(--dp-line);border-radius:8px}
#drawingPanel table{border-collapse:separate;border-spacing:0;width:100%;font-size:13px;table-layout:fixed}
#drawingPanel thead th{position:sticky;top:0;z-index:2;background:#F4F7FB;color:var(--dp-muted);font-weight:500;font-size:12px;padding:8px 10px;border-bottom:1px solid var(--dp-line);text-align:left;white-space:nowrap}
#drawingPanel td{padding:6px 10px;border-bottom:1px solid #EDF1F6;vertical-align:middle;text-align:left}
#drawingPanel tr.zone td{position:sticky;top:33px;z-index:1;background:#EEF3FA;color:var(--dp-navy);font-weight:600;font-size:12.5px;padding:7px 10px;border-bottom:1px solid var(--dp-line)}
#drawingPanel tr.zone td small{font-weight:400;color:var(--dp-muted);margin-left:8px}
#drawingPanel tr.zone td .w{color:#9A6305;margin-left:8px;font-weight:500}
#drawingPanel tr.c td{background:#FFFBF2}
#drawingPanel tr.c td:first-child{box-shadow:inset 3px 0 var(--dp-amber)}
#drawingPanel tr.c+tr.c td{border-top-color:transparent}
#drawingPanel tr:hover td:not(.z){background:#F6F9FD}
#drawingPanel tr.c:hover td{background:#FFF6E3}
#drawingPanel td.f{color:var(--dp-navy);min-width:150px}
#drawingPanel td.f .ph{display:inline-block;font-size:11px;color:var(--dp-steel);background:#E7EEFA;border-radius:4px;padding:0 6px;margin-left:6px}
#drawingPanel td.f .sc{display:block;margin-top:4px}
#drawingPanel td.f .sc input{width:100%;font-size:12px;padding:4px 7px;border:1px dashed #E3B964;border-radius:5px;background:#fff}
#drawingPanel td.f [data-split]{margin-top:4px;font-size:11.5px;padding:2px 8px;border:1px solid #F0D29A;color:#9A6305;background:#fff;border-radius:5px;cursor:pointer}
#drawingPanel td.v input{width:100%;min-width:0;text-overflow:ellipsis;font-size:13px;padding:5px 8px;border:1px solid transparent;border-radius:5px;background:transparent;color:inherit}
#drawingPanel td.v input:hover{border-color:var(--dp-line);background:#fff}
#drawingPanel td.v input:focus{border-color:var(--dp-steel);background:#fff;outline:none;box-shadow:0 0 0 3px #E7EEFA}
#drawingPanel td.u{color:var(--dp-muted);white-space:nowrap;font-size:12px}
#drawingPanel td.ck{width:34px;text-align:center}
#drawingPanel td.ck input{width:15px;height:15px;accent-color:var(--dp-steel);cursor:pointer}
#drawingPanel tr.c td.ck input{accent-color:var(--dp-amber)}
#drawingPanel .dp-src{max-width:100%;overflow:hidden;text-overflow:ellipsis;display:inline-flex;align-items:center;gap:5px;border:1px solid var(--dp-line);background:#fff;border-radius:5px;padding:2px 8px;font-size:11.5px;color:var(--dp-steel);cursor:pointer;white-space:nowrap}
#drawingPanel .dp-src:hover{border-color:var(--dp-steel);background:#EEF3FC}
#drawingPanel .dp-src svg{width:12px;height:12px}
#drawingPanel .dp-st{display:inline-block;font-size:11.5px;padding:1px 8px;border-radius:999px;white-space:nowrap}
#drawingPanel .dp-st.t{background:var(--dp-soft);color:var(--dp-muted)}
#drawingPanel .dp-st.c{background:#FDF0D8;color:#9A6305}
#drawingPanel .dp-st.o{background:#E3F2EA;color:var(--dp-green)}
#drawingPanel tr.hide{display:none}
#drawingPanel .dp-reuse{display:flex;align-items:center;gap:10px;margin:14px 0 0;padding:10px 12px;border-radius:8px;background:#EEF3FC;font-size:13px;color:var(--dp-navy)}
#drawingPanel .dp-reuse button{margin-left:auto}
#drawingPanel .dp-rec{margin-top:14px;border:1px solid var(--dp-line);border-radius:8px}
#drawingPanel .dp-rec>summary{cursor:pointer;padding:9px 12px;font-size:12.5px;color:var(--dp-navy)}
#drawingPanel .dp-rec .lst{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:4px 16px;padding:4px 12px 12px;max-height:260px;overflow:auto}
#drawingPanel .dp-rec .lst button{border:0;background:none;text-align:left;padding:3px 0;font-size:12px;color:var(--dp-navy);cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#drawingPanel .dp-rec .lst button:hover{color:var(--dp-steel);text-decoration:underline}
#drawingPanel .dp-rec .lst code{font:600 11px var(--dp-num);color:var(--dp-steel);margin-right:6px}
#drawingSource{width:min(980px,92vw);max-width:980px;padding:0;border:1px solid var(--line,#D9E1EC);border-radius:12px;overflow:hidden;background:#fff}
#drawingSource .hd{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line,#D9E1EC);background:#F4F7FB}
#drawingSource .hd b{color:var(--bp-navy,#12305A);font-size:14px}
#drawingSource .hd small{color:var(--muted,#6B7280);font-size:12px}
#drawingSource .hd button{margin-left:auto;border:1px solid var(--line,#D9E1EC);background:#fff;border-radius:6px;padding:4px 12px;cursor:pointer}
#drawingSource .bd{padding:16px;background:repeating-linear-gradient(0deg,#F7F9FC 0 23px,#EEF2F8 23px 24px),repeating-linear-gradient(90deg,transparent 0 23px,#EEF2F8 23px 24px)}
#drawingSource img{display:block;max-width:100%;max-height:68vh;margin:auto;object-fit:contain;background:#fff;border:1px solid #C9D5E6;box-shadow:0 4px 18px #12305A1A}
#drawingSource .ft{padding:9px 16px;font-size:12px;color:var(--muted,#6B7280);border-top:1px solid var(--line,#D9E1EC)}
.dp-basis{margin:12px 0;border:1px solid #CFDCF0;border-left:4px solid var(--bp-steel,#1B5AC0);border-radius:0 8px 8px 0;background:#F5F8FE;padding:10px 14px}
.dp-basis .tag{display:inline-block;font-size:11px;font-weight:600;color:#fff;background:var(--bp-steel,#1B5AC0);border-radius:4px;padding:1px 7px;margin-right:8px;vertical-align:1px}
.dp-basis .val{font-size:13px;color:#1F2A37;line-height:1.75}.dp-basis .val b{color:var(--bp-navy,#12305A)}
.dp-basis .src{display:flex;align-items:center;gap:6px;margin-top:6px;border:0;background:none;padding:0;font-size:12px;color:var(--bp-steel,#1B5AC0);cursor:pointer}
.dp-basis .src:hover{text-decoration:underline}
.dp-basis .src svg{width:13px;height:13px}
body[theme-mode=dark] #drawingPanel{--dp-navy:#DCE6F5;--dp-steel:#6FA3FF;--dp-line:#3A4558;--dp-soft:#2A3240;--dp-muted:#A3AEC0;color:#E6EDF7}
body[theme-mode=dark] #drawingPanel .dp-ico{background:#23314A}
body[theme-mode=dark] #drawingPanel .dp-chip.run{background:#23314A;color:#8DB6FF}
body[theme-mode=dark] #drawingPanel .dp-chip.todo,body[theme-mode=dark] #drawingPanel .dp-note,body[theme-mode=dark] #drawingPanel .dp-st.c{background:#3A2E14;color:#F2C46B}
body[theme-mode=dark] #drawingPanel .dp-chip.ok,body[theme-mode=dark] #drawingPanel .dp-st.o{background:#173326;color:#6CCB94}
body[theme-mode=dark] #drawingPanel .dp-step.now b{box-shadow:0 0 0 4px #23314A}
body[theme-mode=dark] #drawingPanel .dp-drop{background:#1E2633;border-color:#3E4A5E}
body[theme-mode=dark] #drawingPanel .dp-drop.over{background:#22324A}
body[theme-mode=dark] #drawingPanel .dp-btn,body[theme-mode=dark] #drawingPanel .dp-doc,body[theme-mode=dark] #drawingPanel .dp-kpi,body[theme-mode=dark] #drawingPanel .dp-pill,body[theme-mode=dark] #drawingPanel .dp-src,body[theme-mode=dark] #drawingPanel td.f [data-split]{background:#232B38;color:#E6EDF7}
body[theme-mode=dark] #drawingPanel .dp-btn.primary{background:#2F6FD6;border-color:#2F6FD6;color:#fff}
body[theme-mode=dark] #drawingPanel .dp-kpi.info,body[theme-mode=dark] #drawingPanel .dp-confirm,body[theme-mode=dark] #drawingPanel thead th{background:#1E2633;color:#A3AEC0}
body[theme-mode=dark] #drawingPanel .dp-pill.sel{background:#6FA3FF;border-color:#6FA3FF;color:#0F1724}
body[theme-mode=dark] #drawingPanel .dp-pill.sel em{color:#1F2A37}
body[theme-mode=dark] #drawingPanel .dp-pill.cf{background:#3A2E14;border-color:#6B5320;color:#F2C46B}
body[theme-mode=dark] #drawingPanel .dp-pill.cf.sel{background:#E09A0E;border-color:#E09A0E;color:#1A1A1A}
body[theme-mode=dark] #drawingPanel .dp-confirm input,body[theme-mode=dark] #drawingPanel td.f .sc input,body[theme-mode=dark] #drawingPanel .dp-doc .nm select{background:#161C26;color:#E6EDF7}
body[theme-mode=dark] #drawingPanel td.f .sc input{border-color:#8A6A24}
body[theme-mode=dark] #drawingPanel td.f .sc input::placeholder,body[theme-mode=dark] #drawingPanel .dp-confirm input::placeholder{color:#7D889A}
body[theme-mode=dark] #drawingPanel td{border-bottom-color:#2E3747;color:#E6EDF7;background:#1B222D}
body[theme-mode=dark] #drawingPanel tr.zone td{background:#243049;color:#DCE6F5}
body[theme-mode=dark] #drawingPanel tr.c td{background:#2E2714}
body[theme-mode=dark] #drawingPanel tr:hover td:not(.z){background:#222B3A}
body[theme-mode=dark] #drawingPanel tr.c:hover td{background:#3A3018}
body[theme-mode=dark] #drawingPanel td.f .ph{background:#23314A;color:#8DB6FF}
body[theme-mode=dark] #drawingPanel td.f [data-split]{color:#F2C46B;border-color:#6B5320}
body[theme-mode=dark] #drawingPanel td.v input{color:#E6EDF7}
body[theme-mode=dark] #drawingPanel td.v input:hover,body[theme-mode=dark] #drawingPanel td.v input:focus{background:#161C26;box-shadow:none}
body[theme-mode=dark] #drawingPanel .dp-src{color:#8DB6FF}
body[theme-mode=dark] #drawingPanel .dp-src:hover{background:#23314A}
body[theme-mode=dark] #drawingPanel .dp-st.t{background:#2A3240;color:#A3AEC0}
body[theme-mode=dark] #drawingPanel .dp-reuse{background:#23314A;color:#DCE6F5}
body[theme-mode=dark] #drawingPanel .dp-rec .lst button{color:#DCE6F5}
body[theme-mode=dark] #drawingPanel .dp-doc [data-remove]:hover:not(:disabled){background:#3A2522}
body[theme-mode=dark] #drawingSource{background:#1B222D;border-color:#3A4558}
body[theme-mode=dark] #drawingSource .hd{background:#222B38;border-color:#3A4558}
body[theme-mode=dark] #drawingSource .hd b{color:#E6EDF7}
body[theme-mode=dark] #drawingSource .hd small,body[theme-mode=dark] #drawingSource .ft{color:#B4BFCF;border-color:#3A4558}
body[theme-mode=dark] #drawingSource .hd button{background:#2F6FD6;border-color:#2F6FD6;color:#fff}
body[theme-mode=dark] #drawingSource .bd{background:repeating-linear-gradient(0deg,#141A23 0 23px,#1E2633 23px 24px),repeating-linear-gradient(90deg,transparent 0 23px,#1E2633 23px 24px)}
body[theme-mode=dark] .dp-basis{background:#1E2A40;border-color:#34507A;border-left-color:#6FA3FF}
body[theme-mode=dark] .dp-basis .val{color:#DCE6F5}
body[theme-mode=dark] .dp-basis .val b{color:#BFD3F5}
body[theme-mode=dark] .dp-basis .src{color:#8DB6FF}
`;
    document.head.append(css);
    const ICON={
        sheet:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 9h18M8 9v11M14 13h4M14 16h3"/></svg>',
        img:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-4.5-4.5L7 20"/></svg>',
        up:'<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 16V4M7 9l5-5 5 5M4 17v3h16v-3"/></svg>',
        caret:'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m6 9 6 6 6-6"/></svg>'
    };
    box.innerHTML='<summary><span class="dp-ico">'+ICON.sheet+'</span><span><div class="dp-title">图纸参数 <small style="font-weight:400;color:var(--dp-muted)">（可选）</small></div><div class="dp-sub" id="drawingSub">上传设计总说明或勘察报告，AI 逐字摘录参数，人工确认后作为图实比对依据</div></span><span class="dp-chip" id="drawingChip">未上传</span><span class="dp-caret">'+ICON.caret+'</span></summary>'
        +'<div class="dp-body"><div class="dp-steps" id="drawingSteps"></div>'
        +'<div class="dp-drop" id="drawingDrop"><span class="dp-ico">'+ICON.up+'</span><div><p>选择或拖入图纸 PDF</p><small>可多选；逐个指定资料类型。图纸在本机识别，不上传原图</small></div><div class="dp-actions"><label class="dp-btn" for="drawingFiles">选择文件<input id="drawingFiles" type="file" multiple accept=".pdf"></label><button id="drawingRead" class="dp-btn primary">读图并提取</button><button id="drawingCancel" class="dp-btn" hidden>取消</button></div></div>'
        +'<div class="dp-docs" id="drawingDocs"></div><p class="dp-note" id="drawingNote"></p><div id="drawingProgress" aria-live="polite"></div><div id="drawingCandidates"></div></div>';
    const modal=document.createElement('dialog');modal.id='drawingSource';document.body.append(modal);
    const field=v=>esc(String(v??''));
    const apiBefore=api;
    let sha='',view=null,timeout=0,epoch=0,choices=new Set(),edits={},person='',busy=false;
    let invalidating=Promise.resolve(),scopes={},split=new Set();
    let items=[],lastRevision=-1,dirty=false,reuseJob=null,filter='';
    const key=c=>JSON.stringify([c.zone||'',c.name,c.drawingScope||c.phase||'']);
    const kind=()=>currentType()?.name||'通用';
    const act=(action,data={})=>apiBefore('/api/extended/drawing-'+action,{...data,sha256:sha,revision:view?.draft?.revision});
    const shortDoc=n=>String(n||'').replace(/\.pdf/i,'').replace(/^.*?(设计总说明|勘察报告)/,'$1');
    async function source(s){
        try{
            const r=await apiBefore('/api/extended/drawing-source',{source:s});
            modal.innerHTML='<div class="hd"><b></b><small></small><button type="button">关闭</button></div><div class="bd"></div><div class="ft">图纸原文截取 · 审查端图纸识别（本机 OCR，坐标取自识别行）</div>';
            modal.querySelector('.hd b').textContent=s.doc;
            modal.querySelector('.hd small').textContent='第 '+s.page+' 页';
            modal.querySelector('.hd button').onclick=()=>modal.close();
            const img=new Image();img.alt='图纸原文截取';img.src=r.image;modal.querySelector('.bd').append(img);
            if(!modal.open)modal.showModal();
        }catch(e){toast(e.message)}
    }
    modal.addEventListener('click',e=>{if(e.target===modal)modal.close()});
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
        ++epoch;clearTimeout(timeout);sha=next;view=null;lastRevision=-1;items=[];choices.clear();edits={};person='';dirty=false;filter='';box.open=false;
        if(!box.hidden)refresh(true);
    }
    function bar(label,done,total,text,state){
        const pct=total?Math.min(100,Math.round(done/total*100)):0;
        return '<div class="dp-bar '+state+'"><div class="hd"><b>'+label+'</b><span>'+field(text)+'</span></div><div class="tr"><i style="width:'+(state==='done'?100:pct)+'%"></i></div></div>';
    }
    function render(){
        if(!view)return;
        const s=view.draft,op=view.progress,ready=view.engine.ready;
        busy=op.status==='running';
        const active=s.parameters.length&&!dirty&&s.kind===kind();
        const conflictKeys=new Set(view.conflicts.map(JSON.stringify));
        const rejectedTotal=s.aiLog.reduce((n,l)=>n+(l.rejected||0),0);
        /* 头部状态 */
        const chip=$('#drawingChip');
        if(active){chip.className='dp-chip ok';chip.textContent='已确认 '+s.parameters.length+' 项';$('#drawingSub').textContent='审查时作为图实比对依据 · 确认人 '+(s.reviewer||'—')}
        else if(busy){chip.className='dp-chip run';chip.textContent=op.phase==='提取'?'AI 提取中':'读图中'}
        else if(s.candidates.length){chip.className='dp-chip todo';chip.textContent=(dirty?'已修改，':'')+'待确认 '+s.candidates.length+' 项'}
        else if(s.documents.length){chip.className='dp-chip';chip.textContent='已上传 '+s.documents.length+' 份'}
        else{chip.className='dp-chip';chip.textContent='未上传'}
        if(!active)$('#drawingSub').textContent='上传设计总说明或勘察报告，AI 逐字摘录参数，人工确认后作为图实比对依据';
        /* 步骤条 */
        const stage=active?4:s.candidates.length&&!busy?3:busy&&op.phase==='提取'?2:busy?1:s.documents.length?1:0;
        $('#drawingSteps').innerHTML=['上传图纸','本机读图','AI 摘录 · 逐字校验','人工确认'].map((t,i)=>'<div class="dp-step '+(i<stage||stage===4?'done':i===stage?'now':'')+'"><b>'+(i<stage||stage===4?'✓':i+1)+'</b>'+t+'</div>').join('');
        /* 按钮与资料 */
        $('#drawingRead').disabled=busy||!ready||!s.documents.length;
        $('#drawingFiles').disabled=busy||!ready;$('#drawingFiles').parentElement.toggleAttribute('hidden',busy);$('#drawingCancel').hidden=!busy;
        $('#drawingRead').hidden=busy;
        $('#drawingRead').textContent=['failed','cancelled'].includes(op.status)?'继续读图和提取':s.candidates.length?'重新读图并提取':'读图并提取';
        $('#drawingNote').textContent=[ready?'':view.engine.message,/深基坑|SMW/i.test(kind())?'':'当前方案类别的字段表尚未实测验证，提取结果请逐项核对',op.error||''].filter(Boolean).join(' · ');
        $('#drawingDocs').innerHTML=s.documents.map((d,i)=>'<div class="dp-doc" title="'+field(d.name)+'"><i>PDF</i><div class="nm"><b>'+field(shortDoc(d.name))+'</b><select data-type="'+i+'" '+(busy?'disabled':'')+' aria-label="资料类型">'+['设计总说明','岩土工程勘察报告'].map(t=>'<option '+(t===d.type?'selected':'')+'>'+t+'</option>').join('')+'</select></div><button data-remove="'+i+'" '+(busy?'disabled':'')+' title="移除" aria-label="移除">×</button></div>').join('');
        /* 进度 */
        const elapsed=op.elapsed||0;
        if(op.phase){
            const reading=op.phase==='读图',extracting=op.phase==='提取';
            const readText=reading?'第 '+Math.min(op.total,op.page||1)+'/'+op.total+' 张 · 瓦片 '+(op.tile||0)+'/'+(op.tileCount||0):'完成';
            const exText=extracting?op.done+'/'+op.total+' 批 · 拒收 '+(op.rejected||0)+' 项':reading?'等待读图':'完成';
            $('#drawingProgress').innerHTML='<div class="dp-prog">'+bar('本机读图',reading?(op.tile||0):1,reading?(op.tileCount||1):1,readText,reading?(busy?'':'wait'):'done')
                +bar('AI 摘录',extracting?op.done:0,extracting?op.total:1,exText,extracting?(busy||op.status!=='done'?'':'done'):reading?'wait':'done')
                +'<small style="color:var(--dp-muted);font-family:var(--dp-num)">已用 '+elapsed+' s</small></div>';
        }else $('#drawingProgress').innerHTML='';
        /* 候选 */
        const pane=$('#drawingCandidates');pane.replaceChildren();
        if(reuseJob?.drawingParams?.parameters?.length&&!active&&!busy){
            const rb=document.createElement("div");rb.className="dp-reuse";
            rb.innerHTML='<span>上次审查已确认 <b>'+reuseJob.drawingParams.parameters.length+'</b> 项图纸参数（《'+field(reuseJob.document.name)+'》），复审可直接沿用，不必重新读图。</span>';
            const use=document.createElement('button');use.className='dp-btn primary';use.textContent='沿用';
            use.onclick=()=>run(async()=>{dirty=false;await action("reuse",{recordId:reuseJob.id},true);box.open=false});rb.append(use);pane.append(rb);
        }
        if(job?.drawingParams&&job.document.sha256===sha){
            const rec=document.createElement('details');rec.className='dp-rec';
            const snap=job.drawingParams;
            rec.innerHTML='<summary>记录中的图纸参数 · '+snap.parameters.length+' 项 · '+field(snap.reviewer)+' · '+field(snap.confirmedAt)+'</summary><div class="lst"></div>';
            const lst=rec.querySelector('.lst');
            for(const p of snap.parameters){const b=document.createElement('button');b.innerHTML='<code>'+field(p.id)+'</code>'+field(p.label+' '+(p.zone||'')+(p.drawingScope?'（'+p.drawingScope+'）':'')+' = '+p.value+' '+(p.unit||''));b.title=p.source.doc+' 第'+p.source.page+'页';b.onclick=()=>source(p.source);lst.append(b)}
            pane.append(rec);
        }
        if(!s.candidates.length||busy)return;
        const grouped=new Map();
        for(const c of s.candidates){if(!grouped.has(key(c)))grouped.set(key(c),[]);grouped.get(key(c)).push(c)}
        const groups=[...grouped].sort(([a],[b])=>a.localeCompare(b,'zh-CN'));
        const checked=new Set(s.parameters.map(p=>p.candidateId));
        const zoneOf=c=>c.zone||'全场通用';
        const zones=new Map();
        for(const c of s.candidates){const z=zoneOf(c);const e=zones.get(z)||{n:0,cf:0};e.n++;if(conflictKeys.has(key(c)))e.cf++;zones.set(z,e)}
        const zoneList=[...zones].sort(([a],[b])=>a==='全场通用'?-1:b==='全场通用'?1:a.localeCompare(b,'zh-CN'));
        const nConf=conflictKeys.size,nPicked=s.candidates.filter(c=>choices.has(c.id)).length;
        let html='<div class="dp-kpis"><div class="dp-kpi"><b>'+s.candidates.length+'</b><span>候选（已逐字校验）</span></div><div class="dp-kpi '+(nConf?'warn':'ok')+'" data-pending-conflicts><b>'+nConf+'</b><span>冲突待选定</span></div><div class="dp-kpi mute"><b>'+rejectedTotal+'</b><span>拒收（原文找不到）</span></div><div class="dp-kpi '+(active?'ok':'')+'"><b>'+nPicked+'</b><span>'+(active?'已确认':'已勾选')+'</span></div><div class="dp-kpi info">只有确认过的参数才会进入审查；同一字段数值不同时必须选定一个，或点“区分工况”分别保留。</div></div>';
        html+='<div class="dp-tool"><div class="dp-pills"><button class="dp-pill'+(filter===''?' sel':'')+'" data-filter="">全部<em>'+s.candidates.length+'</em></button>'+(nConf?'<button class="dp-pill cf'+(filter==='*cf*'?' sel':'')+'" data-filter="*cf*">冲突<em>'+nConf+'</em></button>':'')
            +zoneList.map(([z,e])=>'<button class="dp-pill'+(filter===z?' sel':'')+'" data-filter="'+field(z)+'">'+field(z)+'<em>'+e.n+'</em></button>').join('')+'</div>'
            +'</div>';
        html+='<div class="drrows"><table><colgroup><col style="width:38px"><col style="width:22%"><col><col style="width:56px"><col style="width:190px"><col style="width:76px"></colgroup><thead><tr><th></th><th>字段</th><th>值（可修改，悬停看原文摘录）</th><th>单位</th><th>来源</th><th>状态</th></tr></thead><tbody>';
        items=[];
        const byZone=new Map();
        for(const [k,rows] of groups){const z=zoneOf(rows[0]);if(!byZone.has(z))byZone.set(z,[]);byZone.get(z).push([k,rows])}
        let gi=0;
        for(const [z] of zoneList){
            const e=zones.get(z),list=byZone.get(z)||[];
            html+='<tr class="zone" data-zone="'+field(z)+'"><td colspan="6">'+field(z)+'<small>'+e.n+' 项</small>'+(e.cf?'<span class="w">· '+e.cf+' 项冲突</span>':'')+'</td></tr>';
            for(const [k,rows] of list){
                const conflict=conflictKeys.has(k),groupIndex=items.length,separate=split.has(k),g=gi++;
                for(const c of rows){
                    const i=items.push(c)-1;
                    const st=!dirty&&checked.has(c.id)?'<span class="dp-st o">已确认</span>':conflict?'<span class="dp-st c">冲突</span>':'<span class="dp-st t">待确认</span>';
                    html+='<tr class="'+(conflict?'c':'')+'" data-z="'+field(z)+'" data-cf="'+(conflict?1:0)+'"><td class="ck"><input aria-label="选择候选" data-pick="'+i+'" type="'+(conflict&&!separate?'radio':'checkbox')+'" name="drawGroup'+g+'" '+(choices.has(c.id)?'checked':'')+'></td>'
                        +'<td class="f">'+field(c.name)+(c.drawingScope||c.phase?'<span class="ph">'+field(c.drawingScope||c.phase)+'</span>':'')
                        +(conflict?(separate?'<span class="sc"><input aria-label="适用工况" data-scope="'+i+'" placeholder="适用工况，如 常规开挖" value="'+field(scopes[c.id]||'')+'"></span>':i===groupIndex?'<br><button data-split="'+i+'">区分工况，分别保留</button>':''):'')+'</td>'
                        +'<td class="v"><input type="text" data-edit="'+i+'" value="'+field(edits[c.id]??c.value)+'" title="'+field(c.quote||'')+'"></td><td class="u">'+field(c.unit)+'</td>'
                        +'<td><button class="dp-src" data-source="'+i+'" title="'+field(c.source)+'">'+ICON.img+field(shortDoc(c.source).replace(/\s*第(\d+)页$/,' · P$1'))+'</button></td><td>'+st+'</td></tr>';
                }
            }
        }
        const foot='<div class="dp-confirm"><span class="sum">已勾选 <b>'+nPicked+'</b> / '+s.candidates.length+' 项'+(nConf?'<span data-pending-note style="color:#9A6305"></span>':'')+'</span><label>确认人<input id="drawingReviewer" value="'+field(person)+'" autocomplete="off" placeholder="必填"></label><button id="drawingSafe" class="dp-btn">确认无冲突项</button><button id="drawingAll" class="dp-btn primary">全部确认</button></div>';
        pane.insertAdjacentHTML('beforeend',html+'</tbody></table></div>'+foot);
        updatePendingConflicts();
        applyFilter();
        if(!s.extractionComplete){$('#drawingSafe').disabled=true;$('#drawingAll').disabled=true}
        $('#drawingReviewer').oninput=e=>{person=e.target.value};
        $('#drawingSafe').onclick=()=>confirmRows(false);
        $('#drawingAll').onclick=()=>confirmRows(true);
    }
    function applyFilter(){
        box.querySelectorAll('.drrows tbody tr').forEach(tr=>{
            const z=tr.dataset.zone??tr.dataset.z;
            let show=filter===''||(filter==='*cf*'?(tr.classList.contains('zone')?box.querySelector('.drrows tr[data-z="'+CSS.escape(z)+'"][data-cf="1"]'):tr.dataset.cf==='1'):z===filter);
            tr.classList.toggle('hide',!show);
        });
        box.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('sel',b.dataset.filter===filter));
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
    async function addFiles(files){
        for(const file of files){if(!/\.pdf$/i.test(file.name)){toast('请选择 PDF 文件');continue}await action('upload',{...await fileData(file),type:'设计总说明'},true)}
    }
    $('#drawingFiles').onchange=e=>run(async()=>{const files=Array.from(e.target.files);e.target.value='';await addFiles(files)});
    const drop=$('#drawingDrop');
    drop.addEventListener('dragover',e=>{if(busy||!view?.engine.ready)return;e.preventDefault();drop.classList.add('over')});
    drop.addEventListener('dragleave',()=>drop.classList.remove('over'));
    drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('over');if(busy||!view?.engine.ready)return;run(()=>addFiles(Array.from(e.dataTransfer.files)))});
    $('#drawingRead').onclick=()=>run(async()=>{dirty=false;await action('start',{kind:kind(),config:cfg()},true)});
    $('#drawingCancel').onclick=()=>run(()=>action('cancel'));
    box.addEventListener('click',e=>{
        const el=e.target.closest('button');if(!el)return;
        if(el.dataset.filter!==undefined){filter=el.dataset.filter;applyFilter();return}
        if(el.dataset.split!==undefined){split.add(key(items[+el.dataset.split]));render()}
        if(el.dataset.source!==undefined)source(fromCandidate(items[+el.dataset.source]));
        if(el.dataset.remove!==undefined)run(()=>action('remove',{docId:view.draft.documents[+el.dataset.remove].sha256},true));
    });
    function updatePendingConflicts(){
        const card=box.querySelector('[data-pending-conflicts]');
        if(!card)return;
        const groups=new Map(view.conflicts.map(group=>[JSON.stringify(group),[]]));
        for(const c of items){
            const group=groups.get(key(c));
            if(group&&choices.has(c.id))group.push(c);
        }
        let pending=0;
        for(const chosen of groups.values()){
            if(chosen.length===1)continue;
            const names=new Set(chosen.map(c=>(scopes[c.id]||'').normalize('NFKC').toLowerCase().replace(/\s/g,'')));
            if(!chosen.length||names.has('')||names.size!==chosen.length)pending++;
        }
        card.querySelector('b').textContent=pending;
        card.classList.toggle('warn',pending>0);
        card.classList.toggle('ok',pending===0);
        const note=box.querySelector('[data-pending-note]');
        if(note)note.textContent=pending?' · '+pending+' 个字段待选定':'';
    }
    function changed(){
        if(!dirty&&view.draft.parameters.length){const id=epoch;const captured=view;
            invalidating=act('invalidate').then(r=>{if(id===epoch&&view===captured){view.draft.revision=r.draft.revision;view.draft.parameters=[];lastRevision=r.draft.revision}}).catch(e=>toast(e.message))}
        dirty=true;
        updatePendingConflicts();
        const picked=box.querySelector('.dp-confirm .sum b');
        if(picked)picked.textContent=choices.size;
        const kpi=box.querySelector('.dp-kpis .dp-kpi:nth-child(4)');
        if(kpi){kpi.classList.remove('ok');kpi.querySelector('b').textContent=choices.size;kpi.querySelector('span').textContent='已勾选'}
        const chip=$('#drawingChip');chip.className='dp-chip todo';chip.textContent='已修改，待重新确认';
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
        const anchor=$('#detail .resultsummary');
        let last=anchor;
        for(const b of issue?.parameterBasis||[]){
            if(b.origin!=='审查端图纸识别')continue;
            const panel=document.createElement('div');panel.className='dp-basis';
            const val=document.createElement('div');val.className='val';
            const tag=document.createElement('span');tag.className='tag';tag.textContent='图纸依据 '+b.ref;
            const lb=document.createElement('b');lb.textContent=b.label+(b.zone?'（'+b.zone+'）':'')+' = ';val.append(tag,lb,document.createTextNode(b.value+' '+(b.unit||'')));
            const link=document.createElement('button');link.className='src';link.type='button';
            link.innerHTML=ICON.img;link.append(document.createTextNode(b.source+' · 查看图纸原文'));link.onclick=()=>source(b.drawingSource);
            panel.append(val,link);
            if(last){last.after(panel);last=panel}
        }
    };
    sync();
})();
