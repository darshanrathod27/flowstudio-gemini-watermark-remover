// FlowStudio Pro - Client Application Engine
(function () {
  'use strict';

  // DOM Elements
  const badgeGpu = document.getElementById('badge-gpu');
  const badgeEncoder = document.getElementById('badge-encoder');
  const badgeMasks = document.getElementById('badge-masks');
  const perfModeSelect = document.getElementById('perf-mode-select');
  const btnRefresh = document.getElementById('btn-refresh');

  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const toggleRemoveLogo = document.getElementById('toggle-remove-logo');
  const controlRemoveLogo = document.getElementById('control-remove-logo');
  const upscaleSelect = document.getElementById('upscale-select');
  const selectedSummary = document.getElementById('selected-summary');
  const btnStartBatch = document.getElementById('btn-start-batch');

  const tabCleaner = document.getElementById('tab-cleaner');
  const tabUpscaler = document.getElementById('tab-upscaler');
  const panelTitle = document.getElementById('panel-title');
  const panelDesc = document.getElementById('panel-desc');
  const dropzoneMainText = document.getElementById('dropzone-main-text');

  const jobsTable = document.getElementById('jobs-table');
  const jobsTbody = document.getElementById('jobs-tbody');
  const queueCount = document.getElementById('queue-count');
  const btnStopAll = document.getElementById('btn-stop-all');
  const btnDownloadSelectedZip = document.getElementById('btn-download-selected-zip');
  const btnDownloadAllZip = document.getElementById('btn-download-all-zip');
  const btnClearHistory = document.getElementById('btn-clear-history') || document.getElementById('btn-clear-completed');
  const thSelectAll = document.getElementById('th-select-all');

  // Modal Elements
  const modalCompare = document.getElementById('modal-compare');
  const modalBackdrop = document.getElementById('modal-backdrop');
  const modalClose = document.getElementById('modal-close');
  const modalFilename = document.getElementById('modal-filename');
  const modalMaskInfo = document.getElementById('modal-mask-info');
  const modalModeToggle = document.getElementById('modal-mode-toggle');
  const splitSliderContainer = document.getElementById('split-slider-container');
  const afterLayer = document.getElementById('after-layer');
  const splitDivider = document.getElementById('split-divider');
  const imgBefore = document.getElementById('img-before');
  const imgAfter = document.getElementById('img-after');
  const sideBySideContainer = document.getElementById('side-by-side-container');
  const imgSbsBefore = document.getElementById('img-sbs-before');
  const imgSbsAfter = document.getElementById('img-sbs-after');
  const btnModalDownload = document.getElementById('btn-modal-download');

  // State
  let stagedFiles = [];
  let knownJobs = {};
  let selectedJobIds = new Set();
  let ws = null;
  let wsReconnectDelay = 1000;
  let isSplitDragging = false;
  let currentModalMode = 'split'; // 'split' or 'sbs'

  // --- 1. System Health & Hardware Audit ---
  async function fetchHealth() {
    try {
      const res = await fetch('/api/health');
      if (!res.ok) throw new Error('Health status unavailable');
      const data = await res.json();

      if (data.cuda_available) {
        badgeGpu.className = 'badge badge-gpu';
        badgeGpu.textContent = `⚡ ${data.gpu_name} (${data.vram_gb} GB - ${data.tier})`;
      } else {
        badgeGpu.className = 'badge';
        badgeGpu.textContent = `💻 CPU Universal (${data.cpu_cores} Cores)`;
      }

      badgeEncoder.textContent = `🚀 ${data.video_encoder.toUpperCase()} (${data.encoder_vendor.toUpperCase()})`;
      badgeMasks.textContent = `🛡️ ${data.masks_loaded} Master Masks Calibrated`;

      if (data.perf_mode && perfModeSelect) {
        perfModeSelect.value = data.perf_mode;
      }
      if (data.pools) {
        updatePoolUI(data.pools);
      }
    } catch (e) {
      console.warn('Health fetch error:', e);
      badgeGpu.textContent = '⚡ Engine Standby';
    }
  }

  // --- 2. Perf Mode Update ---
  async function updatePerfMode(newMode) {
    try {
      await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ perf_mode: newMode })
      });
      fetchHealth();
    } catch (e) {
      console.error('Failed to update config:', e);
    }
  }

  // --- 2b. Mode Tab Navigation ---
  if (tabCleaner && tabUpscaler) {
    tabCleaner.addEventListener('click', () => {
      tabCleaner.classList.add('active');
      tabUpscaler.classList.remove('active');
      panelTitle.textContent = 'Batch Media Processing';
      panelDesc.textContent = 'Drag & drop up to 50+ images and videos simultaneously';
      dropzoneMainText.textContent = 'Drag and drop images or videos here';
      toggleRemoveLogo.checked = true;
      controlRemoveLogo.style.display = 'flex';
    });

    tabUpscaler.addEventListener('click', () => {
      tabUpscaler.classList.add('active');
      tabCleaner.classList.remove('active');
      panelTitle.textContent = 'Personal AI Super-Resolution (2K / 4K)';
      panelDesc.textContent = 'Upscale personal videos, anime, home clips, and images with neural AI (Zero watermark logic)';
      dropzoneMainText.textContent = 'Drag and drop any personal videos or images to upscale';
      toggleRemoveLogo.checked = false;
      controlRemoveLogo.style.display = 'none';
      if (upscaleSelect.value === 'off') {
        upscaleSelect.value = '2x_anime';
      }
    });
  }

  // --- 3. Drag & Drop Staging ---
  function updateStagedUI() {
    if (stagedFiles.length === 0) {
      selectedSummary.textContent = 'No files staged';
      btnStartBatch.disabled = true;
    } else {
      let totalBytes = stagedFiles.reduce((acc, f) => acc + f.size, 0);
      let mb = (totalBytes / (1024 * 1024)).toFixed(1);
      selectedSummary.textContent = `${stagedFiles.length} file(s) staged (${mb} MB)`;
      btnStartBatch.disabled = false;
    }
  }

  function handleFiles(files) {
    for (let i = 0; i < files.length; i++) {
      stagedFiles.push(files[i]);
    }
    updateStagedUI();
  }

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer && e.dataTransfer.files) {
      handleFiles(e.dataTransfer.files);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files) {
      handleFiles(e.target.files);
    }
  });

  // --- 4. Batch Upload & Ingestion ---
  async function startBatchUpload() {
    if (stagedFiles.length === 0) return;

    btnStartBatch.disabled = true;
    btnStartBatch.textContent = 'Uploading...';

    const formData = new FormData();
    for (let f of stagedFiles) {
      formData.append('files', f);
    }
    formData.append('upscale_mode', upscaleSelect.value);
    formData.append('remove_logo', toggleRemoveLogo.checked);

    try {
      const res = await fetch('/api/jobs/upload', {
        method: 'POST',
        body: formData
      });
      if (!res.ok) throw new Error('Upload failed');
      const data = await res.json();

      stagedFiles = [];
      fileInput.value = '';
      updateStagedUI();
      fetchJobs();
    } catch (err) {
      alert('Upload failed: ' + err.message);
    } finally {
      btnStartBatch.textContent = 'Start Batch Processing';
      updateStagedUI();
    }
  }

  btnStartBatch.addEventListener('click', startBatchUpload);

  // --- 5. Jobs Queue Rendering ---
  function renderJobs(jobs) {
    if (!jobs || jobs.length === 0) {
      jobsTbody.innerHTML = '<tr class="empty-row"><td colspan="7">No jobs in queue. Stage files above to begin.</td></tr>';
      queueCount.textContent = '0 items';
      btnDownloadAllZip.disabled = true;
      btnDownloadSelectedZip.disabled = true;
      if (btnStopAll) btnStopAll.style.display = 'none';
      return;
    }

    queueCount.textContent = `${jobs.length} items`;
    let hasCompleted = false;
    let anyActive = false;

    // Sort: newest first
    jobs.sort((a, b) => b.created_at - a.created_at);

    let html = '';
    for (let j of jobs) {
      knownJobs[j.id] = j;
      if (j.status === 'completed') hasCompleted = true;
      if (j.status === 'queued' || j.status === 'processing') anyActive = true;

      let isSelected = selectedJobIds.has(j.id);
      let pct = j.progress_pct || 0;
      let statusClass = `status-${j.status}`;
      let isVideo = j.file_type === 'video';
      let typeBadge = isVideo ? '🎬 Video' : '🖼️ Image';

      let maskBadge = `<span class="badge-mask">${j.detected_mask || 'Auto-Detect'}</span>`;
      let upscaleLabel = j.upscale_mode === 'off' ? 'Native' : j.upscale_mode.replace('_', ' ').toUpperCase();

      let speedMeta = '';
      if (j.status === 'processing') {
        if (isVideo && j.total_frames > 0) {
          speedMeta = `Frame ${j.current_frame}/${j.total_frames} • ETA ${j.eta_sec}s`;
        } else {
          speedMeta = 'Processing...';
        }
      } else if (j.status === 'paused') {
        speedMeta = `Paused · Frame ${j.current_frame || 0}/${j.total_frames || 0}`;
        statusClass = 'status-paused';
      } else if (j.status === 'completed') {
        speedMeta = `Finished in ${j.elapsed_sec || 0}s`;
      } else if (j.status === 'cancelled') {
        speedMeta = 'Cancelled by user';
      } else if (j.status === 'failed') {
        speedMeta = j.error ? String(j.error).substring(0, 30) : 'Error';
      }

      let actionsHtml = '';
      if (j.status === 'queued') {
        actionsHtml = `
          <button class="btn btn-warning btn-xs btn-pause" data-id="${j.id}" title="Pause queue">Pause</button>
          <button class="btn btn-danger btn-xs btn-stop" data-id="${j.id}" title="Cancel queue">Cancel</button>
          <button class="btn btn-secondary btn-xs btn-del" data-id="${j.id}" title="Remove">×</button>
        `;
      } else if (j.status === 'processing') {
        actionsHtml = `
          <button class="btn btn-warning btn-xs btn-pause" data-id="${j.id}" title="Pause processing">Pause</button>
          <button class="btn btn-danger btn-xs btn-stop" data-id="${j.id}" title="Cancel job">Cancel</button>
          <button class="btn btn-secondary btn-xs btn-del" data-id="${j.id}" title="Remove">×</button>
        `;
      } else if (j.status === 'paused') {
        actionsHtml = `
          <button class="btn btn-success btn-xs btn-resume" data-id="${j.id}" title="Resume processing">Resume</button>
          <button class="btn btn-danger btn-xs btn-stop" data-id="${j.id}" title="Cancel job">Cancel</button>
          <button class="btn btn-secondary btn-xs btn-del" data-id="${j.id}" title="Remove">×</button>
        `;
      } else if (j.status === 'completed') {
        actionsHtml = `
          <button class="btn btn-secondary btn-xs btn-inspect" data-id="${j.id}">Inspect 4×</button>
          <a class="btn btn-primary btn-xs" href="/api/jobs/${j.id}/download" download>Download</a>
          <button class="btn btn-secondary btn-xs btn-del" data-id="${j.id}" title="Delete">×</button>
        `;
      } else {
        actionsHtml = `
          <button class="btn btn-secondary btn-xs btn-retry" data-id="${j.id}" title="Retry job">Retry</button>
          <button class="btn btn-secondary btn-xs btn-del" data-id="${j.id}" title="Remove">×</button>
        `;
      }

      html += `
        <tr data-id="${j.id}">
          <td>
            <input type="checkbox" class="job-checkbox" data-id="${j.id}" ${isSelected ? 'checked' : ''}>
          </td>
          <td>
            <div class="file-cell">
              <span class="file-name">${escapeHtml(j.filename)}</span>
            </div>
          </td>
          <td><span class="badge-type">${typeBadge}</span></td>
          <td>${maskBadge}</td>
          <td><strong>${upscaleLabel}</strong></td>
          <td>
            <div class="progress-container">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="status-badge ${statusClass}">${j.status}</span>
                <span style="font-size:10px; font-weight:600;">${pct.toFixed(0)}%</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill" style="width: ${pct}%;"></div>
              </div>
              <div class="progress-meta">
                <span>${speedMeta}</span>
              </div>
            </div>
          </td>
          <td style="text-align: right;">
            <div class="actions-cell">
              ${actionsHtml}
            </div>
          </td>
        </tr>
      `;
    }

    jobsTbody.innerHTML = html;
    btnDownloadAllZip.disabled = !hasCompleted;
    btnDownloadSelectedZip.disabled = (selectedJobIds.size === 0);
    if (btnStopAll) {
      btnStopAll.style.display = anyActive ? 'inline-flex' : 'none';
    }

    // Attach row events
    document.querySelectorAll('.job-checkbox').forEach(cb => {
      cb.onchange = () => {
        const id = cb.getAttribute('data-id');
        if (cb.checked) selectedJobIds.add(id);
        else selectedJobIds.delete(id);
        btnDownloadSelectedZip.disabled = (selectedJobIds.size === 0);
      };
    });

    document.querySelectorAll('.btn-pause').forEach(btn => {
      btn.onclick = async () => {
        btn.textContent = 'Pausing...';
        btn.disabled = true;
        try {
          await fetch(`/api/jobs/${btn.getAttribute('data-id')}/pause`, { method: 'POST' });
          fetchJobs();
        } catch (e) {
          console.error('Pause failed:', e);
        }
      };
    });

    document.querySelectorAll('.btn-resume').forEach(btn => {
      btn.onclick = async () => {
        btn.textContent = 'Resuming...';
        btn.disabled = true;
        try {
          await fetch(`/api/jobs/${btn.getAttribute('data-id')}/resume`, { method: 'POST' });
          fetchJobs();
        } catch (e) {
          console.error('Resume failed:', e);
        }
      };
    });

    document.querySelectorAll('.btn-stop').forEach(btn => {
      btn.onclick = async () => {
        btn.textContent = 'Stopping...';
        btn.disabled = true;
        await cancelJob(btn.getAttribute('data-id'));
      };
    });

    document.querySelectorAll('.btn-retry').forEach(btn => {
      btn.onclick = async () => {
        const id = btn.getAttribute('data-id');
        const j = knownJobs[id];
        if (!j) return;
        btn.disabled = true;
        btn.textContent = 'Retrying...';
        try {
          await fetch('/api/extension/ingest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              file_path: j.input_path,
              remove_logo: j.remove_logo,
              upscale_mode: j.upscale_mode,
              replace_original: j.replace_original || false
            })
          });
          fetchJobs();
        } catch (e) {
          console.error('Retry failed:', e);
        }
      };
    });

    document.querySelectorAll('.btn-inspect').forEach(btn => {
      btn.onclick = () => openCompareModal(btn.getAttribute('data-id'));
    });

    document.querySelectorAll('.btn-del').forEach(btn => {
      btn.onclick = () => deleteJob(btn.getAttribute('data-id'));
    });
  }

  function updatePoolUI(pools) {
    const poolIndicator = document.getElementById('pool-status-indicator');
    if (!poolIndicator || !pools) return;
    const fastText = pools.fast_active > 0 ? `${pools.fast_active} Active` : 'Idle';
    const upscaleText = pools.upscale_active > 0 ? `${pools.upscale_active} Active` : 'Idle';
    poolIndicator.textContent = `Fast Pool: ${fastText} | AI Upscale Pool: ${upscaleText}`;
  }

  const btnOpenOutputs = document.getElementById('btn-open-outputs');
  if (btnOpenOutputs) {
    btnOpenOutputs.onclick = async () => {
      try {
        await fetch('/api/system/open-outputs', { method: 'POST' });
      } catch (e) {
        console.error('Failed to open outputs:', e);
      }
    };
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // --- 6. Live Progress Tracking & UPGRADE 3 Unstoppable Connection ---
  async function fetchJobs() {
    try {
      const res = await fetch('/api/jobs');
      if (res.ok) {
        const jobs = await res.json();
        renderJobs(jobs);
      }
    } catch (e) {
      console.warn('Error fetching jobs:', e);
    }
  }

  function setupWebSocket() {
    const loc = window.location;
    const wsProto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${loc.host}/ws/progress`;

    try {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        wsReconnectDelay = 1000;
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data && data.jobs) {
            renderJobs(data.jobs);
          }
          if (data && data.pools) {
            updatePoolUI(data.pools);
          }
        } catch (err) {
          console.error('WS parse error:', err);
        }
      };
      ws.onclose = () => {
        ws = null;
        setTimeout(setupWebSocket, wsReconnectDelay);
        wsReconnectDelay = Math.min(5000, wsReconnectDelay * 1.5);
      };
    } catch (e) {
      ws = null;
      setTimeout(setupWebSocket, 3000);
    }
  }

  // UPGRADE 3: Visibility change listener
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      fetchHealth();
      fetchJobs();
    }
  });

  // Light 3s fallback poll only when WebSocket is disconnected
  setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      fetchJobs();
    }
  }, 3000);

  // --- 7. Modal Inspection & Split Slider ---
  function openCompareModal(jobId) {
    const job = knownJobs[jobId];
    if (!job) return;

    modalFilename.textContent = `${job.filename} — 4x Pixel Inspection`;
    modalMaskInfo.textContent = `Mask: ${job.detected_mask || 'Auto'} | Target: ${job.upscale_mode.toUpperCase()}`;

    const ts = Date.now();
    const beforeUrl = `/api/jobs/${jobId}/preview/before?t=${ts}`;
    const afterUrl = `/api/jobs/${jobId}/preview/after?t=${ts}`;

    imgBefore.src = beforeUrl;
    imgAfter.src = afterUrl;
    imgSbsBefore.src = beforeUrl;
    imgSbsAfter.src = afterUrl;

    btnModalDownload.href = `/api/jobs/${jobId}/download`;
    setSplitPosition(50);
    modalCompare.classList.add('active');
  }

  function closeCompareModal() {
    modalCompare.classList.remove('active');
  }

  function setSplitPosition(pct) {
    pct = Math.max(0, Math.min(100, pct));
    afterLayer.style.width = `${pct}%`;
    splitDivider.style.left = `${pct}%`;
  }

  function handleSliderMove(e) {
    if (!isSplitDragging) return;
    const rect = splitSliderContainer.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const x = clientX - rect.left;
    const pct = (x / rect.width) * 100;
    setSplitPosition(pct);
  }

  splitDivider.addEventListener('mousedown', () => { isSplitDragging = true; });
  window.addEventListener('mouseup', () => { isSplitDragging = false; });
  window.addEventListener('mousemove', handleSliderMove);

  splitDivider.addEventListener('touchstart', () => { isSplitDragging = true; }, { passive: true });
  window.addEventListener('touchend', () => { isSplitDragging = false; });
  window.addEventListener('touchmove', handleSliderMove, { passive: true });

  modalModeToggle.addEventListener('click', () => {
    if (currentModalMode === 'split') {
      currentModalMode = 'sbs';
      splitSliderContainer.style.display = 'none';
      sideBySideContainer.style.display = 'flex';
      modalModeToggle.textContent = 'Switch to Split Slider';
    } else {
      currentModalMode = 'split';
      splitSliderContainer.style.display = 'block';
      sideBySideContainer.style.display = 'none';
      modalModeToggle.textContent = 'Switch to Side-by-Side';
    }
  });

  modalClose.addEventListener('click', closeCompareModal);
  modalBackdrop.addEventListener('click', closeCompareModal);
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeCompareModal();
  });

  // --- 8. Job Management Actions ---
  async function cancelJob(jobId) {
    try {
      await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      fetchJobs();
    } catch (e) {
      alert('Cancel failed: ' + e.message);
    }
  }

  if (btnStopAll) {
    btnStopAll.addEventListener('click', async () => {
      try {
        await fetch('/api/jobs/cancel-all', { method: 'POST' });
        fetchJobs();
      } catch (e) {
        alert('Cancel all failed: ' + e.message);
      }
    });
  }

  async function deleteJob(jobId) {
    if (!confirm('Remove this job from the list?')) return;
    try {
      selectedJobIds.delete(jobId);
      await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
      fetchJobs();
    } catch (e) {
      alert('Delete failed: ' + e.message);
    }
  }

  if (btnClearHistory) {
    btnClearHistory.addEventListener('click', async () => {
      try {
        await fetch('/api/jobs/clear-history', { method: 'POST' });
        selectedJobIds.clear();
        fetchJobs();
      } catch (e) {
        alert('Failed to clear history: ' + e.message);
      }
    });
  }

  if (thSelectAll) {
    thSelectAll.addEventListener('change', () => {
      const allCbs = document.querySelectorAll('.job-checkbox');
      allCbs.forEach(cb => {
        cb.checked = thSelectAll.checked;
        const id = cb.getAttribute('data-id');
        if (thSelectAll.checked) selectedJobIds.add(id);
        else selectedJobIds.delete(id);
      });
      btnDownloadSelectedZip.disabled = (selectedJobIds.size === 0);
    });
  }

  async function triggerZipDownload(targetIds) {
    const isSelected = targetIds && targetIds.length > 0;
    const btn = isSelected ? btnDownloadSelectedZip : btnDownloadAllZip;
    btn.disabled = true;
    const origText = btn.textContent;
    btn.textContent = 'Archiving...';

    try {
      const res = await fetch('/api/jobs/download-zip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_ids: targetIds || [] })
      });
      if (!res.ok) throw new Error('ZIP generation failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = isSelected ? 'FlowStudio_Selected_Batch.zip' : 'FlowStudio_Clean_Batch.zip';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert('ZIP download failed: ' + e.message);
    } finally {
      btn.textContent = origText;
      btn.disabled = false;
    }
  }

  btnDownloadAllZip.addEventListener('click', () => triggerZipDownload([]));
  if (btnDownloadSelectedZip) {
    btnDownloadSelectedZip.addEventListener('click', () => triggerZipDownload(Array.from(selectedJobIds)));
  }

  perfModeSelect.addEventListener('change', (e) => {
    updatePerfMode(e.target.value);
  });

  btnRefresh.addEventListener('click', () => {
    fetchHealth();
    fetchJobs();
  });

  // Init
  fetchHealth();
  fetchJobs();
  setupWebSocket();
})();
