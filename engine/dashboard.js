const $ = id => document.getElementById(id);
const create = (tag, text, cls) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
};
const modes = ['SEARCH', 'CRAWL'];
const tabModes = [...modes, 'LIBRARY', 'CLASSIFY'];
const element = (mode, id) => $(mode === 'CRAWL' ? 'crawl-' + id : id);
const label = mode => mode === 'CRAWL' ? 'Bắt đầu crawl' : 'Tìm kiếm';
let timer = null;
let busy = false;
let trackedJob = null;
let projectOptions = [];

function setupTabs() {
  const form = $('search-form');
  const output = document.querySelector('.output');
  const crawlForm = form.cloneNode(true);
  const crawlOutput = output.cloneNode(true);
  [crawlForm, crawlOutput].forEach(root => {
    [root, ...root.querySelectorAll('[id]')].forEach(node => { if (node.id) node.id = 'crawl-' + node.id; });
    root.querySelectorAll('label[for]').forEach(node => { node.htmlFor = 'crawl-' + node.htmlFor; });
  });
  crawlForm.querySelector('.fields').remove();
  crawlForm.querySelector('h2').textContent = 'Crawl group theo khoảng thời gian';
  crawlForm.querySelector('.date-block .hint').textContent = 'Chọn khoảng ngày cần thu thập · giờ Việt Nam';
  crawlForm.querySelector('.note').textContent = 'Facebook browser · lưu bài viết, bình luận và phản hồi vào kho raw trước, rồi lọc và phân loại. Quét lại cả bài cũ trong danh sách đã biết để tìm bình luận mới. Phạm vi thu thập có giới hạn; xem kho dữ liệu và kết quả phân loại sau khi chạy.';
  elementFrom(crawlForm, 'crawl-submit').textContent = label('CRAWL');
  const sources = create('details', undefined, 'group-list');
  sources.id = 'crawl-sources';
  sources.append(create('summary', 'Group trong watchlist'), create('ul'));
  crawlForm.querySelector('.date-block').before(sources);
  form.querySelector('.note').textContent = 'Google / SerpApi · tìm theo keyword và hashtag. Tự loại tin tuyển dụng, thuê, mua bán, vay nợ và trao đổi hàng hóa có intent rõ ràng.';
  const tabs = create('div', undefined, 'tabs');
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-label', 'Chế độ thu thập');
  const header = document.querySelector('header');
  header.querySelector('h1').textContent = 'Theo dõi phản ánh dự án';
  header.querySelector('p').textContent = 'Thu thập nội dung, tra cứu dữ liệu gốc và đánh giá phản ánh theo từng dự án.';
  header.after(tabs);
  tabModes.forEach(mode => {
    const tab = create('button', mode === 'CLASSIFY' ? 'Phản ánh / phân loại' : mode === 'LIBRARY' ? 'Kho dữ liệu' : mode === 'CRAWL' ? 'Thu thập / lịch crawl' : 'Tìm kiếm Google', 'tab');
    tab.type = 'button';
    tab.id = 'tab-' + mode;
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-controls', 'panel-' + mode);
    tab.onclick = () => switchTab(mode);
    tab.onkeydown = event => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const next = event.key === 'Home' ? tabModes[0] : event.key === 'End' ? tabModes.at(-1) : tabModes[(tabModes.indexOf(mode) + (event.key === 'ArrowRight' ? 1 : tabModes.length - 1)) % tabModes.length];
        switchTab(next);
        $('tab-' + next).focus();
      }
    };
    tabs.append(tab);
    const panel = create('section');
    panel.id = 'panel-' + mode;
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', tab.id);
    if (mode === 'CLASSIFY') panel.append(classificationPanel());
    else if (mode === 'LIBRARY') panel.append(libraryPanel());
    else panel.append(mode === 'SEARCH' ? form : crawlForm, mode === 'SEARCH' ? output : crawlOutput);
    if (mode === 'CRAWL') panel.insertBefore(scheduleForm(), crawlOutput);
    document.querySelector('main').append(panel);
  });
  switchTab('SEARCH');
}
function elementFrom(root, id) { return root.querySelector('#' + id); }
function scheduleForm() {
  const form = create('form', undefined, 'panel schedule-panel'); form.id = 'schedule-form';
  form.append(create('h2', 'Lịch crawl bài viết và bình luận'));
  const fields = create('div', undefined, 'fields');
  const field = (id, title, input) => {
    const wrapper = create('div', undefined, 'field');
    const caption = create('label', title); caption.htmlFor = id;
    input.id = id; wrapper.append(caption, input); fields.append(wrapper); return input;
  };
  [0, 1].forEach(index => {
    ['start', 'end'].forEach(suffix => {
      const input = field('schedule-slot-' + index + '-' + suffix,
        'Khung ' + (index + 1) + (suffix === 'start' ? ' · từ giờ' : ' · đến giờ'), create('input'));
      input.type = 'time'; input.required = true;
      input.value = index === 0 ? (suffix === 'start' ? '05:00' : '08:30') : (suffix === 'start' ? '17:00' : '18:30');
    });
  });
  const interval = field('schedule-interval', 'Lặp mỗi (phút)', create('input'));
  const projectSelect = field('schedule-project_id', 'Dự án của lịch crawl', create('select'));
  const allProjects = create('option', 'Tất cả group đang bật'); allProjects.value = ''; projectSelect.append(allProjects);
  interval.type = 'number'; interval.min = '30'; interval.max = '45'; interval.value = '45'; interval.required = true;
  const actions = create('div', undefined, 'action');
  actions.append(create('div', 'Mỗi ngày theo giờ Việt Nam, mặc định lặp mỗi 45 phút và thêm lượt chốt cuối khung. Thu bài viết, bình luận và trả lời; đọc lại bài cũ để tìm bình luận mới. Lưu dữ liệu gốc vào kho chung trước khi lọc và phân loại. Khoảng cần theo dõi: từ đầu khung đến thời điểm chạy. Ngoài khung giờ không bắt đầu lượt mới; lượt đang chạy được hoàn tất. Cần giữ máy và backend chạy.', 'note'));
  const buttons = create('div', undefined, 'schedule-buttons');
  const save = create('button', 'Bật / cập nhật lịch', 'button'); save.id = 'schedule-enable'; save.type = 'submit';
  const stop = create('button', 'Tắt lịch', 'button secondary'); stop.id = 'schedule-disable'; stop.type = 'button';
  stop.onclick = () => saveSchedule(false);
  buttons.append(save, stop); actions.append(buttons);
  const message = create('div'); message.id = 'schedule-status'; message.setAttribute('role', 'status');
  form.append(fields, actions, message);
  form.onsubmit = event => { event.preventDefault(); saveSchedule(true); };
  return form;
}
function scheduleMessage(text, error = false) {
  $('schedule-status').textContent = text; $('schedule-status').className = error ? 'error' : '';
}
function showSchedule(schedule, initialize = false) {
  if (initialize) {
    $('schedule-project_id').value = schedule.project_id || '';
    $('schedule-interval').value = schedule.interval_min_minutes || 45;
    (schedule.daily_slots || []).slice(0, 2).forEach((slot, index) => {
      $('schedule-slot-' + index + '-start').value = slot.start;
      $('schedule-slot-' + index + '-end').value = slot.end;
    });
  }
  const next = schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString('vi-VN', {timeZone: 'Asia/Ho_Chi_Minh'}) : '';
  const cadence = schedule.window_mode === 'DAILY_SLOTS' ? 'hằng ngày ' + schedule.daily_slots.map(slot => slot.start + '–' + slot.end).join(', ') + '; lặp ' + schedule.interval_min_minutes + '–' + schedule.interval_max_minutes + ' phút' : 'lịch cũ mỗi ' + schedule.interval_minutes + ' phút';
  scheduleMessage((schedule.enabled ? 'Lịch đang bật · ' + cadence + '. Lượt tiếp theo: ' + next : 'Lịch đang tắt.') +
    (schedule.pipeline === 'RAW_V2_THREADS' ? ' Thu bài viết, bình luận, trả lời → lưu kho → lọc → phân loại.' : '') +
    (schedule.error === 'SCHEDULE_WINDOW_ENDED' ? ' Khoảng ngày đã kết thúc.' : schedule.error ? ' Lịch gặp lỗi; kiểm tra nguồn và cấu hình.' : '') +
    (schedule.active_job ? ' Một lượt thu thập đang chạy.' : ''), Boolean(schedule.error && schedule.error !== 'SCHEDULE_WINDOW_ENDED'));
  $('schedule-disable').disabled = !schedule.enabled;
  if (schedule.active_job && trackedJob !== schedule.active_job.job_id) {
    const job = schedule.active_job; trackedJob = job.job_id; setBusy(true, job.mode || 'CRAWL');
    status(job.mode || 'CRAWL', 'Đang thu thập theo lịch hoặc lượt đang chạy…'); poll(job.job_id, job.mode || 'CRAWL');
  }
}
async function saveSchedule(enabled) {
  const payload = {enabled};
  if (enabled) Object.assign(payload, {
    project_id: $('schedule-project_id').value,
    window_mode: 'DAILY_SLOTS', interval_min_minutes: Number($('schedule-interval').value),
    interval_max_minutes: Number($('schedule-interval').value),
    daily_slots: [0, 1].map(index => ({start: $('schedule-slot-' + index + '-start').value, end: $('schedule-slot-' + index + '-end').value})),
  });
  $('schedule-enable').disabled = $('schedule-disable').disabled = true;
  try {
    const response = await fetch('/api/schedule', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    const schedule = await response.json(); if (!response.ok) throw Error(schedule.error || 'Không cập nhật được lịch.');
    showSchedule(schedule, true);
    if (!enabled) scheduleMessage('Đã tắt lịch. Lượt đang chạy sẽ hoàn tất; không bắt đầu lượt tiếp theo.');
  } catch (error) { scheduleMessage(error.message, true); $('schedule-disable').disabled = false; }
  finally { $('schedule-enable').disabled = false; }
}
async function refreshSchedule(initialize = false) {
  try {
    const response = await fetch('/api/schedule'); if (!response.ok) throw Error();
    showSchedule(await response.json(), initialize);
  } catch { scheduleMessage('Chưa đọc được trạng thái lịch crawl.', true); }
}
function switchTab(mode) {
  clearTimeout(classificationRefreshTimer);
  clearTimeout(classificationDebounce);
  if(mode!=='CLASSIFY'&&classificationFetchController)classificationFetchController.abort();
  tabModes.forEach(value => {
    $('panel-' + value).hidden = value !== mode;
    $('tab-' + value).setAttribute('aria-selected', String(value === mode));
    $('tab-' + value).tabIndex = value === mode ? 0 : -1;
  });
  const selectedTab=$('tab-'+mode),tabStrip=selectedTab.parentElement;
  const tabRect=selectedTab.getBoundingClientRect(),stripRect=tabStrip.getBoundingClientRect();
  if(tabRect.left<stripRect.left)tabStrip.scrollLeft-=stripRect.left-tabRect.left;
  else if(tabRect.right>stripRect.right)tabStrip.scrollLeft+=tabRect.right-stripRect.right;
  if (mode === 'LIBRARY') loadLibrary();
  if (mode === 'CLASSIFY') loadClassifications();
}
function terms(value) { return [...new Set(value.split(',').map(text => text.trim()).filter(Boolean))]; }
function status(mode, message, error = false) {
  element(mode, 'status').textContent = message;
  element(mode, 'status').className = error ? 'error' : '';
}
function setBusy(value, activeMode) {
  busy = value;
  modes.forEach(mode => {
    element(mode, 'submit').disabled = value;
    element(mode, 'submit').textContent = value && mode === activeMode ? 'Đang chạy…' : label(mode);
  });
}
function suggest(values, inputId, listId, chipsId) {
  values.forEach(value => {
    const option = create('option'); option.value = value; $(listId).append(option);
    const chip = create('button', value); chip.type = 'button';
    chip.onclick = () => {
      const existing = terms($(inputId).value);
      if (!existing.includes(value) && existing.length < 3) existing.push(value);
      $(inputId).value = existing.join(', ');
    };
    $(chipsId).append(chip);
  });
}
function render(mode, rows) {
  const body = element(mode, 'rows'); body.replaceChildren();
  element(mode, 'count').textContent = rows.length + ' kết quả';
  if (!rows.length) {
    const cell = create('td', undefined, 'empty'); cell.colSpan = 5;
    cell.append(create('strong', 'Chưa có kết quả đã xác minh thời gian đăng'), create('span', 'Link thiếu thời gian đăng hoặc ngoài khoảng ngày không được hiển thị ở đây.'));
    const row = create('tr'); row.append(cell); body.append(row); return;
  }
  rows.forEach(item => {
    const row = create('tr'), linkCell = create('td');
    try {
      const url = new URL(item.url);
      if (url.protocol !== 'https:' || !['facebook.com', 'fb.watch', 'tiktok.com', 'youtube.com', 'youtu.be'].some(domain => url.hostname === domain || url.hostname.endsWith('.' + domain))) return;
      const link = create('a', item.title || 'Mở link ↗');
      link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
      linkCell.append(link, create('div', item.platform + ' · ' + new Date(item.published_at).toLocaleString('vi-VN', {timeZone: 'Asia/Ho_Chi_Minh'}), 'sub'));
    } catch { return; }
    const groupCell = create('td');
    if (item.group_url) {
      try {
        const url = new URL(item.group_url);
        if (url.protocol === 'https:' && ['facebook.com', 'www.facebook.com'].includes(url.hostname) && /^\/groups\/[^/]+\/?$/.test(url.pathname)) {
          const link = create('a', item.group || url.pathname.split('/')[2]);
          link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; groupCell.append(link);
        }
      } catch {}
    }
    if (!groupCell.childNodes.length) groupCell.append(create('span', '—', 'dash'));
    row.append(linkCell, groupCell);
    [item.project, item.summary, item.issue].forEach(value => row.append(create('td', typeof value === 'string' && value ? value : '—', value ? '' : 'dash')));
    body.append(row);
  });
}
const errors = {
  SERPAPI_NETWORK_ERROR: 'Một truy vấn Google bị timeout.', SERPAPI_INVALID_KEY: 'API key Google không hợp lệ.',
  SERPAPI_PROVIDER_QUOTA: 'Tài khoản đã hết quota Google.', LOCAL_REQUEST_QUOTA: 'Đã đạt ngân sách request.',
  SEARCH_FAILED: 'Lượt thu thập gặp lỗi.', SERPAPI_RATE_LIMIT: 'Google đang giới hạn lượt tìm kiếm.',
  LOGIN_REQUIRED: 'Facebook yêu cầu đăng nhập.', SESSION_EXPIRED: 'Phiên Facebook hết hạn.',
  CAPTCHA: 'Facebook yêu cầu xác minh CAPTCHA.', PROFILE_IN_USE: 'Profile Facebook đang được sử dụng.',
};
async function poll(id, mode) {
  try {
    const response = await fetch('/api/jobs/' + id);
    if (!response.ok) throw Error();
    const job = await response.json();
    if (job.status === 'RUNNING') { timer = setTimeout(() => poll(id, mode), 1500); return; }
    render(mode, job.rows || []);
    const warnings = [...new Set(job.warnings || [])].map(code => errors[code] || 'Một nguồn chưa trả được kết quả.');
    status(mode, 'Đã thu được ' + (job.rows || []).length + ' kết quả đúng khoảng ngày; loại ' + (job.dropped || 0) + ' theo rule. ' + (job.pending_verification || 0) + ' mục chưa xác minh thời gian đăng.' +
      (job.coverage_limited ? ' Lượt này chưa xác nhận đã thu hết nội dung trong khoảng ngày.' : '') + (warnings.length ? ' ' + warnings.join(' ') : ''), job.status === 'FAILED');
    if (mode === 'CRAWL') {
      status(mode, (job.rows || []).length + ' nội dung xác minh trong khoảng ngày. Dữ liệu gốc đã lưu; xem tab Kho dữ liệu và Kết quả phân loại. Chưa xác nhận thu hết bình luận.' + (warnings.length ? ' ' + warnings.join(' ') : ''), job.status === 'FAILED');
    }
    trackedJob = null; setBusy(false);
  } catch {
    trackedJob = null; status(mode, 'Mất kết nối với lượt thu thập. Tải lại trang để theo dõi lại.', true); setBusy(false);
  }
}
async function submit(mode, event) {
  event.preventDefault();
  if (busy) return;
  const payload = {start_date: element(mode, 'start').value, end_date: element(mode, 'end').value};
  payload.project_id = element(mode, 'project_id').value;
  if (mode === 'SEARCH') {
    payload.keywords = terms($('keywords').value); payload.hashtags = terms($('hashtags').value);
    if ((!payload.keywords.length && !payload.hashtags.length) || payload.keywords.length > 3 || payload.hashtags.length > 3) {
      status(mode, 'Nhập 1–3 keyword hoặc 1–3 hashtag.', true); return;
    }
  }
  if (payload.start_date > payload.end_date) { status(mode, 'Ngày bắt đầu phải trước ngày kết thúc.', true); return; }
  setBusy(true, mode); status(mode, 'Đang thu thập theo khoảng ngày bạn chọn…'); clearTimeout(timer);
  try {
    const response = await fetch(mode === 'CRAWL' ? '/api/crawl' : '/api/search', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    const job = await response.json();
    if (response.status === 409 && job.code === 'SEARCH_RUNNING' && job.job_id) {
      const activeMode = modes.includes(job.mode) ? job.mode : mode;
      trackedJob = job.job_id; switchTab(activeMode); setBusy(true, activeMode); status(activeMode, job.error); poll(job.job_id, activeMode); return;
    }
    if (!response.ok) throw Error(job.error || 'Chưa thể chạy thu thập.');
    trackedJob = job.job_id; status(mode, 'Đang chạy ' + job.source_count + ' nguồn theo khoảng ngày bạn chọn…'); poll(job.job_id, mode);
  } catch (error) { status(mode, error.message, true); setBusy(false); }
}
async function options() {
  try {
    const response = await fetch('/api/options'); if (!response.ok) throw Error();
    const data = await response.json();
    projectOptions = data.projects || [];
    [element('SEARCH', 'project_id'), element('CRAWL', 'project_id'), $('library-project_id'), $('schedule-project_id')].forEach(select => {
      projectOptions.forEach(project => { const option = create('option', project.name); option.value = project.project_id; select.append(option); });
    });
    modes.forEach(mode => {
      element(mode, 'project_id').nextElementSibling.textContent = 'Lọc theo tên/bí danh trong bài hoặc group đã gắn dự án. Dữ liệu chỉ suy từ group được ghi “chưa xác nhận”.';
      element(mode, 'project_id').onchange = () => {
        const project = projectOptions.find(p => p.project_id === element(mode, 'project_id').value);
        render(mode, []);
        if (mode === 'SEARCH') {
          $('keywords').value = project ? project.discovery_terms[0] : (data.keywords[0] || '');
          $('hashtags').value = '';
          $('keyword-list').replaceChildren(); $('keyword-chips').replaceChildren();
          $('hashtag-list').replaceChildren(); $('hashtag-chips').replaceChildren();
          suggest(project ? project.discovery_terms : data.keywords, 'keywords', 'keyword-list', 'keyword-chips');
          suggest(project ? project.hashtags : data.hashtags, 'hashtags', 'hashtag-list', 'hashtag-chips');
          status(mode, project ? 'Đã chọn ' + project.name + '. Bấm Tìm kiếm để chạy truy vấn cho dự án.' : 'Đã chuyển về truy vấn tự nhập.');
        } else {
          const groups = (data.groups || []).filter(g => !project || project.source_ids.includes(g.source_id));
          const details = $('crawl-sources');
          details.querySelector('summary').textContent = groups.filter(g => g.ready).length + '/' + groups.length + ' group đang sẵn sàng';
          details.querySelector('ul').replaceChildren(); groups.forEach(g => details.querySelector('ul').append(create('li', g.name + (g.ready ? '' : ' · chưa sẵn sàng'))));
          status(mode, project && !project.source_ids.length ? 'Dự án chưa có group được duyệt để crawl. Có thể dùng tab Tìm kiếm trước.' : 'Bấm Bắt đầu crawl để chạy các group thuộc phạm vi đã chọn.');
        }
      };
    });
    modes.forEach(mode => {
      element(mode, 'start').value = element(mode, 'end').value = data.today;
      element(mode, 'start').max = element(mode, 'end').max = data.today;
    });
    $('keywords').value = data.keywords[0] || '';
    suggest(data.keywords, 'keywords', 'keyword-list', 'keyword-chips');
    suggest(data.hashtags, 'hashtags', 'hashtag-list', 'hashtag-chips');
    const groups = data.groups || [], ready = groups.filter(group => group.ready);
    const details = $('crawl-sources'); details.querySelector('summary').textContent = ready.length + '/' + groups.length + ' group đang sẵn sàng';
    groups.forEach(group => details.querySelector('ul').append(create('li', group.name + (group.ready ? '' : ' · chưa sẵn sàng'))));
    await Promise.all(['SEARCH'].map(async mode => {
      const params = {mode, start_date: data.today, end_date: data.today};
      if (mode === 'SEARCH') params.keywords = $('keywords').value;
      const response = await fetch('/api/results?' + new URLSearchParams(params));
      if (response.ok) { const output = await response.json(); render(mode, output.rows || []); status(mode, 'Đang hiển thị dữ liệu đã lưu. Bấm ' + label(mode) + ' để thu thập lại.'); }
    }));
    const activeResponse = await fetch('/api/jobs/active');
    if (activeResponse.ok) {
      const {job} = await activeResponse.json();
      if (job) { const mode = job.mode || 'SEARCH'; trackedJob = job.job_id; setBusy(true, mode); status(mode, 'Đang tiếp tục theo dõi lượt thu thập…'); poll(job.job_id, mode); }
    }
    await refreshSchedule(true);
    setInterval(() => refreshSchedule(), 5000);
  } catch { modes.forEach(mode => status(mode, 'Chưa đọc được cấu hình. Vui lòng tải lại trang.', true)); setBusy(true); }
}
const reviewLabels = {UNREVIEWED: 'Chưa đánh giá', RELEVANT: 'Liên quan', IRRELEVANT: 'Không liên quan', NEEDS_REVIEW: 'Cần xem xét'};
let libraryPage = 1;
let libraryDebounce = null;
function libraryPanel() {
  const panel = create('div', undefined, 'panel');
  panel.append(create('h2', 'Kho dữ liệu gốc'), create('p', 'Tra cứu bài viết, bình luận và trả lời đã lưu trước lọc. Nội dung bị loại vẫn giữ để đối chiếu. Đánh giá và ghi chú được lưu qua các lượt crawl; xem tab Phản ánh / phân loại để tra cứu kết quả model.', 'note'));
  const form = create('form'); form.id = 'library-form';
  const fields = create('div', undefined, 'fields library-controls');
  function field(id, title, type, choices) {
    const box = create('div', undefined, 'field'), label = create('label', title);
    label.htmlFor = 'library-' + id;
    const input = create(choices ? 'select' : 'input'); input.id = label.htmlFor;
    if (choices) Object.entries(choices).forEach(([value, text]) => { const opt = create('option', text); opt.value = value; input.append(opt); });
    else input.type = type || 'text';
    input.onchange=()=>{libraryPage=1;loadLibrary();};
    if(!choices&&input.type==='text')input.oninput=()=>{clearTimeout(libraryDebounce);libraryDebounce=setTimeout(()=>{libraryPage=1;loadLibrary();},300);};
    box.append(label, input); fields.append(box);
  }
  field('keyword', 'Tìm trong nội dung / tên group');
  field('source_id', 'Group / nguồn', null, {'': 'Tất cả nguồn'});
  field('project_id', 'Dự án theo nguồn / dấu hiệu', null, {'': 'Tất cả dự án', '__unknown__': 'Chưa xác định dự án'});
  field('platform', 'Nền tảng', null, {'': 'Tất cả', facebook: 'Facebook', tiktok: 'TikTok', youtube: 'YouTube'});
  field('review', 'Đánh giá', null, {'': 'Tất cả', ...reviewLabels});
  field('node_type', 'Loại nội dung', null, {'':'Tất cả',POST:'Bài viết',COMMENT:'Bình luận',REPLY:'Trả lời'});
  field('date_basis', 'Lọc theo ngày', null, {collected_at: 'Ngày thu thập', published_at: 'Ngày đăng đã xác minh'});
  field('start_date', 'Từ ngày (giờ Việt Nam)', 'date'); field('end_date', 'Đến ngày (để trống = tất cả)', 'date');
  field('run_id', 'Lượt crawl', null, {'': 'Tất cả lượt'});
  const refresh = create('button', 'Lọc / làm mới', 'button'); refresh.type = 'submit';
  const exportButton = create('button', 'Xuất Excel', 'button secondary'); exportButton.type = 'button'; exportButton.id = 'library-export'; exportButton.onclick = exportLibrary;
  const actions = create('div', undefined, 'schedule-buttons'); actions.append(refresh, exportButton);
  const advanced=create('details',undefined,'advanced-filters');advanced.append(create('summary','Bộ lọc nâng cao'));
  const advancedFields=create('div',undefined,'fields library-controls');
  ['platform','run_id'].forEach(id=>advancedFields.append(fields.querySelector('#library-'+id).parentElement));
  advanced.append(advancedFields);
  const reset=create('button','Xóa bộ lọc','button secondary');reset.type='button';reset.onclick=()=>{form.querySelectorAll('input,select').forEach(input=>input.value=input.id==='library-date_basis'?'collected_at':'');libraryPage=1;loadLibrary();};actions.append(reset);
  form.append(fields, advanced, actions); form.onsubmit = event => { event.preventDefault(); libraryPage = 1; loadLibrary(); };
  const status = create('p'); status.id = 'library-status'; status.setAttribute('role', 'status');
  const exportStatus = create('p'); exportStatus.id = 'library-export-status'; exportStatus.setAttribute('role', 'status');
  const wrap = create('div', undefined, 'table-wrap library-table-wrap');
  wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', 'Bảng kho dữ liệu, cuộn ngang để xem các cột');
  const table = create('table', undefined, 'library-table');
  const caption = create('caption', 'Nội dung đã crawl qua các lượt thu thập');
  const head = create('thead'), headings = create('tr');
  ['STT', 'Link URL / nền tảng', 'Group / nguồn', 'Nội dung', 'Ngày đăng', 'Thu thập gần nhất', 'Lịch sử crawl', 'Đánh giá', 'Ghi chú', 'Dự án'].forEach(title => {
    const cell = create('th', title); cell.scope = 'col'; headings.append(cell);
  });
  head.append(headings);
  const rows = create('tbody'); rows.id = 'library-rows';
  table.append(caption, head, rows); wrap.append(table);
  const pages = create('div', undefined, 'schedule-buttons');
  ['prev', 'next'].forEach((name, index) => {
    const button = create('button', index ? 'Trang sau' : 'Trang trước', 'button secondary'); button.type = 'button'; button.id = 'library-' + name;
    button.onclick = () => { libraryPage += index ? 1 : -1; loadLibrary(); }; pages.append(button);
  });
  panel.append(form, status, exportStatus, create('p', 'Mỗi hàng là một bài viết, bình luận hoặc phản hồi. Lọc ngày đăng dùng thời gian riêng của từng nội dung; thiếu thời gian vẫn xem được khi bỏ lọc ngày. Excel xuất tất cả trang theo bộ lọc hiện tại.', 'hint'), wrap, pages); return panel;
}
function safeLibraryLink(url, title) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:' || !['facebook.com', 'tiktok.com', 'youtube.com', 'youtu.be', 'fb.watch'].some(domain => parsed.hostname === domain || parsed.hostname.endsWith('.' + domain))) return create('span', title || 'URL không hợp lệ');
    const link = create('a', title || parsed.href); link.href = parsed.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; return link;
  } catch { return create('span', title || 'Thiếu URL'); }
}
function libraryDate(value) { return value ? new Date(value).toLocaleString('vi-VN', {timeZone: 'Asia/Ho_Chi_Minh'}) : 'Chưa xác định'; }
function libraryFilters() {
  const params = new URLSearchParams();
  ['keyword', 'source_id', 'project_id', 'platform', 'review', 'node_type', 'date_basis', 'start_date', 'end_date', 'run_id'].forEach(key => { if ($('library-' + key).value) params.set(key, $('library-' + key).value); });
  return params;
}
async function exportLibrary() {
  const button = $('library-export'); button.disabled = true;
  $('library-export-status').textContent = 'Đang tạo file Excel…';
  try {
    const response = await fetch('/api/library/export.xlsx?' + libraryFilters());
    if (!response.ok) { const error = await response.json(); throw Error(error.error || 'Không xuất được Excel.'); }
    const blob = await response.blob(), url = URL.createObjectURL(blob);
    const link = create('a'); link.href = url;
    const filename = (response.headers.get('Content-Disposition') || '').match(/filename="([a-zA-Z0-9_.-]+)"/);
    link.download = filename ? filename[1] : 'vincons-library.xlsx';
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    $('library-export-status').textContent = 'Đã xuất Excel theo bộ lọc hiện tại, gồm tất cả trang và đánh giá/ghi chú đã lưu.';
  } catch (error) { $('library-export-status').textContent = error.message; }
  finally { button.disabled = false; }
}
let libraryLoadSequence=0;
async function loadLibrary() {
  clearTimeout(libraryDebounce);
  const sequence=++libraryLoadSequence;
  const start=$('library-start_date').value,end=$('library-end_date').value,invalid=Boolean(start&&end&&start>end);
  ['start_date','end_date'].forEach(id=>{$('library-'+id).setAttribute('aria-invalid',String(invalid));$('library-'+id).setAttribute('aria-describedby','library-status');});
  $('library-prev').disabled=$('library-next').disabled=true;
  if(invalid){$('library-status').textContent='Ngày bắt đầu phải trước hoặc bằng ngày kết thúc. Kết quả bên dưới thuộc bộ lọc trước đó.';$('library-rows').setAttribute('aria-busy','false');return;}
  const params = libraryFilters(); params.set('page', libraryPage);
  $('library-rows').setAttribute('aria-busy','true');
  $('library-status').textContent = 'Đang đọc dữ liệu đã lưu…';
  try {
    const response = await fetch('/api/library?' + params); const data = await response.json();
    if(sequence!==libraryLoadSequence)return;
    if (!response.ok) throw Error(data.error || 'Không đọc được kho dữ liệu.');
    [['source_id', data.sources.map(source => [source.source_id, source.name])], ['run_id', data.runs.map(run => [run, run])]].forEach(([id, values]) => {
      const select = $('library-' + id), selected = select.value;
      select.replaceChildren(); [['', id === 'run_id' ? 'Tất cả lượt' : 'Tất cả nguồn'], ...values].forEach(([value, title]) => { const option = create('option', title); option.value = value; select.append(option); }); select.value = selected;
    });
    $('library-status').textContent = data.total + ' bản ghi · trang ' + data.page + '/' + Math.max(1, Math.ceil(data.total / data.page_size));
    libraryPage=data.page;
    $('library-prev').disabled = data.page <= 1; $('library-next').disabled = data.page * data.page_size >= data.total;
    const rows = $('library-rows'); rows.replaceChildren();
    if (!data.rows.length) {
      const row = create('tr'), cell = create('td', 'Chưa có bản ghi phù hợp bộ lọc.', 'empty'); cell.colSpan = 10; row.append(cell); rows.append(row);
    }
    data.rows.forEach((item, index) => {
      const row = create('tr'); row.dataset.recordId = item.record_id;
      const number = create('td', String((data.page - 1) * data.page_size + index + 1));
      const link = create('td'); link.append(safeLibraryLink(item.url, item.node_type ? 'Mở link URL' : item.title || 'Mở link URL'), create('div', (item.platform || '') + ' · ' + ({POST:'Bài viết',COMMENT:'Bình luận',REPLY:'Trả lời'}[item.node_type] || '') + (item.pipeline === 'HISTORICAL_V1' ? ' · Dữ liệu cũ' : ''), 'sub'));
      const group = create('td'); group.append(safeLibraryLink(item.group_url, item.group || 'Chưa xác định'));
      const contentCell = create('td');
      const preview = create('p', item.text ? item.text.slice(0, 180) + (item.text.length > 180 ? '…' : '') : 'Chưa lấy được nội dung đầy đủ.', 'library-preview'); contentCell.append(preview);
      const published = create('td', libraryDate(item.published_at));
      if (item.publication_precision !== 'INSTANT') published.append(create('div', 'Chưa xác minh chính xác', 'sub'));
      const collected = create('td', libraryDate(item.collected_at));
      const content = create('details'); content.append(create('summary', 'Xem nội dung đã thu thập'));
      const text = create('p', item.text || 'Chưa lấy được nội dung đầy đủ.'); text.style.whiteSpace = 'pre-wrap'; text.style.overflowWrap = 'anywhere'; content.append(text); contentCell.append(content);
      const lineage = create('details'); lineage.append(create('summary', item.observation_count + ' lần ghi nhận · ' + item.run_ids.length + ' lượt crawl'));
      lineage.append(create('p', 'Nội dung: ' + ({COMPLETE:'Đã trích xuất',PARTIAL:'Đã trích xuất một phần',FAILED:'Chưa trích xuất được',REFERENCE_ONLY:'Chỉ có thông tin tham chiếu'}[item.extraction_status] || 'Chưa xác định') + ' · ' + (item.missing_data_reasons || []).length + ' thông tin còn thiếu'), create('p', item.run_ids.join('\n')));
      const history = create('td'); history.append(lineage);
      const review = create('form'), label = create('label', 'Đánh giá '), select = create('select'); review.id = 'library-review-' + item.record_id;
      Object.entries(reviewLabels).forEach(([value, title]) => { const option = create('option', title); option.value = value; select.append(option); }); select.value = item.review.status; label.append(select);
      const noteLabel = create('label', 'Ghi chú '), note = create('textarea'); note.setAttribute('form', review.id); note.value = item.review.note; note.maxLength = 2000; note.rows = 3; note.style.width = '100%'; noteLabel.append(note);
      const save = create('button', 'Lưu đánh giá', 'button'); save.type = 'submit'; const message = create('p'); message.setAttribute('role', 'status');
      message.textContent = item.review.updated_at ? 'Đã lưu: ' + libraryDate(item.review.updated_at) : '';
      review.append(label, save, message); review.onsubmit = async event => {
        event.preventDefault(); save.disabled = true;
        try {
          const response = await fetch('/api/library/review', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({record_id: item.record_id, status: select.value, note: note.value})});
          const result = await response.json(); if (!response.ok) throw Error(result.error || 'Không lưu được đánh giá.');
          message.textContent = 'Đã lưu: ' + libraryDate(result.updated_at);
        } catch (error) { message.textContent = error.message; }
        finally { save.disabled = false; }
      }; const reviewCell = create('td'); reviewCell.append(review);
      const notesCell = create('td'); notesCell.append(noteLabel);
      row.append(number, link, group, contentCell, published, collected, history, reviewCell, notesCell,
        create('td', item.project || 'Chưa xác định dự án')); rows.append(row);
    });
  } catch (error) { if(sequence===libraryLoadSequence)$('library-status').textContent='Chưa đọc được kho dữ liệu. Bấm Lọc / làm mới để thử lại. Kết quả bên dưới là dữ liệu đã đọc trước đó.'; }
  finally{if(sequence===libraryLoadSequence)$('library-rows').setAttribute('aria-busy','false');}
}
const intentLabels={ADVERTISING:'Quảng cáo',SALES:'Bán hàng',RECRUITMENT:'Tuyển dụng',RENTAL:'Thuê',BUY_SELL:'Mua bán',LOAN_DEBT:'Vay nợ',GOODS_EXCHANGE:'Đổi hàng',COMPLAINT:'Phản ánh',INFORMATIONAL:'Thông tin',UNKNOWN:'Chưa rõ'};
setupTabs();
modes.forEach(mode => element(mode, 'search-form').addEventListener('submit', event => submit(mode, event)));
options();
