// FlowStudio Pro - Client Application Engine
(function () {
  'use strict';

  // DOM Elements
  const badgeGpu = document.getElementById('badge-gpu');
  const badgeEncoder = document.getElementById('badge-encoder');
  const badgeMasks = document.getElementById('badge-masks');
  const perfModeSelect = document.getElementById('perf-mode-select');
  const btnRefresh = document.getElementById('btn-refresh');
  const btnOpenUninstall = document.getElementById('btn-open-uninstall');

  // Uninstall Modal Elements
  const modalUninstall = document.getElementById('modal-uninstall');
  const uninstallBackdrop = document.getElementById('uninstall-backdrop');
  const uninstallModalClose = document.getElementById('uninstall-modal-close');
  const uninstallConfirmBody = document.getElementById('uninstall-confirm-body');
  const uninstallDoneBody = document.getElementById('uninstall-done-body');
  const uninstallModalFooter = document.getElementById('uninstall-modal-footer');
  const uninstallCleanCaches = document.getElementById('uninstall-clean-caches');
  const uninstallErrorMsg = document.getElementById('uninstall-error-msg');
  const btnUninstallCancel = document.getElementById('btn-uninstall-cancel');
  const btnUninstallConfirm = document.getElementById('btn-uninstall-confirm');

  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const toggleRemoveLogo = document.getElementById('toggle-remove-logo');
  const controlRemoveLogo = document.getElementById('control-remove-logo');
  const upscaleSelect = document.getElementById('upscale-select');
  const selectedSummary = document.getElementById('selected-summary');
  const btnStartBatch = document.getElementById('btn-start-batch');

  const tabCleaner = document.getElementById('tab-cleaner');
  const tabUpscaler = document.getElementById('tab-upscaler');
  const tabProject = document.getElementById('tab-project');
  const uploadPanel = document.getElementById('upload-panel');
  const projectPanel = document.getElementById('project-panel');
  const panelTitle = document.getElementById('panel-title');
  const panelDesc = document.getElementById('panel-desc');
  const dropzoneMainText = document.getElementById('dropzone-main-text');

  // Smart Project Folder / ZIP Elements
  const btnPickFolder = document.getElementById('btn-pick-folder');
  const btnRescanFolder = document.getElementById('btn-rescan-folder');
  const projectFolderPathEl = document.getElementById('project-folder-path');
  const projectZipDropzone = document.getElementById('project-zip-dropzone');
  const projectZipInput = document.getElementById('project-zip-input');
  const btnPickZip = document.getElementById('btn-pick-zip');
  const projectZipMeta = document.getElementById('project-zip-meta');
  const projectScanCard = document.getElementById('project-scan-card');
  const scanTotalCount = document.getElementById('scan-total-count');
  const scanNeedsCount = document.getElementById('scan-needs-count');
  const scanCleanCount = document.getElementById('scan-clean-count');
  const scanOtherCount = document.getElementById('scan-other-count');
  const projectFilesSummary = document.getElementById('project-files-summary');
  const projectFilesList = document.getElementById('project-files-list');
  const projectModeGroup = document.getElementById('project-mode-group');
  const modeInPlaceRadio = document.getElementById('mode-in-place');
  const modeNewFolderRadio = document.getElementById('mode-new-folder');
  const projectModeHint = document.getElementById('project-mode-hint');
  const projectOutputNameGroup = document.getElementById('project-output-name-group');
  const projectOutputName = document.getElementById('project-output-name');
  const projectUpscaleSelect = document.getElementById('project-upscale-select');
  const projectUpscaleCleanWrap = document.getElementById('project-upscale-clean-wrap');
  const projectUpscaleClean = document.getElementById('project-upscale-clean');
  const btnStartProject = document.getElementById('btn-start-project');
  const projectProgressCard = document.getElementById('project-progress-card');
  const projectJobStatus = document.getElementById('project-job-status');
  const projectJobName = document.getElementById('project-job-name');
  const projectJobCounts = document.getElementById('project-job-counts');
  const btnProjPause = document.getElementById('btn-proj-pause');
  const btnProjResume = document.getElementById('btn-proj-resume');
  const btnProjCancel = document.getElementById('btn-proj-cancel');
  const btnProjOpenFolder = document.getElementById('btn-proj-open-folder');
  const projectJobBar = document.getElementById('project-job-bar');
  const projectJobCurrentFile = document.getElementById('project-job-current-file');
  const projectJobPct = document.getElementById('project-job-pct');
  const projectJobOutputPath = document.getElementById('project-job-output-path');

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

  // Smart Project State
  let projectSourceType = null; // 'folder' | 'zip' | null
  let selectedFolderPath = '';
  let selectedZipFile = null;
  let lastScanResult = null;
  let activeProjectJobId = null;
  let isProjectSubmitting = false;
  let lastProjectUpscaleMode = 'off';

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
  function setActiveTab(tabName) {
    if (tabCleaner) tabCleaner.classList.toggle('active', tabName === 'cleaner');
    if (tabUpscaler) tabUpscaler.classList.toggle('active', tabName === 'upscaler');
    if (tabProject) tabProject.classList.toggle('active', tabName === 'project');

    if (uploadPanel) uploadPanel.style.display = tabName === 'project' ? 'none' : 'block';
    if (projectPanel) projectPanel.style.display = tabName === 'project' ? 'block' : 'none';

    if (tabName === 'cleaner') {
      panelTitle.textContent = 'Batch Media Processing';
      panelDesc.textContent = 'Drag & drop up to 50+ images and videos simultaneously';
      dropzoneMainText.textContent = 'Drag and drop images or videos here';
      toggleRemoveLogo.checked = true;
      controlRemoveLogo.style.display = 'flex';
    } else if (tabName === 'upscaler') {
      panelTitle.textContent = 'Personal AI Super-Resolution (2K / 4K)';
      panelDesc.textContent = 'Upscale personal videos, anime, home clips, and images with neural AI (Zero watermark logic)';
      dropzoneMainText.textContent = 'Drag and drop any personal videos or images to upscale';
      toggleRemoveLogo.checked = false;
      controlRemoveLogo.style.display = 'none';
      if (upscaleSelect.value === 'off') {
        upscaleSelect.value = '2x_anime';
      }
    }
  }

  if (tabCleaner) tabCleaner.addEventListener('click', () => setActiveTab('cleaner'));
  if (tabUpscaler) tabUpscaler.addEventListener('click', () => setActiveTab('upscaler'));
  if (tabProject) tabProject.addEventListener('click', () => setActiveTab('project'));

  // --- 2c. Smart Project Folder / ZIP Logic ---
  function getSelectedProjectMode() {
    return (modeNewFolderRadio && modeNewFolderRadio.checked) ? 'new_folder' : 'in_place';
  }

  function updateProjectOptionsUI() {
    if (!projectPanel) return;
    const isZip = projectSourceType === 'zip';
    const mode = getSelectedProjectMode();

    if (projectModeGroup) {
      projectModeGroup.style.display = isZip ? 'none' : 'flex';
    }
    if (projectModeHint) {
      projectModeHint.textContent = mode === 'new_folder'
        ? 'Creates a clean copy inside Downloads/<Folder Name> preserving all subfolders & non-media files.'
        : 'Replaces ONLY watermarked files inside the original PC folder; everything else untouched.';
    }
    if (projectOutputNameGroup) {
      const showRename = isZip || mode === 'new_folder';
      projectOutputNameGroup.style.display = showRename ? 'flex' : 'none';
      if (isZip && selectedZipFile && projectOutputName && !projectOutputName.dataset.userEdited) {
        projectOutputName.value = selectedZipFile.name.replace(/\.zip$/i, '');
      } else if (!isZip && selectedFolderPath && projectOutputName && !projectOutputName.dataset.userEdited) {
        const baseName = selectedFolderPath.split(/[\\/]/).filter(Boolean).pop() || 'FlowProject';
        projectOutputName.placeholder = `${baseName}_clean`;
      }
    }
    if (projectUpscaleCleanWrap && projectUpscaleSelect) {
      const curUpMode = projectUpscaleSelect.value;
      const showUpscaleClean = curUpMode !== 'off';
      projectUpscaleCleanWrap.style.display = showUpscaleClean ? 'inline-flex' : 'none';
      if (projectUpscaleClean) {
        if (!showUpscaleClean) {
          projectUpscaleClean.checked = false;
        } else if (lastProjectUpscaleMode === 'off') {
          projectUpscaleClean.checked = true;
        }
      }
      lastProjectUpscaleMode = curUpMode;
    }
    if (btnStartProject) {
      const readyFolder = projectSourceType === 'folder' && !!selectedFolderPath && !!lastScanResult;
      const readyZip = projectSourceType === 'zip' && !!selectedZipFile;
      btnStartProject.disabled = isProjectSubmitting || !(readyFolder || readyZip);
    }
  }

  function formatApiError(resData, fallback) {
    if (!resData) return fallback;
    const d = resData.detail !== undefined ? resData.detail : resData.error;
    if (!d) return fallback;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      return d.map(x => (x && x.msg ? x.msg : JSON.stringify(x))).join('; ') || fallback;
    }
    return JSON.stringify(d);
  }

  function renderScanSummary(scan) {
    if (!projectScanCard || !scan) return;
    projectScanCard.style.display = 'flex';
    if (scanTotalCount) scanTotalCount.textContent = String(scan.total_files || 0);
    if (scanNeedsCount) scanNeedsCount.textContent = String(scan.needs_clean_count || 0);
    if (scanCleanCount) scanCleanCount.textContent = String(scan.already_clean_count || 0);
    if (scanOtherCount) scanOtherCount.textContent = String(scan.other_files_count || 0);
    if (projectFilesSummary) {
      projectFilesSummary.textContent = `View File Breakdown (${scan.total_files || 0} files)`;
    }

    if (projectFilesList) {
      const rows = [];
      for (const item of (scan.needs_clean || [])) {
        rows.push({ item, cls: 'scan-badge-clean', label: 'Clean Media' });
      }
      for (const item of (scan.already_clean || [])) {
        rows.push({ item, cls: 'scan-badge-skip', label: 'Skipped' });
      }
      for (const item of (scan.other_files || [])) {
        rows.push({ item, cls: 'scan-badge-other', label: 'Kept Verbatim' });
      }
      if (rows.length === 0) {
        projectFilesList.innerHTML = '<div class="project-file-row"><span class="project-file-rel">Folder is empty</span></div>';
      } else {
        projectFilesList.innerHTML = rows.map(({ item, cls, label }) => {
          const dims = (item.width && item.height) ? `${item.width}×${item.height}` : (item.ext || '');
          return `
            <div class="project-file-row">
              <span class="project-file-rel">${escapeHtml(item.rel_path || item.filename)}</span>
              <span class="project-file-meta">
                <span class="file-subtext">${escapeHtml(dims)}</span>
                <span class="scan-badge ${cls}">${label}</span>
              </span>
            </div>
          `;
        }).join('');
      }
    }
  }

  async function scanSelectedFolder(folderPath) {
    if (!folderPath) return;
    if (projectFolderPathEl) {
      projectFolderPathEl.textContent = `${folderPath} (Scanning...)`;
    }
    try {
      const res = await fetch('/api/project/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: folderPath })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Scan failed');
      }
      const data = await res.json();
      lastScanResult = data;
      if (projectFolderPathEl) projectFolderPathEl.textContent = data.folder_path || folderPath;
      if (btnRescanFolder) btnRescanFolder.style.display = 'inline-flex';
      renderScanSummary(data);
    } catch (err) {
      lastScanResult = null;
      if (projectFolderPathEl) projectFolderPathEl.textContent = folderPath;
      alert('Folder scan failed: ' + err.message);
    } finally {
      updateProjectOptionsUI();
    }
  }

  async function openFolderInExplorer(folderPath) {
    if (!folderPath) return;
    try {
      const res = await fetch('/api/system/open-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: folderPath })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Could not open folder');
      }
    } catch (err) {
      alert('Failed to open folder: ' + err.message);
    }
  }

  function stageProjectZip(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.zip')) {
      alert('Please select a valid .zip project archive.');
      return;
    }
    projectSourceType = 'zip';
    selectedZipFile = file;
    selectedFolderPath = '';
    lastScanResult = null;
    if (projectFolderPathEl) projectFolderPathEl.textContent = 'No folder selected';
    if (btnRescanFolder) btnRescanFolder.style.display = 'none';
    if (projectScanCard) projectScanCard.style.display = 'none';
    if (projectOutputName) {
      delete projectOutputName.dataset.userEdited;
      projectOutputName.value = file.name.replace(/\.zip$/i, '');
    }
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    if (projectZipMeta) {
      projectZipMeta.textContent = `📦 ${file.name} (${mb} MB) — ready to extract & clean`;
    }
    updateProjectOptionsUI();
  }

  function renderActiveProjectProgress(jobs) {
    if (!projectProgressCard) return;
    let job = activeProjectJobId ? jobs.find(j => j.id === activeProjectJobId) : null;
    if (!job) {
      const projectJobs = jobs
        .filter(j => j.file_type === 'project')
        .sort((a, b) => b.created_at - a.created_at);
      if (projectJobs.length > 0 && (projectJobs[0].status === 'processing' || projectJobs[0].status === 'queued' || projectJobs[0].status === 'paused')) {
        job = projectJobs[0];
        activeProjectJobId = job.id;
      }
    }
    if (!job) {
      activeProjectJobId = null;
      projectProgressCard.style.display = 'none';
      return;
    }

    projectProgressCard.style.display = 'flex';
    const pct = Math.round(job.progress_pct || 0);
    if (projectJobStatus) {
      projectJobStatus.className = `status-badge status-${job.status === 'paused' ? 'paused' : job.status}`;
      projectJobStatus.textContent = job.status;
    }
    if (projectJobName) projectJobName.textContent = job.filename || 'Project';
    if (projectJobBar) projectJobBar.style.width = `${pct}%`;
    if (projectJobPct) projectJobPct.textContent = `${pct}%`;

    const ps = job.project_summary || {};
    if (projectJobCounts) {
      if (job.status === 'completed') {
        const cleaned = ps.cleaned_count || 0;
        const kept = (ps.copied_count || 0) + (ps.skipped_count || 0);
        const failed = ps.failed_count || 0;
        projectJobCounts.textContent = `Cleaned: ${cleaned} · Kept: ${kept}${failed ? ` · Failed: ${failed}` : ''}`;
      } else if (job.total_frames > 0) {
        projectJobCounts.textContent = `Files: ${job.current_frame || 0}/${job.total_frames}`;
      } else {
        projectJobCounts.textContent = '';
      }
    }

    if (projectJobCurrentFile) {
      if (job.status === 'completed') {
        projectJobCurrentFile.textContent = `Completed in ${job.elapsed_sec || 0}s`;
      } else if (job.status === 'failed') {
        projectJobCurrentFile.textContent = job.error || 'Project processing failed';
      } else if (job.status === 'cancelled') {
        projectJobCurrentFile.textContent = 'Cancelled by user';
      } else {
        projectJobCurrentFile.textContent = job.current_file || 'Processing...';
      }
    }

    const outDir = job.final_saved_path || job.output_path || '';
    if (projectJobOutputPath) {
      if (job.status === 'completed' && outDir) {
        projectJobOutputPath.style.display = 'block';
        projectJobOutputPath.textContent = `Saved in: ${outDir}`;
      } else {
        projectJobOutputPath.style.display = 'none';
      }
    }

    const isActive = job.status === 'queued' || job.status === 'processing';
    const isPaused = job.status === 'paused';
    if (btnProjPause) {
      btnProjPause.style.display = isActive ? 'inline-flex' : 'none';
      btnProjPause.disabled = false;
      btnProjPause.onclick = async () => {
        btnProjPause.disabled = true;
        await fetch(`/api/jobs/${job.id}/pause`, { method: 'POST' });
        fetchJobs();
      };
    }
    if (btnProjResume) {
      btnProjResume.style.display = isPaused ? 'inline-flex' : 'none';
      btnProjResume.disabled = false;
      btnProjResume.onclick = async () => {
        btnProjResume.disabled = true;
        await fetch(`/api/jobs/${job.id}/resume`, { method: 'POST' });
        fetchJobs();
      };
    }
    if (btnProjCancel) {
      btnProjCancel.style.display = (isActive || isPaused) ? 'inline-flex' : 'none';
      btnProjCancel.disabled = false;
      btnProjCancel.onclick = async () => {
        btnProjCancel.disabled = true;
        await cancelJob(job.id);
      };
    }
    if (btnProjOpenFolder) {
      btnProjOpenFolder.style.display = (job.status === 'completed' && outDir) ? 'inline-flex' : 'none';
      btnProjOpenFolder.onclick = () => openFolderInExplorer(outDir);
    }
  }

  if (btnPickFolder) {
    btnPickFolder.addEventListener('click', async () => {
      btnPickFolder.disabled = true;
      const origText = btnPickFolder.textContent;
      btnPickFolder.textContent = 'Opening Picker...';
      try {
        const res = await fetch('/api/system/pick-folder', { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.ok && data.path) {
          projectSourceType = 'folder';
          selectedFolderPath = data.path;
          selectedZipFile = null;
          if (projectZipInput) projectZipInput.value = '';
          if (projectZipMeta) projectZipMeta.textContent = 'Drop a Flow project .ZIP here or click to browse';
          if (projectOutputName) {
            delete projectOutputName.dataset.userEdited;
            projectOutputName.value = '';
          }
          await scanSelectedFolder(data.path);
        }
      } catch (err) {
        alert('Folder picker failed: ' + err.message);
      } finally {
        btnPickFolder.disabled = false;
        btnPickFolder.textContent = origText;
      }
    });
  }

  if (btnRescanFolder) {
    btnRescanFolder.addEventListener('click', () => {
      if (selectedFolderPath) scanSelectedFolder(selectedFolderPath);
    });
  }

  if (btnPickZip && projectZipInput) {
    btnPickZip.addEventListener('click', (e) => {
      e.stopPropagation();
      projectZipInput.click();
    });
  }

  if (projectZipDropzone && projectZipInput) {
    projectZipDropzone.addEventListener('click', () => projectZipInput.click());
    projectZipDropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      projectZipDropzone.classList.add('dragover');
    });
    projectZipDropzone.addEventListener('dragleave', () => {
      projectZipDropzone.classList.remove('dragover');
    });
    projectZipDropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      projectZipDropzone.classList.remove('dragover');
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        stageProjectZip(e.dataTransfer.files[0]);
      }
    });
    projectZipInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        stageProjectZip(e.target.files[0]);
      }
    });
  }

  if (modeInPlaceRadio) modeInPlaceRadio.addEventListener('change', updateProjectOptionsUI);
  if (modeNewFolderRadio) modeNewFolderRadio.addEventListener('change', updateProjectOptionsUI);
  if (projectUpscaleSelect) projectUpscaleSelect.addEventListener('change', updateProjectOptionsUI);
  if (projectOutputName) {
    projectOutputName.addEventListener('input', () => {
      projectOutputName.dataset.userEdited = '1';
    });
  }

  if (btnStartProject) {
    btnStartProject.addEventListener('click', async () => {
      if (isProjectSubmitting) return;
      isProjectSubmitting = true;
      btnStartProject.disabled = true;
      const origText = btnStartProject.textContent;
      btnStartProject.textContent = projectSourceType === 'zip' ? 'Uploading ZIP...' : 'Starting...';

      try {
        const upMode = projectUpscaleSelect ? projectUpscaleSelect.value : 'off';
        const upClean = (upMode !== 'off') && projectUpscaleClean && projectUpscaleClean.checked;
        let resData = null;

        if (projectSourceType === 'zip' && selectedZipFile) {
          const fd = new FormData();
          fd.append('file', selectedZipFile);
          fd.append('output_name', (projectOutputName ? projectOutputName.value.trim() : '') || '');
          fd.append('upscale_mode', upMode);
          fd.append('upscale_clean_files', String(upClean));
          const res = await fetch('/api/project/upload-zip', { method: 'POST', body: fd });
          resData = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(formatApiError(resData, `ZIP upload failed (HTTP ${res.status})`));
          selectedZipFile = null;
          if (projectZipInput) projectZipInput.value = '';
          if (projectZipMeta) projectZipMeta.textContent = 'Drop a Flow project .ZIP here or click to browse';
        } else if (projectSourceType === 'folder' && selectedFolderPath) {
          const mode = getSelectedProjectMode();
          const outName = (mode === 'new_folder' && projectOutputName && projectOutputName.value.trim())
            ? projectOutputName.value.trim()
            : null;
          const res = await fetch('/api/project/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              folder_path: selectedFolderPath,
              mode,
              output_name: outName,
              upscale_mode: upMode,
              upscale_clean_files: upClean
            })
          });
          resData = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(formatApiError(resData, `Project start failed (HTTP ${res.status})`));
        }

        if (resData && resData.job_id) {
          activeProjectJobId = resData.job_id;
          fetchJobs();
        }
      } catch (err) {
        alert('Project start failed: ' + err.message);
      } finally {
        isProjectSubmitting = false;
        btnStartProject.textContent = origText;
        updateProjectOptionsUI();
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
      renderActiveProjectProgress([]);
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
    renderActiveProjectProgress(jobs);

    let html = '';
    for (let j of jobs) {
      knownJobs[j.id] = j;
      const isProject = j.file_type === 'project';
      if (j.status === 'completed' && !isProject) hasCompleted = true;
      if (j.status === 'queued' || j.status === 'processing') anyActive = true;

      let isSelected = !isProject && selectedJobIds.has(j.id);
      let pct = j.progress_pct || 0;
      let statusClass = `status-${j.status}`;
      let isVideo = j.file_type === 'video';
      let typeBadge = isProject ? (j.is_zip ? '📦 Project ZIP' : '📁 Project') : (isVideo ? '🎬 Video' : '🖼️ Image');

      let maskLabel = isProject ? (j.mode === 'in_place' ? 'In-Place' : 'New Folder') : (j.detected_mask || 'Auto-Detect');
      let maskBadge = `<span class="badge-mask">${escapeHtml(maskLabel)}</span>`;
      let upscaleLabel = j.upscale_mode === 'off' ? 'Native' : j.upscale_mode.replace('_', ' ').toUpperCase();

      let speedMeta = '';
      if (j.status === 'processing') {
        if (isProject) {
          const filePart = j.total_frames > 0 ? `File ${j.current_frame}/${j.total_frames}` : 'Scanning...';
          speedMeta = `${filePart}${j.current_file ? ` · ${escapeHtml(j.current_file)}` : ''}`;
        } else if (isVideo && j.total_frames > 0) {
          speedMeta = `Frame ${j.current_frame}/${j.total_frames} • ETA ${j.eta_sec}s`;
        } else {
          speedMeta = 'Processing...';
        }
      } else if (j.status === 'paused') {
        speedMeta = isProject
          ? `Paused · File ${j.current_frame || 0}/${j.total_frames || 0}`
          : `Paused · Frame ${j.current_frame || 0}/${j.total_frames || 0}`;
        statusClass = 'status-paused';
      } else if (j.status === 'completed') {
        if (isProject) {
          const ps = j.project_summary || {};
          const cleaned = ps.cleaned_count || 0;
          const kept = (ps.copied_count || 0) + (ps.skipped_count || 0);
          speedMeta = `${cleaned} cleaned · ${kept} kept (${j.elapsed_sec || 0}s)`;
        } else {
          speedMeta = `Finished in ${j.elapsed_sec || 0}s`;
        }
      } else if (j.status === 'cancelled') {
        speedMeta = 'Cancelled by user';
      } else if (j.status === 'failed') {
        const errFull = j.error ? String(j.error) : 'Error';
        speedMeta = `<span title="${escapeHtml(errFull)}">${escapeHtml(errFull.substring(0, 60))}</span>`;
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
        if (isProject) {
          const outPath = j.final_saved_path || j.output_path || '';
          actionsHtml = `
            <button class="btn btn-primary btn-xs btn-open-proj-folder" data-path="${escapeHtml(outPath)}" ${outPath ? '' : 'disabled'}>📂 Open Output Folder</button>
            <button class="btn btn-secondary btn-xs btn-del" data-id="${j.id}" title="Delete">×</button>
          `;
        } else {
          actionsHtml = `
            <button class="btn btn-secondary btn-xs btn-inspect" data-id="${j.id}">Inspect 4×</button>
            <a class="btn btn-primary btn-xs" href="/api/jobs/${j.id}/download" download>Download</a>
            <button class="btn btn-secondary btn-xs btn-del" data-id="${j.id}" title="Delete">×</button>
          `;
        }
      } else {
        actionsHtml = isProject ? `
          <button class="btn btn-secondary btn-xs btn-del" data-id="${j.id}" title="Remove">×</button>
        ` : `
          <button class="btn btn-secondary btn-xs btn-retry" data-id="${j.id}" title="Retry job">Retry</button>
          <button class="btn btn-secondary btn-xs btn-del" data-id="${j.id}" title="Remove">×</button>
        `;
      }

      const checkboxHtml = isProject
        ? ''
        : `<input type="checkbox" class="job-checkbox" data-id="${j.id}" ${isSelected ? 'checked' : ''}>`;

      html += `
        <tr data-id="${j.id}">
          <td>
            ${checkboxHtml}
          </td>
          <td>
            <div class="file-cell">
              <div class="file-title-row">
                <span class="file-name">${escapeHtml(j.filename)}</span>
              </div>
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

    document.querySelectorAll('.btn-open-proj-folder').forEach(btn => {
      btn.onclick = () => openFolderInExplorer(btn.getAttribute('data-path'));
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
    if (!job) {
      activeProjectJobId = null;
      projectProgressCard.style.display = 'none';
      return;
    }

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

  // --- 7b. Uninstall Modal Controls ---
  function openUninstallModal() {
    if (!modalUninstall) return;
    if (uninstallConfirmBody) uninstallConfirmBody.style.display = 'flex';
    if (uninstallDoneBody) uninstallDoneBody.style.display = 'none';
    if (uninstallModalFooter) uninstallModalFooter.style.display = 'flex';
    if (uninstallErrorMsg) {
      uninstallErrorMsg.style.display = 'none';
      uninstallErrorMsg.textContent = '';
    }
    if (btnUninstallConfirm) {
      btnUninstallConfirm.disabled = false;
      btnUninstallConfirm.textContent = 'Delete FlowStudio & Environment';
    }
    if (uninstallCleanCaches) uninstallCleanCaches.checked = true;
    modalUninstall.classList.add('active');
  }

  function closeUninstallModal() {
    if (modalUninstall) modalUninstall.classList.remove('active');
  }

  if (btnOpenUninstall) btnOpenUninstall.addEventListener('click', openUninstallModal);
  if (uninstallModalClose) uninstallModalClose.addEventListener('click', closeUninstallModal);
  if (uninstallBackdrop) uninstallBackdrop.addEventListener('click', closeUninstallModal);
  if (btnUninstallCancel) btnUninstallCancel.addEventListener('click', closeUninstallModal);

  if (btnUninstallConfirm) {
    btnUninstallConfirm.addEventListener('click', async () => {
      btnUninstallConfirm.disabled = true;
      btnUninstallConfirm.textContent = 'Uninstalling...';
      if (uninstallErrorMsg) {
        uninstallErrorMsg.style.display = 'none';
        uninstallErrorMsg.textContent = '';
      }

      try {
        const res = await fetch('/api/system/uninstall', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            clean_caches: uninstallCleanCaches ? Boolean(uninstallCleanCaches.checked) : true,
            confirm: 'UNINSTALL_FLOWSTUDIO'
          })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data.detail || `Uninstall failed (HTTP ${res.status})`);
        }
        if (uninstallConfirmBody) uninstallConfirmBody.style.display = 'none';
        if (uninstallModalFooter) uninstallModalFooter.style.display = 'none';
        if (uninstallDoneBody) uninstallDoneBody.style.display = 'flex';
      } catch (err) {
        if (uninstallErrorMsg) {
          uninstallErrorMsg.textContent = err.message;
          uninstallErrorMsg.style.display = 'block';
        }
        btnUninstallConfirm.disabled = false;
        btnUninstallConfirm.textContent = 'Delete FlowStudio & Environment';
      }
    });
  }

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeCompareModal();
      closeUninstallModal();
    }
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
  updateProjectOptionsUI();
  fetchHealth();
  fetchJobs();
  setupWebSocket();
  try {
    if (new URLSearchParams(window.location.search).get('uninstall') === '1') {
      openUninstallModal();
    }
  } catch (_) {}
})();
