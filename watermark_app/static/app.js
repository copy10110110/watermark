let currentTasks = { embed: null, extract: null };
const blobUrls = [];

// Tab switching
function switchTab(name) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector(`[onclick="switchTab('${name}')"]`).classList.add('active');
    document.getElementById(`tab-${name}`).classList.add('active');
}

// Embed
async function startEmbed() {
    const files = document.getElementById('embed-files').files;
    if (!files.length) { alert('请选择图片'); return; }
    const text = document.getElementById('embed-text').value;
    const mode = document.getElementById('embed-mode').value;
    const formData = new FormData();
    for (const f of files) formData.append('files', f);
    formData.append('text', text);
    formData.append('mode', mode);
    const resp = await fetch('/api/embed', { method: 'POST', body: formData });
    const task = await resp.json();
    currentTasks.embed = task.task_id;
    showProgress('embed');
    pollTask(task.task_id, 'embed');
}

async function startExtract() {
    const files = document.getElementById('extract-files').files;
    if (!files.length) { alert('请选择图片'); return; }
    const formData = new FormData();
    for (const f of files) formData.append('files', f);
    const resp = await fetch('/api/extract', { method: 'POST', body: formData });
    const task = await resp.json();
    currentTasks.extract = task.task_id;
    showProgress('extract');
    pollTask(task.task_id, 'extract');
}

function showProgress(type) {
    document.getElementById(`${type}-progress`).classList.remove('hidden');
    document.getElementById(`${type}-cancel-btn`).classList.remove('hidden');
    if (type === 'embed') document.getElementById('embed-pause-btn').classList.remove('hidden');
    document.getElementById(`${type}-start-btn`).disabled = true;
}

async function pollTask(taskId, type) {
    const interval = setInterval(async () => {
        try {
            const resp = await fetch(`/api/task/${taskId}/status`);
            const task = await resp.json();
            updateProgress(task, type);
            if (['completed', 'cancelled', 'failed'].includes(task.status)) {
                clearInterval(interval);
                showResults(task, type);
                document.getElementById(`${type}-start-btn`).disabled = false;
            }
        } catch (e) {}
    }, 1000);
}

function updateProgress(task, type) {
    const pct = task.total ? Math.round(task.progress.current / task.total * 100) : 0;
    const fill = document.getElementById(`${type}-progress-fill`);
    if (fill) fill.style.width = pct + '%';
    const statusEl = document.getElementById(`${type}-status-text`);
    if (statusEl) statusEl.textContent = `${task.progress.current}/${task.total} — ${task.status}`;
    const successEl = document.getElementById(`${type}-success-count`);
    const failEl = document.getElementById(`${type}-fail-count`);
    if (successEl) successEl.textContent = task.stats?.success || 0;
    if (failEl) failEl.textContent = task.stats?.failed || 0;
}

function showResults(task, type) {
    const container = document.getElementById(`${type}-results`);
    if (!container) return;
    container.classList.remove('hidden');
    // 添加下载按钮
    let downloadHtml = '';
    if (task.download_url) {
        downloadHtml = `<div style="margin-bottom:12px"><a href="${task.download_url}" class="btn btn-primary" download>📥 下载结果 ZIP</a></div>`;
    }
    if (type === 'extract') {
        let html = '<table class="result-table"><tr><th>文件</th><th>提取文本</th><th>置信度</th><th>AI分数</th><th>判定</th></tr>';
        for (const r of (task.results || [])) {
            const cls = r.success ? 'match' : 'mismatch';
            const verdict = r.verdict || '-';
            const badgeCls = verdict === 'likely_ai' ? 'badge-ai' : verdict === 'likely_real' ? 'badge-real' : 'badge-unknown';
            html += `<tr class="${cls}"><td>${r.filename || '-'}</td><td>${r.text || '—'}</td><td>${r.confidence != null ? (r.confidence*100).toFixed(0)+'%' : '-'}</td><td>${r.ai_score != null ? r.ai_score.toFixed(2) : '-'}</td><td><span class="badge ${badgeCls}">${verdict}</span></td></tr>`;
        }
        html += '</table>';
        document.getElementById('extract-result-table').innerHTML = downloadHtml + html;
    } else {
        let html = '';
        for (const r of (task.results || [])) html += `<div style="color:var(--success)">✅ ${r.output || r.filename || '-'}</div>`;
        for (const e of (task.errors || [])) html += `<div style="color:var(--danger)">❌ ${e.filename} — ${e.error}</div>`;
        document.getElementById(`${type}-result-list`).innerHTML = downloadHtml + html;
    }
}

async function cancelCurrent(type) {
    const taskId = currentTasks[type];
    if (taskId) await fetch(`/api/task/${taskId}/cancel`, { method: 'POST' });
}

async function togglePause(type) {
    const btn = document.getElementById('embed-pause-btn');
    const isPaused = btn.textContent === '继续';
    const taskId = currentTasks[type];
    await fetch(`/api/task/${taskId}/pause?action=${isPaused ? 'resume' : 'pause'}`, { method: 'POST' });
    btn.textContent = isPaused ? '暂停' : '继续';
}

// Blob URL cleanup
const _orig = URL.createObjectURL;
URL.createObjectURL = function(b) { const u = _orig.call(URL, b); blobUrls.push(u); return u; };
window.addEventListener('beforeunload', () => blobUrls.forEach(u => URL.revokeObjectURL(u)));
