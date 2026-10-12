// Saved results: local controls, bounded server pages, no model calls on filtering.
let classificationPage = 1;
let classificationFetchController = null;
let classificationRefreshTimer = null;
let classificationDebounce = null;
let classificationIssues = [];
const classificationFilterLabels = {'node-type':'Loại',group:'Group',project:'Dự án',issue:'Vấn đề',keyword:'Nội dung','start-date':'Từ ngày','end-date':'Đến ngày','time-status':'Thời gian đăng',filter:'Kết quả',intent:'Mục đích','date-basis':'Thời gian',processing:'Xử lý'};
const classificationFilterKeys = {'node-type':'node_type',group:'source_id',project:'project_id',issue:'issue_id',keyword:'keyword','start-date':'start_date','end-date':'end_date','time-status':'time_status',filter:'relevance',intent:'intent','date-basis':'date_basis',processing:'processing_status'};

function classificationIssueOptions() {
  const project=$('classification-project').value,select=$('classification-issue'),saved=select.value;
  select.replaceChildren();
  [['','Tất cả vấn đề'],...classificationIssues.filter(i=>!project||project==='__unknown__'||!i.project_ids||i.project_ids.includes(project)).map(i=>[i.issue_id,i.name])].forEach(([value,text])=>{const option=create('option',text);option.value=value;select.append(option);});
  select.value=[...select.options].some(o=>o.value===saved)?saved:'';
}
function classificationActiveFilters() {
  const chips=$('classification-active-filters');chips.replaceChildren();
  Object.keys(classificationFilterKeys).forEach(id=>{
    const input=$('classification-'+id),value=input.value;
    if(!value||id==='date-basis'&&value==='published_at')return;
    const text=input.tagName==='SELECT'?input.selectedOptions[0]?.textContent:value;
    const button=create('button',classificationFilterLabels[id]+': '+text+' · Bỏ lọc','filter-chip');button.type='button';
    button.onclick=()=>{input.value=id==='date-basis'?'published_at':'';if(id==='project')classificationIssueOptions();classificationPage=1;loadClassifications();};chips.append(button);
  });
  chips.hidden=!chips.childElementCount;
}

function classificationPanel() {
  const panel=create('div',undefined,'panel work-panel');
  panel.append(create('h2','Phản ánh và kết quả phân loại'),create('p','Theo dõi vấn đề theo dự án, group và thời gian. Bài viết, bình luận và trả lời được xét riêng.','note'));
  const presets=create('div',undefined,'filter-presets');presets.setAttribute('aria-label','Lọc nhanh kết quả');
  [['','Tất cả'],['KEEP','Phản ánh phù hợp'],['REVIEW','Cần xem xét'],['UNCLASSIFIED','Chưa phân loại'],['DROP','Đã loại']].forEach(([value,text])=>{
    const button=create('button',text,'preset');button.type='button';button.dataset.filter=value;button.dataset.label=text;button.setAttribute('aria-pressed','false');
    button.onclick=()=>{$('classification-filter').value=value;classificationPage=1;loadClassifications();};presets.append(button);
  });presets.id='classification-presets';panel.append(presets);
  const main=create('div',undefined,'fields classification-controls');
  const advanced=create('details',undefined,'advanced-filters');advanced.append(create('summary','Bộ lọc nâng cao'));
  const extra=create('div',undefined,'fields classification-controls');advanced.append(extra);
  const field=(id,title,choices,type,target=main)=>{
    const box=create('div',undefined,'field'),label=create('label',title),input=create(choices?'select':'input');
    input.id='classification-'+id;label.htmlFor=input.id;
    if(choices)choices.forEach(([value,text])=>{const option=create('option',text);option.value=value;input.append(option);});else input.type=type||'text';
    input.onchange=()=>{if(id==='project')classificationIssueOptions();classificationPage=1;loadClassifications();};
    if(input.type==='text')input.oninput=()=>{clearTimeout(classificationDebounce);classificationDebounce=setTimeout(()=>{classificationPage=1;loadClassifications();},300);};
    box.append(label,input);target.append(box);return input;
  };
  field('keyword','Tìm trong nội dung').placeholder='Nhập từ khóa, có dấu hoặc không dấu';
  field('project','Dự án đã phân loại',[['','Tất cả dự án'],['__unknown__','Chưa xác định']]);
  field('group','Group',[['','Tất cả group']]);
  field('issue','Vấn đề',[['','Tất cả vấn đề']]);
  field('node-type','Loại nội dung',[['','Tất cả'],['POST','Bài viết'],['COMMENT','Bình luận'],['REPLY','Trả lời']]);
  field('date-basis','Thời gian để lọc',[['published_at','Ngày đăng đã xác minh'],['collected_at','Lần thu thập gần nhất']]);
  field('start-date','Từ ngày',null,'date');field('end-date','Đến ngày',null,'date');
  field('filter','Kết quả phân loại',[['','Tất cả'],['KEEP','Phản ánh phù hợp'],['REVIEW','Cần xem xét'],['DROP','Đã loại'],['UNCLASSIFIED','Chưa phân loại']],null,extra);
  field('intent','Mục đích nội dung',[['','Tất cả'],...Object.entries(intentLabels)],null,extra);
  field('time-status','Thời gian đăng',[['','Tất cả'],['INSTANT','Đã xác minh'],['UNKNOWN','Chưa xác minh']],null,extra);
  field('processing','Trạng thái xử lý',[['','Tất cả'],['PENDING','Chờ xử lý'],['RUNNING','Đang xử lý'],['FAILED','Phân loại lỗi'],['UNCLASSIFIED','Chưa có kết quả'],['DONE','Đã phân loại'],['FILTER_DROP','Bị loại bởi bộ lọc'],['STALE','Chờ phiên bản mới'],['OVERSIZED','Nội dung quá dài']],null,extra);
  const dates=create('div',undefined,'date-shortcuts');dates.append(create('span','Khoảng nhanh:'));
  [[1,'Hôm nay'],[7,'7 ngày'],[14,'14 ngày'],[0,'Mọi ngày']].forEach(([days,text])=>{
    const button=create('button',text,'button secondary compact');button.type='button';button.onclick=()=>{
      const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
      const values=Object.fromEntries(parts.map(p=>[p.type,p.value]));const end=values.year+'-'+values.month+'-'+values.day;
      const first=new Date(end+'T12:00:00Z');first.setUTCDate(first.getUTCDate()-Math.max(0,days-1));
      $('classification-start-date').value=days?first.toISOString().slice(0,10):'';$('classification-end-date').value=days?end:'';
      classificationPage=1;loadClassifications();
    };dates.append(button);
  });
  panel.append(main,dates,advanced);
  const chips=create('div',undefined,'active-filters');chips.id='classification-active-filters';chips.setAttribute('aria-label','Bộ lọc đang áp dụng');chips.hidden=true;panel.append(chips);
  const actions=create('div',undefined,'action');const left=create('div',undefined,'schedule-buttons');
  const reset=create('button','Xóa bộ lọc','button secondary');reset.type='button';reset.onclick=()=>{
    Object.keys(classificationFilterKeys).forEach(k=>$('classification-'+k).value=k==='date-basis'?'published_at':'');classificationPage=1;loadClassifications();
  };
  const refresh=create('button','Cập nhật dữ liệu','button secondary');refresh.type='button';refresh.onclick=()=>loadClassifications(true);left.append(reset,refresh);
  const run=create('button','Xử lý nội dung chưa phân loại','button');run.id='classification-run';run.type='button';
  run.onclick=async()=>{run.disabled=true;try{const response=await fetch('/api/classifications/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!response.ok)throw Error();await loadClassifications(true);}catch{$('classification-status').textContent='Chưa khởi chạy được phân loại. Bạn có thể thử lại.';run.disabled=false;}};
  actions.append(left,run);panel.append(actions,create('p','Bộ lọc chỉ tra cứu kết quả đã lưu. Nút xử lý bỏ qua nội dung đã phân loại cùng phiên bản.','hint'));
  const monitoring=create('label',undefined,'monitoring-control'),auto=create('input');auto.type='checkbox';auto.checked=true;auto.id='classification-auto-refresh';
  auto.onchange=()=>{clearTimeout(classificationRefreshTimer);if(auto.checked)loadClassifications();};
  monitoring.append(auto,document.createTextNode('Tự cập nhật mỗi 15 giây khi đang xem tab này'));panel.append(monitoring);
  const status=create('p');status.id='classification-status';status.setAttribute('role','status');panel.append(status);
  const wrap=create('div',undefined,'table-wrap');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Bảng kết quả phân loại, có thể cuộn ngang');
  const table=create('table',undefined,'classification-table'),head=create('thead'),tr=create('tr');
  ['Link URL / loại','Group','Ngày đăng','Nội dung','Mục đích','Kết quả','Dự án / vấn đề'].forEach(label=>{const th=create('th',label);th.scope='col';tr.append(th);});head.append(tr);
  const body=create('tbody');body.id='classification-rows';table.append(head,body);wrap.append(table);panel.append(wrap);
  const pages=create('nav',undefined,'pagination');pages.setAttribute('aria-label','Phân trang kết quả phân loại');
  ['prev','next'].forEach((key,index)=>{const button=create('button',index?'Trang sau':'Trang trước','button secondary');button.id='classification-'+key;button.type='button';button.onclick=()=>{classificationPage+=index?1:-1;loadClassifications();};pages.append(button);});
  const pageLabel=create('span');pageLabel.id='classification-page';pages.insertBefore(pageLabel,pages.lastChild);panel.append(pages);
  panel.append(create('p','Giờ Việt Nam. Lọc ngày đăng dùng thời gian riêng của từng nội dung và bỏ qua các mục chưa xác minh thời gian. Chọn ngày thu thập để tra cứu các mục đó.','hint'));return panel;
}

async function loadClassifications(force=false) {
  clearTimeout(classificationRefreshTimer);
  clearTimeout(classificationDebounce);
  if(classificationFetchController)classificationFetchController.abort();
  classificationFetchController=null;
  const start=$('classification-start-date').value,end=$('classification-end-date').value;
  const invalid=Boolean(start&&end&&start>end);
  ['start-date','end-date'].forEach(id=>{$('classification-'+id).setAttribute('aria-invalid',String(invalid));$('classification-'+id).setAttribute('aria-describedby','classification-status');});
  classificationActiveFilters();
  if(invalid){$('classification-status').textContent='Ngày bắt đầu phải trước hoặc bằng ngày kết thúc. Kết quả bên dưới thuộc bộ lọc trước đó.';$('classification-rows').setAttribute('aria-busy','false');$('classification-prev').disabled=$('classification-next').disabled=true;return;}
  const controller=new AbortController();classificationFetchController=controller;
  const params=new URLSearchParams({page:classificationPage,page_size:25});
  Object.entries(classificationFilterKeys).forEach(([id,key])=>{const value=$('classification-'+id).value.trim();if(value)params.set(key,value);});if(force===true)params.set('refresh','1');
  const body=$('classification-rows');body.setAttribute('aria-busy','true');$('classification-status').textContent='Đang đọc kết quả đã lưu…';
  $('classification-prev').disabled=$('classification-next').disabled=true;
  try {
    const response=await fetch('/api/classifications?'+params,{signal:controller.signal});const data=await response.json();if(!response.ok)throw Error(data.error||'Chưa đọc được kết quả.');
    if(controller!==classificationFetchController)return;
    const fill=(id,values)=>{const select=$('classification-'+id),saved=select.value;select.replaceChildren();values.forEach(([value,text])=>{const option=create('option',text);option.value=value;select.append(option);});select.value=saved;};
    fill('group',[['','Tất cả group'],...(data.sources||[]).map(s=>[s.source_id,s.name])]);fill('project',[['','Tất cả dự án'],['__unknown__','Chưa xác định'],...(data.projects||[]).map(p=>[p.project_id,p.name])]);classificationIssues=data.issues||[];classificationIssueOptions();classificationActiveFilters();
    $('classification-presets').querySelectorAll('button').forEach(button=>{const value=button.dataset.filter;const count=value?(data.summary?.[value]||0):Object.values(data.summary||{}).reduce((a,b)=>a+b,0);button.textContent=button.dataset.label+' · '+count;button.setAttribute('aria-pressed',String($('classification-filter').value===value));});
    body.replaceChildren();
    const outcomes={KEEP:'Phản ánh phù hợp',REVIEW:'Cần xem xét',DROP:'Đã loại',PENDING:'Chờ phân loại',RUNNING:'Đang phân loại',FAILED:'Phân loại lỗi',STALE:'Chờ phiên bản mới',OVERSIZED:'Nội dung quá dài',UNCLASSIFIED:'Chưa phân loại'};
    data.rows.forEach(row=>{
      const tr=create('tr'),link=create('td');link.append(safeLibraryLink(row.url,'Mở link URL'),create('div',({POST:'Bài viết',COMMENT:'Bình luận',REPLY:'Trả lời'})[row.node_type]||'Nội dung','sub'));
      const content=create('td'),details=create('details');details.append(create('summary',(row.raw_text||'Chưa lấy được nội dung').slice(0,160)));const text=create('p',row.raw_text||'Chưa lấy được nội dung.');text.className='content-text';details.append(text);content.append(details);
      const result=row.analysis?.relevance||(row.processing_status==='FILTER_DROP'?'DROP':row.processing_status),outcome=create('td');outcome.append(create('span',outcomes[result]||'Chưa có kết quả','status-pill status-'+result));
      if(row.reason_vi){const why=create('details');why.append(create('summary','Lý do'),create('p',row.reason_vi));outcome.append(why);}
      const issue=create('td');(row.analysis?.project_matches||[]).forEach(p=>issue.append(create('p',(data.projects||[]).find(x=>x.project_id===p.project_id)?.name||p.project_id)));(row.analysis?.issues||[]).forEach(i=>issue.append(create('p',i.summary)));
      const time=create('td',libraryDate(row.published_at));if(row.publication_precision!=='INSTANT')time.append(create('div','Chưa xác minh','sub'));
      const labels=row.analysis?.content_intents||row.filter_decision?.content_intents||[];
      tr.append(link,create('td',(row.groups||[]).join('\n')),time,content,create('td',labels.map(l=>intentLabels[l]||'Chưa rõ').join(', ')),outcome,issue);body.append(tr);
    });
    if(!data.rows.length){const tr=create('tr'),cell=create('td',undefined,'empty');cell.colSpan=7;cell.append(create('strong','Không có nội dung phù hợp'),create('span','Thử mở rộng khoảng ngày hoặc xóa bộ lọc.'));tr.append(cell);body.append(tr);}
    classificationPage=data.page;$('classification-prev').disabled=data.page<=1;$('classification-next').disabled=data.page*data.page_size>=data.total;
    $('classification-page').textContent='Trang '+data.page+' / '+Math.max(1,Math.ceil(data.total/data.page_size));
    $('classification-status').textContent=data.total.toLocaleString('vi-VN')+' nội dung khớp bộ lọc · hiển thị '+data.rows.length+' nội dung · cập nhật '+new Date().toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})+(data.running?' · đang xử lý nội dung chưa phân loại':'');$('classification-run').disabled=data.running;
  } catch(error){if(error.name==='AbortError'||controller!==classificationFetchController)return;$('classification-status').textContent='Chưa đọc được kết quả. Bấm Cập nhật dữ liệu để thử lại. Kết quả bên dưới là dữ liệu đã đọc trước đó.';}
  finally{if(controller===classificationFetchController){body.setAttribute('aria-busy','false');if(!$('panel-CLASSIFY').hidden&&$('classification-auto-refresh').checked)classificationRefreshTimer=setTimeout(()=>loadClassifications(),15000);}}
}
