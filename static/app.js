function fmtBytes(n) {
  const v = Number(n);
  if (!isFinite(v)) return '—';
  if (v < 1024) return v + ' B';
  const units = ['KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
  let val = v;
  let i = 0;
  while (i < units.length - 1 && val >= 1024) {
    val /= 1024;
    i++;
  }
  return val.toFixed(1) + ' ' + units[i];
}

function stamp(id) {
  document.getElementById(id).textContent = 'refreshed ' + new Date().toTimeString().slice(0, 8);
}

function showError(panel, msg) {
  const el = document.getElementById(panel + '-error');
  el.textContent = 'error: ' + msg;
  el.hidden = false;
}

function clearError(panel) {
  const el = document.getElementById(panel + '-error');
  el.textContent = '';
  el.hidden = true;
}

async function getJSON(url) {
  const r = await fetch(url);
  return r.json();
}

function errMsg(data) {
  return data.error + (data.details ? ' — ' + data.details : '');
}

let runInFlight = false;

async function loadStatus() {
  const panel = 'director';
  try {
    const data = await getJSON('/api/status');
    if (data.error) {
      showError(panel, errMsg(data));
      document.getElementById('director-dot').className = 'dot fail';
      document.getElementById('director-version').textContent = '—';
      return;
    }
    clearError(panel);
    document.getElementById('director-dot').className = 'dot ok';
    document.getElementById('director-version').textContent = data.version;
  } catch (e) {
    showError(panel, 'fetch failed');
    document.getElementById('director-dot').className = 'dot fail';
    document.getElementById('director-version').textContent = '—';
  } finally {
    stamp(panel + '-stamp');
  }
}

async function renderJobs() {
  const panel = 'jobs';
  try {
    const data = await getJSON('/api/jobs');
    if (data.error) {
      showError(panel, errMsg(data));
      return;
    }
    clearError(panel);
    const body = document.getElementById('jobs-body');
    while (body.firstChild) {
      body.removeChild(body.firstChild);
    }
    for (const job of data.jobs || []) {
      const row = document.createElement('div');
      row.className = 'job-row';

      const nameSpan = document.createElement('span');
      nameSpan.className = 'job-name';
      nameSpan.textContent = job.name || '—';
      row.appendChild(nameSpan);

      const badge = document.createElement('span');
      const run = job.last_run;
      const badgeData = run && run.badge ? run.badge : { klass: 'unknown', label: 'never ran' };
      badge.className = 'badge ' + badgeData.klass;
      badge.textContent = badgeData.label;
      row.appendChild(badge);

      const timeSpan = document.createElement('span');
      timeSpan.className = 'job-time';
      timeSpan.textContent = run && run.starttime ? run.starttime : '—';
      row.appendChild(timeSpan);

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'run-btn';
      btn.textContent = 'run';
      const name = job.name || '';
      btn.addEventListener('click', async function (event) {
        const btn = event.currentTarget;
        if (!confirm('Run job ' + name + ' now?')) return;
        if (runInFlight) {
          const feedback = document.getElementById('jobs-feedback');
          feedback.className = 'panel-feedback fail';
          feedback.textContent = 'error: a run is already in progress';
          return;
        }
        runInFlight = true;
        const feedback = document.getElementById('jobs-feedback');
        btn.disabled = true;
        try {
          const r = await fetch('/api/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job: name })
          });
          const respData = await r.json();
          if (respData.error) {
            feedback.className = 'panel-feedback fail';
            feedback.textContent = 'error: ' + respData.error;
          } else {
            feedback.className = 'panel-feedback';
            feedback.textContent = 'queued jobid ' + respData.jobid;
          }
        } catch (err) {
          feedback.className = 'panel-feedback fail';
          feedback.textContent = 'error: fetch failed';
        } finally {
          try {
            await renderJobs();
          } finally {
            runInFlight = false;
            btn.disabled = false;
          }
        }
      });
      row.appendChild(btn);

      body.appendChild(row);
    }
  } catch (e) {
    showError(panel, 'fetch failed');
  } finally {
    stamp(panel + '-stamp');
  }
}

async function loadJobs() {
  if (runInFlight) return;
  await renderJobs();
}

async function loadHistory() {
  const panel = 'history';
  try {
    const data = await getJSON('/api/history?limit=25');
    if (data.error) {
      showError(panel, errMsg(data));
      return;
    }
    clearError(panel);
    const body = document.getElementById('history-body');
    while (body.firstChild) {
      body.removeChild(body.firstChild);
    }
    for (const run of data.runs || []) {
      const tr = document.createElement('tr');

      const cells = [
        run.jobid,
        run.name,
        run.level,
        run.starttime,
        run.jobfiles,
        fmtBytes(run.jobbytes)
      ];
      for (const value of cells) {
        const td = document.createElement('td');
        td.textContent = value !== undefined && value !== null ? value : '—';
        tr.appendChild(td);
      }

      const statusTd = document.createElement('td');
      const badge = document.createElement('span');
      const badgeData = run.badge || { klass: 'unknown', label: '?' };
      badge.className = 'badge ' + badgeData.klass;
      badge.textContent = badgeData.label;
      statusTd.appendChild(badge);
      tr.appendChild(statusTd);

      body.appendChild(tr);
    }
  } catch (e) {
    showError(panel, 'fetch failed');
  } finally {
    stamp(panel + '-stamp');
  }
}

async function loadMedia() {
  const panel = 'media';
  try {
    const data = await getJSON('/api/media');
    if (data.error) {
      showError(panel, errMsg(data));
      return;
    }
    clearError(panel);
    const body = document.getElementById('media-body');
    while (body.firstChild) {
      body.removeChild(body.firstChild);
    }
    for (const row of data.media || []) {
      const tr = document.createElement('tr');

      const values = [
        row.volume,
        row.pool,
        row.status,
        fmtBytes(row.bytes),
        row.lastwritten || '—',
        row.inchanger ? 'yes' : 'no'
      ];
      for (const value of values) {
        const td = document.createElement('td');
        td.textContent = value !== undefined && value !== null ? value : '—';
        tr.appendChild(td);
      }

      body.appendChild(tr);
    }
  } catch (e) {
    showError(panel, 'fetch failed');
  } finally {
    stamp(panel + '-stamp');
  }
}

loadStatus();
loadJobs();
loadHistory();
loadMedia();
setInterval(loadStatus, 15000);
setInterval(loadJobs, 15000);
setInterval(loadHistory, 15000);
setInterval(loadMedia, 60000);
